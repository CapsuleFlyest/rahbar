"""Semantic cache over Redis (section 3.3). Defended in docs/adr/0003.

Entries are keyed by the index *generation_id* (the indexer's `index_id`). A re-index writes
a new id, so every old entry becomes unreachable at once: that is the invalidation, with no
extra network path from the indexer to Redis. The TTL then reclaims the old namespace.

Never cached: follow-ups, abstentions, anything that failed validation (see should_cache).
Redis trouble never breaks answering: errors are logged and treated as a miss.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from collections.abc import Callable
from typing import Any

log = logging.getLogger("rahbar.cache")

KEY_PREFIX = "rahbar:cache"


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def should_cache(answered_from_context: bool, fallback_reason: str | None, followup: bool) -> bool:
    """A cached mistake is served to everyone, so cache only clean, grounded answers."""
    return answered_from_context and fallback_reason is None and not followup


class SemanticCache:
    def __init__(
        self,
        client: Any,
        threshold: float,
        ttl_seconds: int,
        generation_id: Callable[[], str],
    ) -> None:
        self.client = client
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self._generation_id = generation_id

    def _namespace(self) -> str:
        return f"{KEY_PREFIX}:{self._generation_id()}"

    def lookup(self, vector: list[float], include_superseded: bool) -> dict[str, Any] | None:
        """Best cached response with cosine similarity >= threshold, or None."""
        try:
            best_score, best = 0.0, None
            for key in self.client.scan_iter(match=f"{self._namespace()}:*", count=200):
                raw = self.client.get(key)
                if not raw:
                    continue
                entry = json.loads(raw)
                if entry.get("include_superseded") != include_superseded:
                    continue
                score = cosine(vector, entry["embedding"])
                if score >= self.threshold and score > best_score:
                    best_score, best = score, entry["response"]
            return best
        except Exception as exc:    # Redis down, bad entry: a miss, never an error
            log.warning("cache lookup failed", extra={"error": type(exc).__name__})
            return None

    def store(
        self, vector: list[float], include_superseded: bool, response: dict[str, Any]
    ) -> None:
        try:
            entry = {"embedding": vector, "include_superseded": include_superseded,
                     "response": response}
            self.client.set(f"{self._namespace()}:{uuid.uuid4().hex}", json.dumps(entry),
                            ex=self.ttl_seconds)
        except Exception as exc:
            log.warning("cache store failed", extra={"error": type(exc).__name__})
