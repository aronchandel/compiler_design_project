"""
cpp2py FastAPI backend.

Exposes the cpp2py compiler and Phase 6/7 features over HTTP.
Invokes the real compiler; never fabricates results.
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import cpp2py
from api.routers import translate, difftest, reporting, health

# ---------------------------------------------------------------------------
# CORS origins – configure via FRONTEND_ORIGIN env-var
# ---------------------------------------------------------------------------
_FRONTEND_ORIGIN = os.environ.get(
    "FRONTEND_ORIGIN", "http://localhost:5173"
)
_ALLOWED_ORIGINS = [
    _FRONTEND_ORIGIN,
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    # Also allow null origin (opening file:// in browser)
    "null",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    yield


app = FastAPI(
    title="cpp2py API",
    description="REST API for the cpp2py C++ → Python translator",
    version=cpp2py.__version__,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"https?://localhost(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health.router, prefix="/api")
app.include_router(translate.router, prefix="/api")
app.include_router(difftest.router, prefix="/api")
app.include_router(reporting.router, prefix="/api")

# ---------------------------------------------------------------------------
# Serve the Stitch-generated frontend as static files from /app
# ---------------------------------------------------------------------------
_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")


# ---------------------------------------------------------------------------
# Global exception handler – never leak internal paths or tracebacks
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. See server logs for details.",
        },
    )
