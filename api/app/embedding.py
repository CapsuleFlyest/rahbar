"""Question embedding through Ollama (section 3.2, step 3).

The indexer embeds chunks with the same model name (the pin, section 4.4). Models of the
nomic family are trained with task prefixes: documents get "search_document: ", queries get
"search_query: ". The indexer applies the first, this module applies the second.
"""

from __future__ import annotations

import httpx


class EmbeddingError(Exception):
    """The embedding backend was unreachable or answered with something unusable."""


def query_prefix(model: str) -> str:
    return "search_query: " if model.lower().startswith("nomic") else ""


class Embedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._transport = transport

    def embed_query(self, text: str) -> list[float]:
        payload = {"model": self.model, "input": [query_prefix(self.model) + text]}
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(f"{self.base_url}/api/embed", json=payload)
                response.raise_for_status()
                vectors = response.json()["embeddings"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise EmbeddingError(f"embedding call failed: {type(exc).__name__}: {exc}") from exc
        if not vectors or not vectors[0]:
            raise EmbeddingError("embedding backend returned no vector")
        return [float(x) for x in vectors[0]]
