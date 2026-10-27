from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["difftest"])

class DifftestStatusResponse(BaseModel):
    phase: str = "Phase 6 — Differential Testing"
    cxx_available: bool
    compiler: str | None
    compiler_version: str | None
    message: str

class DifftestRunRequest(BaseModel):
    suite: str = Field("curated", description="Suite to run: curated | generated")
    compat: str = Field("range_guided", description="Compat mode: naive | always | range_guided")
    overflow: str = Field("assume_no_overflow", description="Overflow policy")
    count: int = Field(10, ge=1, le=50, description="Number of programs (generated suite only)")
    seed: int = Field(1, description="Random seed (generated suite only)")

class DifftestRunResponse(BaseModel):
    available: bool
    message: str
    suite: str | None = None
    total_runs: int | None = None
    agreement_rate: float | None = None
    counts: dict[str, int] | None = None
    has_mismatches: bool | None = None
    error: str | None = None

@router.get("/difftest/status", response_model=DifftestStatusResponse)
def difftest_status() -> DifftestStatusResponse:
    from cpp2py.testing.cxx_runner import probe_cxx_capabilities
    caps = probe_cxx_capabilities()
    if caps.available:
        msg = f"Differential testing available — {caps.compiler} {caps.version or ''}"
    else:
        msg = "g++ not found; differential testing requires a C++ compiler. Install g++ to enable."
    return DifftestStatusResponse(
        cxx_available=caps.available,
        compiler=caps.compiler if caps.available else None,
        compiler_version=caps.version if caps.available else None,
        message=msg,
    )

@router.post("/difftest/run", response_model=DifftestRunResponse)
def difftest_run(req: DifftestRunRequest) -> DifftestRunResponse:
    from cpp2py.testing.cxx_runner import probe_cxx_capabilities
    caps = probe_cxx_capabilities()
    if not caps.available:
        return DifftestRunResponse(
            available=False,
            message="g++ not available on this server. Differential testing cannot run.",
        )

    allowed_suites = {"curated", "generated"}
    if req.suite not in allowed_suites:
        raise HTTPException(status_code=422, detail=f"suite must be one of {sorted(allowed_suites)}")

    allowed_compat = {"naive", "always", "range_guided"}
    if req.compat not in allowed_compat:
        raise HTTPException(status_code=422, detail=f"compat must be one of {sorted(allowed_compat)}")

    try:
        from cpp2py.testing.difftest import run_suite
        summary = run_suite(
            suite=req.suite,
            seed=req.seed,
            count=req.count,
            compat_mode=req.compat,
            overflow_policy=req.overflow,
            timeout=10.0,
            out_dir=None,
        )

        counts = {k.value: v for k, v in summary.counts.items()}

        return DifftestRunResponse(
            available=True,
            message="Differential test suite completed.",
            suite=req.suite,
            total_runs=summary.total_runs,
            agreement_rate=summary.agreement_rate,
            counts=counts,
            has_mismatches=summary.has_mismatches(),
        )
    except Exception as exc:
        return DifftestRunResponse(
            available=True,
            message="Differential test suite encountered an error.",
            error=str(exc)[:200],
        )
