from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, CompatMode, OverflowPolicy, TargetModel
from cpp2py.diagnostics import Severity
from cpp2py.testing.py_runner import run_python

router = APIRouter(tags=["execute"])

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cpp2py-exec-")

_MAX_SOURCE_BYTES = 256 * 1024
_MAX_STDIN_BYTES = 1024 * 1024


class ExecuteRequest(BaseModel):
    python_source: str | None = Field(None, description="Python source code to execute")
    source_code: str | None = Field(None, description="Optional C++ source code to translate and execute")
    stdin: str = Field("", description="Standard input text to feed to the program")
    timeout: float = Field(5.0, description="Execution timeout in seconds", ge=0.1, le=30.0)
    compat: str = Field("range_guided", description="Compatibility mode if compiling C++")
    overflow: str = Field("assume_no_overflow", description="Overflow policy if compiling C++")
    fold_constants: bool = Field(True, description="Enable constant folding if compiling C++")

    @field_validator("python_source")
    @classmethod
    def _check_py_size(cls, v: str | None) -> str | None:
        if v is not None and len(v.encode("utf-8")) > _MAX_SOURCE_BYTES:
            raise ValueError(f"python_source exceeds maximum allowed size of {_MAX_SOURCE_BYTES} bytes")
        return v

    @field_validator("source_code")
    @classmethod
    def _check_source_size(cls, v: str | None) -> str | None:
        if v is not None and len(v.encode("utf-8")) > _MAX_SOURCE_BYTES:
            raise ValueError(f"source_code exceeds maximum allowed size of {_MAX_SOURCE_BYTES} bytes")
        return v

    @field_validator("stdin")
    @classmethod
    def _check_stdin_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _MAX_STDIN_BYTES:
            raise ValueError(f"stdin exceeds maximum allowed size of {_MAX_STDIN_BYTES} bytes")
        return v


class ExecuteResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    timed_out: bool = False
    output_capped: bool = False


def _run_isolated_python(py_source: str, stdin_text: str, timeout: float):
    return run_python(py_source, stdin_text=stdin_text, timeout=timeout)


@router.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest) -> ExecuteResponse:
    py_code = req.python_source

    if not py_code or not py_code.strip():
        if not req.source_code or not req.source_code.strip():
            raise HTTPException(status_code=422, detail="Either python_source or source_code must be provided")

        target = TargetModel(overflow_policy=OverflowPolicy(req.overflow))
        config = CompilerConfig(
            target=target,
            compat_mode=CompatMode(req.compat),
            fold_constants=req.fold_constants,
        )
        comp_res = compile_source(req.source_code, "input.cpp", config)
        if not comp_res.success or comp_res.python_source is None:
            err_msgs = [f"[{d.code}] {d.message}" for d in comp_res.diagnostics if d.severity == Severity.ERROR]
            return ExecuteResponse(
                success=False,
                stdout="",
                stderr="Compilation failed:\n" + "\n".join(err_msgs),
                exit_code=2,
                duration_ms=0.0,
                timed_out=False,
                output_capped=False,
            )
        py_code = comp_res.python_source

    try:
        compile(py_code, "<generated>", "exec")
    except SyntaxError as e:
        return ExecuteResponse(
            success=False,
            stdout="",
            stderr=f"SyntaxError in generated Python: {e}",
            exit_code=1,
            duration_ms=0.0,
            timed_out=False,
            output_capped=False,
        )

    loop = asyncio.get_event_loop()
    t0 = time.monotonic()
    try:
        res = await loop.run_in_executor(
            _EXECUTOR,
            _run_isolated_python,
            py_code,
            req.stdin,
            req.timeout,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Execution process error: {exc}",
        ) from exc

    duration_ms = round((time.monotonic() - t0) * 1000, 1)

    return ExecuteResponse(
        success=(res.exit_code == 0 and not res.timed_out),
        stdout=res.stdout,
        stderr=res.stderr,
        exit_code=res.exit_code,
        duration_ms=duration_ms,
        timed_out=res.timed_out,
        output_capped=res.output_capped,
    )
