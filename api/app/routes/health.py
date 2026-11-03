"""Liveness and readiness (section 4.3). They answer different questions."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import readiness

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request) -> JSONResponse:
    """200 only when Chroma, a non-empty collection, Redis and the embedding pin are OK."""
    ok, checks, failures = readiness.evaluate(request.app.state)
    if ok:
        return JSONResponse({"status": "ready", "checks": checks})
    return JSONResponse(status_code=503,
                        content={"status": "not ready", "checks": checks, "failed": failures})
