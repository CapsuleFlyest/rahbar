"""Shared fakes: no network, no model, no Redis, no Chroma."""

from __future__ import annotations

import fnmatch
from typing import Any

import pytest

from app.config import Settings
from app.providers.llm.base import ProviderError, Usage
from app.schemas import Answer, Citation, Passage


def make_passage(
    chunk_id: str = "c1",
    text: str = "Attendance of at least 80 percent is required.",
    source: str = "rules-2026.pdf",
    section: str = "1.21 Attendance",
    page: int | None = 4,
    score: float = 0.8,
) -> Passage:
    return Passage(chunk_id=chunk_id, text=text, source=source, section=section,
                   page=page, score=score)


def good_answer(passage: Passage | None = None, **overrides: Any) -> Answer:
    p = passage or make_passage()
    base: dict[str, Any] = {
        "reasoning": "r", "answer": "80 percent attendance is required.",
        "citations": [Citation(source=p.source, section=p.section, page=p.page)],
        "answered_from_context": True, "confidence": "high",
    }
    base.update(overrides)
    return Answer(**base)


class FakeRetriever:
    name = "fake"

    def __init__(self, passages: list[Passage], vector: list[float] | None = None,
                 index_id: str = "gen1") -> None:
        self.passages = passages
        self.vector = vector
        self.index_id = index_id
        self.calls: list[dict[str, Any]] = []

    def embed_query(self, question: str) -> list[float] | None:
        return self.vector

    def retrieve(self, question: str, k: int, vector: list[float] | None = None,
                 include_superseded: bool = False) -> list[Passage]:
        self.calls.append({"k": k, "include_superseded": include_superseded})
        return self.passages[:k]

    def index_info(self) -> dict[str, Any]:
        return {"index_id": self.index_id}


class ScriptedProvider:
    """Returns / raises each scripted item in turn; records every call."""

    name = "scripted"

    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.calls = 0
        self.prompts: list[list[Passage]] = []

    def generate(self, question: str, passages: list[Passage],
                 usage: Usage | None = None) -> Answer:
        self.calls += 1
        self.prompts.append(passages)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[no-any-return]


class FakeRedis:
    """The few Redis commands the cache and readiness use, in memory."""

    def __init__(self, fail: bool = False) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail = fail

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("redis down")

    def ping(self) -> bool:
        self._check()
        return True

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._check()
        self.data[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def get(self, key: str) -> str | None:
        self._check()
        return self.data.get(key)

    def scan_iter(self, match: str = "*", count: int = 10) -> Any:
        self._check()
        return iter([k for k in list(self.data) if fnmatch.fnmatch(k, match)])


@pytest.fixture()
def settings() -> Settings:
    return Settings(retriever="chroma", llm_provider="stub", relevance_floor=0.5,
                    cache_threshold=0.92, embed_model="nomic-embed-text")


__all__ = ["FakeRedis", "FakeRetriever", "ProviderError", "ScriptedProvider",
           "good_answer", "make_passage"]
