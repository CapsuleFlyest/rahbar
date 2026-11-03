"""The API process. It reads the index; it never builds it (section 4.2).

Run locally with stubs:   make dev     (then open http://localhost:8000)
Run in the container:     uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from . import readiness
from .config import Settings, get_settings
from .logjson import configure_logging, request_id_var
from .providers.llm import get_provider
from .retrieval import get_retriever
from .routes import ask, health, metrics
from .services.cache import SemanticCache

log = logging.getLogger("rahbar.api")


def _build_redis(settings: Settings) -> Any:
    import redis

    return redis.Redis(host=settings.redis_host, port=settings.redis_port, db=0,
                       decode_responses=True, socket_timeout=2, socket_connect_timeout=2)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    app.state.retriever = get_retriever(settings)
    app.state.provider = get_provider(settings)
    # Read-only handles for readiness and the cache. This process never indexes (4.2):
    # the indexer Job is the only writer.
    app.state.chroma = None
    app.state.redis = None
    app.state.cache = None
    checks_on = readiness.checks_enabled(settings)
    if checks_on or (settings.cache_enabled and settings.retriever == "chroma"):
        app.state.redis = _build_redis(settings)
    if checks_on:
        from .retrieval.chroma import ChromaInspector

        app.state.chroma = ChromaInspector(settings)
    if settings.cache_enabled and settings.retriever == "chroma":
        retriever = app.state.retriever
        app.state.cache = SemanticCache(
            app.state.redis, settings.cache_threshold, settings.cache_ttl_seconds,
            generation_id=lambda: str(retriever.index_info().get("index_id", "unknown")),
        )
    log.info(
        "api started",
        extra={"retriever": settings.retriever, "llm_provider": settings.llm_provider,
               "embed_model": settings.embed_model, "top_k": settings.top_k,
               "relevance_floor": settings.relevance_floor, "temperature": settings.temperature,
               "cache": app.state.cache is not None, "ready_checks": checks_on},
    )
    if checks_on:
        # Log the embedding-pin verdict once at startup; /readyz repeats it on every probe.
        ok, _checks, failures = readiness.evaluate(app.state)
        log.info("startup readiness", extra={"ready": ok, "failures": failures})
    yield


app = FastAPI(title="RAHBAR API", lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_var.set(rid)
    start = time.perf_counter()
    status = 500
    metrics.INFLIGHT.inc()
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")   # route template, not the raw URL
        elapsed = time.perf_counter() - start
        metrics.REQUESTS.labels(path=path, status=str(status)).inc()
        metrics.LATENCY.labels(path=path).observe(elapsed)
        if path not in ("/healthz", "/readyz", "/metrics"):
            log.info("request", extra={"path": path, "status": status,
                                       "ms": round(elapsed * 1000, 1)})
        metrics.INFLIGHT.dec()
        request_id_var.reset(token)


app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(ask.router)

# Development only: `make dev` serves the chat UI from this process, so you can try it
# without a cluster. On Kubernetes the ui Deployment serves it and this stays unset.
_ui_dir = os.environ.get("SERVE_UI_DIR")
if _ui_dir:
    app.mount("/", StaticFiles(directory=_ui_dir, html=True), name="ui")
