"""Readiness (sections 4.2-4.4): may this pod take traffic?

Ready means: Chroma reachable, the collection exists and is NON-EMPTY, Redis reachable, and
the embedding model the index was built with equals EMBED_MODEL. Anything else is a 503 that
names the failed dependency, so the pod is withheld from the Service instead of serving
empty retrievals or nonsense vectors. Liveness (/healthz) never calls any of this.

This module only reads. The indexer Job writes the index.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("rahbar.readiness")


def checks_enabled(settings: Any) -> bool:
    mode = settings.ready_checks
    if mode == "on":
        return True
    if mode == "off":
        return False
    return bool(settings.retriever == "chroma")      # auto


def pin_conflict(index_model: str | None, api_model: str) -> str | None:
    """Describe the embedding-pin conflict, or None when the index and the API agree."""
    if index_model != api_model:
        return (f"embedding model mismatch: index built with {index_model!r}, "
                f"API configured with {api_model!r} (EMBED_MODEL)")
    return None


def evaluate(state: Any) -> tuple[bool, dict[str, str], list[str]]:
    """Return (ready, per-dependency status, failure messages).

    `state` carries `settings`, `chroma` (heartbeat/get_collection_info) and `redis`."""
    settings = state.settings
    if not checks_enabled(settings):
        return True, {"dependencies": "not checked"}, []

    checks: dict[str, str] = {}
    failures: list[str] = []

    try:
        state.chroma.heartbeat()
        checks["chroma"] = "ok"
    except Exception as exc:
        checks["chroma"] = "unreachable"
        failures.append(f"chroma unreachable: {type(exc).__name__}")
    else:
        try:
            info = state.chroma.get_collection_info()
        except Exception as exc:
            checks["collection"] = "missing"
            failures.append(f"collection {settings.collection!r} not found: {type(exc).__name__}")
        else:
            if info["count"] <= 0:       # the central check of section 4.2
                checks["collection"] = "empty"
                failures.append(f"collection {settings.collection!r} is empty: run the indexer Job")
            else:
                checks["collection"] = f"ok ({info['count']} chunks)"
            conflict = pin_conflict(info["metadata"].get("embed_model"), settings.embed_model)
            if conflict:
                checks["embedding_pin"] = "mismatch"
                failures.append(conflict)
            else:
                checks["embedding_pin"] = "ok"

    try:
        if state.redis is None:
            raise RuntimeError("no redis client")
        state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = "unreachable"
        failures.append(f"redis unreachable: {type(exc).__name__}")

    for message in failures:
        log.warning("not ready", extra={"reason": message})
    return not failures, checks, failures
