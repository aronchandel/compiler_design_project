"""Phase 7 fidelity reporting and fault localisation router.

POST /api/report/fidelity   — generate a fidelity report for submitted C++ source
GET  /api/report/semantic-differences — return the fixed semantic differences list
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, CompatMode, OverflowPolicy, TargetModel
from cpp2py.reporting.fidelity import (
    build_translation_fidelity_report,
    FIXED_SEMANTIC_DIFFERENCES,
    DISCLAIMER,
)

router = APIRouter(tags=["reporting"])

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cpp2py-report-")
_MAX_SOURCE_BYTES = 256 * 1024


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class FidelityRequest(BaseModel):
    source_code: str = Field(..., description="C++ source code")
    filename: str = Field("input.cpp", description="Logical filename")
    compat: str = Field("range_guided")
    overflow: str = Field("assume_no_overflow")

    @field_validator("source_code")
    @classmethod
    def _check_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _MAX_SOURCE_BYTES:
            raise ValueError(f"source_code exceeds {_MAX_SOURCE_BYTES} bytes")
        return v


class SemanticDifferencesResponse(BaseModel):
    phase: str = "Phase 7 — Fidelity Reporting"
    differences: list[str]
    disclaimer: str
    limitations: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_config(compat: str, overflow: str) -> CompilerConfig:
    target = TargetModel(overflow_policy=OverflowPolicy(overflow))
    return CompilerConfig(target=target, compat_mode=CompatMode(compat))


def _generate_fidelity(source_code: str, filename: str, config: CompilerConfig) -> dict[str, Any]:
    result = compile_source(source_code, filename, config)
    report = build_translation_fidelity_report(source_code, filename, config, result)
    return report.to_dict()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/report/semantic-differences", response_model=SemanticDifferencesResponse)
def semantic_differences() -> SemanticDifferencesResponse:
    """Return known semantic differences between C++ and generated Python."""
    return SemanticDifferencesResponse(
        differences=FIXED_SEMANTIC_DIFFERENCES,
        disclaimer=DISCLAIMER,
        limitations="See docs/LIMITATIONS.md for the complete specification.",
    )


@router.post("/report/fidelity")
async def fidelity_report(req: FidelityRequest) -> dict[str, Any]:
    """
    Generate a Phase 7 fidelity report for the given C++ source.

    Translates the source with the compiler and returns structured fidelity
    data including helper counts, risks, operation counts, and assumptions.
    """
    if not req.source_code.strip():
        raise HTTPException(status_code=422, detail="source_code must not be empty")

    try:
        config = _build_config(req.compat, req.overflow)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    loop = asyncio.get_event_loop()
    try:
        report_dict = await loop.run_in_executor(
            _EXECUTOR,
            _generate_fidelity,
            req.source_code,
            req.filename,
            config,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Fidelity report generation failed. See server logs.",
        ) from exc

    return report_dict
