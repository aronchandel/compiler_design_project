"""Translation router — POST /api/translate.

Invokes the real cpp2py compiler via compile_source().
Never fabricates output; on error returns structured diagnostics.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from cpp2py.compiler import compile_source, CompilationResult
from cpp2py.config import CompilerConfig, CompatMode, OverflowPolicy, TargetModel
from cpp2py.diagnostics import Severity

router = APIRouter(tags=["translate"])

# Thread pool for blocking compiler work; keeps the event loop free
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cpp2py-")

# Request size limit: 256 KB of C++ source
_MAX_SOURCE_BYTES = 256 * 1024


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class TranslateRequest(BaseModel):
    source_code: str = Field(..., description="C++ source code to translate")
    filename: str = Field("input.cpp", description="Logical filename (for diagnostics)")
    compat: str = Field("range_guided", description="Compatibility mode: naive | always | range_guided")
    overflow: str = Field("assume_no_overflow", description="Overflow policy: assume_no_overflow | wrap | trap")
    fold_constants: bool = Field(True, description="Enable constant folding")
    idiomatic_loops: bool = Field(False, description="Emit idiomatic Python for-loops where possible")

    @field_validator("source_code")
    @classmethod
    def _check_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _MAX_SOURCE_BYTES:
            raise ValueError(f"source_code exceeds maximum allowed size of {_MAX_SOURCE_BYTES} bytes")
        return v

    @field_validator("compat")
    @classmethod
    def _check_compat(cls, v: str) -> str:
        allowed = {"naive", "always", "range_guided"}
        if v not in allowed:
            raise ValueError(f"compat must be one of {sorted(allowed)}")
        return v

    @field_validator("overflow")
    @classmethod
    def _check_overflow(cls, v: str) -> str:
        allowed = {"assume_no_overflow", "wrap", "trap"}
        if v not in allowed:
            raise ValueError(f"overflow must be one of {sorted(allowed)}")
        return v


class DiagnosticItem(BaseModel):
    severity: str
    code: str
    message: str
    location: str | None = None


class TranslateResponse(BaseModel):
    success: bool
    python_source: str | None
    diagnostics: list[DiagnosticItem]
    error_count: int
    warning_count: int
    duration_ms: float
    # Optional summary fields populated on success
    function_count: int | None = None
    line_count_cpp: int | None = None
    line_count_py: int | None = None
    ir_source: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_config(req: TranslateRequest) -> CompilerConfig:
    target = TargetModel(overflow_policy=OverflowPolicy(req.overflow))
    return CompilerConfig(
        target=target,
        compat_mode=CompatMode(req.compat),
        fold_constants=req.fold_constants,
        idiomatic_loops=req.idiomatic_loops,
    )


def _diag_to_item(d: Any) -> DiagnosticItem:
    loc: str | None = None
    if d.span is not None:
        loc = f"{d.span.file}:{d.span.start.line}:{d.span.start.col}"
    return DiagnosticItem(
        severity=d.severity.value,
        code=d.code,
        message=d.message,
        location=loc,
    )


def _run_compile(source_code: str, filename: str, config: CompilerConfig) -> CompilationResult:
    """Blocking wrapper around compile_source; runs in thread pool."""
    return compile_source(source_code, filename, config)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest) -> TranslateResponse:
    """
    Translate C++ source code to Python using the cpp2py compiler.

    Returns the generated Python source, translation status, and diagnostics.
    Never returns fabricated output.
    """
    if not req.source_code.strip():
        raise HTTPException(status_code=422, detail="source_code must not be empty")

    config = _build_config(req)
    loop = asyncio.get_event_loop()

    t0 = time.monotonic()
    try:
        result: CompilationResult = await loop.run_in_executor(
            _EXECUTOR,
            _run_compile,
            req.source_code,
            req.filename,
            config,
        )
    except Exception as exc:
        # Internal error from the compiler itself – do not expose details
        raise HTTPException(
            status_code=500,
            detail="Compiler pipeline raised an unexpected error. See server logs.",
        ) from exc

    duration_ms = round((time.monotonic() - t0) * 1000, 1)

    diag_items = [_diag_to_item(d) for d in result.diagnostics]
    error_count = sum(1 for d in result.diagnostics if d.severity == Severity.ERROR)
    warning_count = sum(1 for d in result.diagnostics if d.severity == Severity.WARNING)

    func_count: int | None = None
    ir_text: str | None = None
    if result.ir:
        func_count = len(result.ir.functions)
        from cpp2py.ir.printer import format_module
        ir_text = format_module(result.ir)

    py_lines: int | None = None
    if result.python_source:
        py_lines = result.python_source.count("\n") + 1

    cpp_lines = req.source_code.count("\n") + 1

    return TranslateResponse(
        success=result.success,
        python_source=result.python_source,
        diagnostics=diag_items,
        error_count=error_count,
        warning_count=warning_count,
        duration_ms=duration_ms,
        function_count=func_count,
        line_count_cpp=cpp_lines,
        line_count_py=py_lines,
        ir_source=ir_text,
    )
