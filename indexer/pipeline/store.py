"""Stage 5: Store. The only code in the whole system that writes to Chroma."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import IndexerSettings
from .models import Chunk

BATCH = 100


def get_client(settings: IndexerSettings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                               settings=ChromaSettings(anonymized_telemetry=False))


def _log(msg: str, **fields: object) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "logger": "rahbar.indexer.store", "msg": msg, **fields}), flush=True)


def collection_metadata(chunks: list[Chunk], dimension: int,
                        settings: IndexerSettings) -> dict[str, str | int | float | bool]:
    """The pin and provenance the API reads at startup (section 4.4)."""
    return {
        "hnsw:space": "cosine",
        "embed_model": settings.embed_model,
        "dimension": dimension,
        "index_id": uuid.uuid4().hex,   # new on every run: the API's cache keys on it
        "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chunk_count": len(chunks),
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "chunk_strategy": settings.chunk_strategy,
    }


def _get_existing(client: Any, name: str) -> Any | None:
    try:
        return client.get_collection(name)
    except Exception:  # Chroma raises when the collection does not exist
        return None


def _add_batches(collection: Any, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    for start in range(0, len(chunks), BATCH):
        part = chunks[start:start + BATCH]
        collection.upsert(
            ids=[c.id for c in part],
            documents=[c.text for c in part],
            embeddings=vectors[start:start + BATCH],
            metadatas=[c.metadata() for c in part],
        )


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings,
          client: Any | None = None) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model
    and vector dimension in the collection metadata (section 4.4). Return the count.

    Decision (ADR 0001): while the API is serving from the collection we never
    delete-then-add. If the pin (embed_model, dimension) is unchanged we upsert the new
    chunks, then delete the ids that are no longer in the corpus (prune), then refresh the
    collection metadata, so the collection is never empty and the API's /readyz never
    flips. Only when the pin changes (vectors from two models are not comparable, and the
    dimension may differ) do we delete and recreate; readiness drops until it finishes,
    which is the correct behaviour for an index nobody can query correctly."""
    if not chunks:
        raise ValueError("refusing to store an empty index: no chunks")
    if len(chunks) != len(vectors):
        raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
    dimension = len(vectors[0])
    if any(len(v) != dimension for v in vectors):
        raise ValueError("vectors have inconsistent dimensions")
    ids = [c.id for c in chunks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate chunk ids: ids must be unique across the corpus")

    client = client or get_client(settings)
    metadata = collection_metadata(chunks, dimension, settings)
    existing = _get_existing(client, settings.collection)

    if existing is None:
        collection = client.create_collection(name=settings.collection, metadata=metadata)
        _add_batches(collection, chunks, vectors)
        _log("created collection", collection=settings.collection, chunks=len(chunks))
        return int(collection.count())

    old = existing.metadata or {}
    if old.get("embed_model") != settings.embed_model or old.get("dimension") != dimension:
        _log("embedding pin changed: recreating collection; the API will be not-ready "
             "until this finishes", old_model=old.get("embed_model"),
             old_dimension=old.get("dimension"), new_model=settings.embed_model,
             new_dimension=dimension)
        client.delete_collection(settings.collection)
        collection = client.create_collection(name=settings.collection, metadata=metadata)
        _add_batches(collection, chunks, vectors)
        return int(collection.count())

    _add_batches(existing, chunks, vectors)
    keep = set(ids)
    stale = [i for i in existing.get(include=[])["ids"] if i not in keep]
    for start in range(0, len(stale), BATCH):
        existing.delete(ids=stale[start:start + BATCH])
    existing.modify(metadata=metadata)
    _log("updated collection", collection=settings.collection, chunks=len(chunks),
         pruned=len(stale))
    return int(existing.count())
