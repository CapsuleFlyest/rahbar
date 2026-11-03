"""In-memory stand-ins for the Chroma client and collection."""

from __future__ import annotations

from typing import Any


class FakeCollection:
    def __init__(self, name: str, metadata: dict[str, Any]) -> None:
        self.name, self.metadata, self.rows = name, dict(metadata), {}

    def add(self, ids, documents, embeddings, metadatas) -> None:  # type: ignore[no-untyped-def]
        self.upsert(ids, documents, embeddings, metadatas)

    def upsert(self, ids, documents, embeddings, metadatas) -> None:  # type: ignore[no-untyped-def]
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, e, m)

    def get(self, include=None) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        return {"ids": list(self.rows)}

    def delete(self, ids) -> None:  # type: ignore[no-untyped-def]
        for i in ids:
            self.rows.pop(i, None)

    def modify(self, metadata=None, name=None) -> None:  # type: ignore[no-untyped-def]
        if metadata is not None:
            self.metadata = dict(metadata)

    def count(self) -> int:
        return len(self.rows)


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}
        self.deleted: list[str] = []

    def heartbeat(self) -> int:
        return 1

    def get_collection(self, name: str) -> FakeCollection:
        if name not in self.collections:
            raise ValueError(f"Collection {name} does not exist")
        return self.collections[name]

    def delete_collection(self, name: str) -> None:
        if name not in self.collections:
            raise ValueError("no such collection")
        self.deleted.append(name)
        del self.collections[name]

    def create_collection(self, name: str, metadata: dict[str, Any]) -> FakeCollection:
        self.collections[name] = FakeCollection(name, metadata)
        return self.collections[name]
