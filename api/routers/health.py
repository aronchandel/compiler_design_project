from __future__ import annotations

import time

import cpp2py
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])

_START_TIME = time.time()

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    uptime_seconds: float

@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="cpp2py",
        version=cpp2py.__version__,
        uptime_seconds=round(time.time() - _START_TIME, 2),
    )
