"""The real retriever (sections 3.2 and 4.4). It only ever READS the collection.

The indexer Job is the only writer. This class has no add/upsert/delete call on purpose.
"""

from __future__ import annotations

import time
from typing import Any

from ..config import Settings
from ..embedding import Embedder
from ..schemas import Passage

INDEX_INFO_TTL_SECONDS = 15.0


class ChromaInspector:
    """Read-only view of the collection: heartbeat, metadata and size. Readiness uses it
    on its own, so the probe works even while RETRIEVER=stub (week 1)."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        if client is None:
            import chromadb  # the thin client, from chromadb-client in requirements.txt
            from chromadb.config import Settings as ChromaSettings

            client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        self.client = client

    def heartbeat(self) -> None:
        self.client.heartbeat()

    def _collection(self) -> Any:
        return self.client.get_collection(self.settings.collection)

    def get_collection_info(self) -> dict[str, Any]:
        """Collection metadata and size, for readiness and for the cache generation id."""
        collection = self._collection()
        return {"metadata": dict(collection.metadata or {}), "count": int(collection.count())}


class ChromaRetriever(ChromaInspector):
    name = "chroma"

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        super().__init__(settings, client)
        self.embedder = embedder or Embedder(
            settings.ollama_url, settings.embed_model, timeout=settings.llm_timeout_seconds
        )
        self._info: dict[str, Any] = {}
        self._info_at = 0.0

    def embed_query(self, question: str) -> list[float] | None:
        return self.embedder.embed_query(question)

    def index_info(self) -> dict[str, Any]:
        """The index generation being served. Cached for a few seconds so the cache lookup
        does not add a Chroma round trip to every question."""
        now = time.monotonic()
        if not self._info or now - self._info_at > INDEX_INFO_TTL_SECONDS:
            metadata = self.get_collection_info()["metadata"]
            self._info = {"index_id": str(metadata.get("index_id", "unknown")), **metadata}
            self._info_at = now
        return self._info

    def retrieve(
        self,
        question: str,
        k: int,
        vector: list[float] | None = None,
        include_superseded: bool = False,
    ) -> list[Passage]:
        if vector is None:
            vector = self.embed_query(question)
        where = None if include_superseded else {"superseded": False}
        result = self._collection().query(
            query_embeddings=[vector],
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        passages: list[Passage] = []
        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances):
            meta = meta or {}
            page = meta.get("page")
            passages.append(
                Passage(
                    chunk_id=str(chunk_id),
                    text=text or "",
                    source=str(meta.get("source", "unknown")),
                    section=str(meta.get("section", "")),
                    page=int(page) if page is not None else None,
                    score=1.0 - float(distance),   # Chroma returns cosine distance
                )
            )
        passages.sort(key=lambda p: p.score, reverse=True)
        return passages
