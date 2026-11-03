"""The retriever interface. The rest of the API only ever sees this."""

from __future__ import annotations

from typing import Any, Protocol

from ..schemas import Passage


class Retriever(Protocol):
    name: str

    def embed_query(self, question: str) -> list[float] | None:
        """Embed the question with the pinned model, or None when there is no embedding
        (the stub). The vector is reused for the cache lookup and the retrieval."""
        ...

    def retrieve(
        self,
        question: str,
        k: int,
        vector: list[float] | None = None,
        include_superseded: bool = False,
    ) -> list[Passage]:
        """Return up to k passages, best first. Superseded documents are excluded
        unless include_superseded is set (the user asked about an older version)."""
        ...

    def index_info(self) -> dict[str, Any]:
        """Identity of the index being served; `index_id` changes on every re-index."""
        ...
