"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

import time

import httpx

from .config import IndexerSettings

DOC_PREFIX = "search_document: "   # the API prefixes questions with "search_query: "
TIMEOUT_SECONDS = 120.0
ATTEMPTS = 3


def uses_prefix(model: str) -> bool:
    return model.lower().startswith("nomic")


def embedding_dimension(vectors: list[list[float]]) -> int:
    if not vectors:
        raise ValueError("no vectors")
    return len(vectors[0])


def _post_batch(client: httpx.Client, url: str, model: str, batch: list[str]) -> list[list[float]]:
    reason = ""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = client.post(url, json={"model": model, "input": batch})
            if response.status_code < 500:
                response.raise_for_status()
                return list(response.json()["embeddings"])
            reason = f"HTTP {response.status_code}"
        except httpx.TransportError as exc:
            reason = type(exc).__name__
        if attempt < ATTEMPTS:
            time.sleep(min(2.0 ** attempt, 8.0))
    raise RuntimeError(f"embedding request to {url} failed after {ATTEMPTS} attempts: {reason}")


def embed(texts: list[str], settings: IndexerSettings, *,
          transport: httpx.BaseTransport | None = None) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else.

    With Ollama: POST {ollama_url}/api/embed with {"model": ..., "input": [texts]}
    returns {"embeddings": [[...], ...]}. Calls are batched (EMBED_BATCH_SIZE). Nomic
    models get the document prefix they were trained with."""
    if not texts:
        return []
    inputs = [DOC_PREFIX + t for t in texts] if uses_prefix(settings.embed_model) else list(texts)
    url = settings.ollama_url.rstrip("/") + "/api/embed"
    batch_size = max(1, settings.embed_batch_size)
    vectors: list[list[float]] = []
    with httpx.Client(timeout=TIMEOUT_SECONDS, transport=transport) as client:
        for start in range(0, len(inputs), batch_size):
            batch = inputs[start:start + batch_size]
            got = _post_batch(client, url, settings.embed_model, batch)
            if len(got) != len(batch):
                raise RuntimeError(
                    f"embedding count mismatch: sent {len(batch)} texts, got {len(got)} vectors")
            vectors.extend(got)
    dim = len(vectors[0])
    if dim == 0 or any(len(v) != dim for v in vectors):
        raise RuntimeError("embedding dimension is inconsistent across vectors")
    return vectors
