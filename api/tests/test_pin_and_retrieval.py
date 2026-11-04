"""Embedding pin, readiness, retriever, Ollama provider and cache: no network, no sleeping."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from conftest import good_answer, make_passage
from pydantic import ValidationError

from app import readiness
from app.config import Settings
from app.embedding import Embedder, EmbeddingError, query_prefix
from app.providers.llm.base import ProviderError, Usage
from app.providers.llm.ollama import OllamaProvider
from app.retrieval.chroma import ChromaRetriever
from app.services.cache import SemanticCache, cosine, should_cache


# ---------------------------------------------------------------- fakes
class FakeCollection:
    def __init__(self, metadata: dict[str, Any], count: int, hits: dict[str, Any] | None = None):
        self.metadata, self._count, self.hits, self.queries = metadata, count, hits, []

    def count(self) -> int:
        return self._count

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.queries.append(kwargs)
        return self.hits or {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


class FakeChroma:
    def __init__(self, collection: FakeCollection | None, alive: bool = True) -> None:
        self.collection, self.alive = collection, alive

    def heartbeat(self) -> int:
        if not self.alive:
            raise ConnectionError("down")
        return 1

    def get_collection(self, name: str) -> FakeCollection:
        if self.collection is None:
            raise ValueError("no such collection")
        return self.collection


class FakeRedis:
    def __init__(self, fail: bool = False) -> None:
        self.data: dict[str, Any] = {}
        self.fail = fail

    def ping(self) -> bool:
        if self.fail:
            raise ConnectionError("redis down")
        return True

    def scan_iter(self, match: str, count: int = 100) -> list[str]:
        if self.fail:
            raise ConnectionError("redis down")
        prefix = match.rstrip("*")
        return [k for k in self.data if k.startswith(prefix)]

    def get(self, key: str) -> Any:
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        if self.fail:
            raise ConnectionError("redis down")
        self.data[key] = value


class InspectorAdapter:
    """What app.state.chroma looks like to readiness: heartbeat() + get_collection_info()."""

    def __init__(self, chroma: FakeChroma, name: str = "rahbar") -> None:
        self.chroma, self.name = chroma, name

    def heartbeat(self) -> None:
        self.chroma.heartbeat()

    def get_collection_info(self) -> dict[str, Any]:
        c = self.chroma.get_collection(self.name)
        return {"metadata": dict(c.metadata), "count": c.count()}


def state(chroma: FakeChroma, redis: FakeRedis | None, model: str = "nomic-embed-text",
          mode: str = "on") -> Any:
    settings = Settings(embed_model=model, ready_checks=mode, retriever="chroma")
    return SimpleNamespace(settings=settings, chroma=InspectorAdapter(chroma), redis=redis)


# ---------------------------------------------------------------- readiness / the pin
GOOD_META = {"embed_model": "nomic-embed-text", "dimension": 768, "index_id": "abc"}


def test_ready_when_chroma_collection_redis_and_pin_agree() -> None:
    ok, checks, failures = readiness.evaluate(
        state(FakeChroma(FakeCollection(GOOD_META, 12)), FakeRedis()))
    assert ok and not failures and checks["embedding_pin"] == "ok"


def test_not_ready_when_the_collection_is_empty() -> None:
    ok, checks, failures = readiness.evaluate(
        state(FakeChroma(FakeCollection(GOOD_META, 0)), FakeRedis()))
    assert not ok and checks["collection"] == "empty" and "empty" in failures[0]


def test_not_ready_when_the_collection_does_not_exist_yet() -> None:
    ok, checks, _ = readiness.evaluate(state(FakeChroma(None), FakeRedis()))
    assert not ok and checks["collection"] == "missing"


def test_not_ready_when_chroma_is_unreachable() -> None:
    ok, checks, failures = readiness.evaluate(
        state(FakeChroma(None, alive=False), FakeRedis()))
    assert not ok and checks["chroma"] == "unreachable" and "chroma unreachable" in failures[0]


def test_not_ready_when_redis_is_unreachable() -> None:
    ok, checks, _ = readiness.evaluate(
        state(FakeChroma(FakeCollection(GOOD_META, 5)), FakeRedis(fail=True)))
    assert not ok and checks["redis"] == "unreachable"


def test_embedding_model_mismatch_refuses_to_become_ready_and_names_the_conflict() -> None:
    ok, checks, failures = readiness.evaluate(
        state(FakeChroma(FakeCollection(GOOD_META, 5)), FakeRedis(), model="mxbai-embed-large"))
    assert not ok and checks["embedding_pin"] == "mismatch"
    assert "mismatch" in failures[0]
    assert "nomic-embed-text" in failures[0] and "mxbai-embed-large" in failures[0]


def test_dummy_index_agrees_with_the_dummy_pin() -> None:
    meta = {"embed_model": "dummy-768"}
    ok, _, _ = readiness.evaluate(
        state(FakeChroma(FakeCollection(meta, 3)), FakeRedis(), model="dummy-768"))
    assert ok


@pytest.mark.parametrize(("mode", "retriever", "expected"), [
    ("on", "stub", True), ("off", "chroma", False), ("auto", "chroma", True),
    ("auto", "stub", False)])
def test_ready_checks_mode(mode: str, retriever: str, expected: bool) -> None:
    assert readiness.checks_enabled(Settings(ready_checks=mode, retriever=retriever)) is expected


def test_readiness_is_trivially_ok_when_checks_are_off() -> None:
    ok, checks, _ = readiness.evaluate(
        state(FakeChroma(None, alive=False), None, mode="off"))
    assert ok and checks == {"dependencies": "not checked"}


# ---------------------------------------------------------------- embedder
def _embed_client(handler: Any) -> Embedder:
    return Embedder("http://ollama.test/", "nomic-embed-text",
                    transport=httpx.MockTransport(handler))


def test_embedder_sends_the_query_prefix_and_returns_floats() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"embeddings": [[1, 2, 3]]})

    assert _embed_client(handler).embed_query("hide dc?") == [1.0, 2.0, 3.0]
    assert seen["model"] == "nomic-embed-text"
    assert seen["input"] == ["search_query: hide dc?"]


def test_query_prefix_only_for_nomic_models() -> None:
    assert query_prefix("nomic-embed-text") and query_prefix("mxbai-embed-large") == ""


@pytest.mark.parametrize("response", [httpx.Response(500), httpx.Response(200, json={"x": 1}),
                                      httpx.Response(200, json={"embeddings": []})])
def test_embedder_failures_become_embedding_error(response: httpx.Response) -> None:
    with pytest.raises(EmbeddingError):
        _embed_client(lambda request: response).embed_query("q")


# ---------------------------------------------------------------- retriever
HITS = {"ids": [["c1", "c2"]], "documents": [["old text", "new text"]],
        "metadatas": [[{"source": "a.pdf", "section": "Hide", "page": 3},
                       {"source": "b.pdf", "section": "Help", "page": None}]],
        "distances": [[0.40, 0.10]]}


def _retriever(collection: FakeCollection) -> ChromaRetriever:
    return ChromaRetriever(Settings(), client=FakeChroma(collection), embedder=None)


def test_retriever_converts_distance_to_similarity_and_sorts() -> None:
    collection = FakeCollection(GOOD_META, 2, HITS)
    passages = _retriever(collection).retrieve("q", 2, vector=[0.1])
    assert [p.chunk_id for p in passages] == ["c2", "c1"]
    assert passages[0].score == pytest.approx(0.9) and passages[1].score == pytest.approx(0.6)
    assert passages[0].page is None and passages[1].page == 3


def test_retriever_filters_out_superseded_documents_by_default() -> None:
    collection = FakeCollection(GOOD_META, 2, HITS)
    _retriever(collection).retrieve("q", 5, vector=[0.1])
    assert collection.queries[0]["where"] == {"superseded": False}


def test_retriever_can_include_superseded_when_the_user_asks_for_old_rules() -> None:
    collection = FakeCollection(GOOD_META, 2, HITS)
    _retriever(collection).retrieve("q", 5, vector=[0.1], include_superseded=True)
    assert collection.queries[0]["where"] is None


def test_retriever_has_no_write_methods() -> None:
    for name in ("add", "upsert", "delete", "update"):
        assert not hasattr(ChromaRetriever, name)


def test_index_info_is_cached_between_calls() -> None:
    collection = FakeCollection(GOOD_META, 2)
    retriever = _retriever(collection)
    assert retriever.index_info()["index_id"] == "abc"
    collection.metadata = {**GOOD_META, "index_id": "new"}
    assert retriever.index_info()["index_id"] == "abc"      # still inside the TTL


# ---------------------------------------------------------------- ollama provider
def _ollama(handler: Any) -> OllamaProvider:
    return OllamaProvider(Settings(ollama_url="http://ollama.test", llm_model="m",
                                   temperature=0.2), transport=httpx.MockTransport(handler))


def test_ollama_sends_schema_temperature_and_records_tokens() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={
            "message": {"content": good_answer().model_dump_json()},
            "prompt_eval_count": 50, "eval_count": 7})

    usage = Usage()
    answer = _ollama(handler).generate("q?", [make_passage()], usage)
    assert answer.answered_from_context and (usage.tokens_in, usage.tokens_out) == (50, 7)
    assert seen["format"]["title"] == "Answer" and seen["options"]["temperature"] == 0.2
    assert seen["stream"] is False


def test_ollama_prose_instead_of_json_raises_validation_error() -> None:
    provider = _ollama(lambda r: httpx.Response(200, json={"message": {"content": "Sure! The DC is 15."}}))
    with pytest.raises(ValidationError):
        provider.generate("q?", [make_passage()])


def test_ollama_http_failure_becomes_provider_error() -> None:
    with pytest.raises(ProviderError):
        _ollama(lambda r: httpx.Response(503)).generate("q?", [make_passage()])


# ---------------------------------------------------------------- cache
def _cache(redis: FakeRedis, generation: list[str], threshold: float = 0.9) -> SemanticCache:
    return SemanticCache(redis, threshold, 60, lambda: generation[0])


def test_cache_hits_above_the_threshold_and_misses_below() -> None:
    redis, generation = FakeRedis(), ["g1"]
    cache = _cache(redis, generation)
    cache.store([1.0, 0.0], False, {"answer": "cached"})
    assert cache.lookup([1.0, 0.05], False) == {"answer": "cached"}
    assert cache.lookup([0.0, 1.0], False) is None


def test_cache_entries_for_old_rules_are_kept_apart() -> None:
    redis, generation = FakeRedis(), ["g1"]
    cache = _cache(redis, generation)
    cache.store([1.0, 0.0], True, {"answer": "old rules"})
    assert cache.lookup([1.0, 0.0], False) is None


def test_a_new_index_generation_invalidates_every_cached_answer() -> None:
    redis, generation = FakeRedis(), ["g1"]
    cache = _cache(redis, generation)
    cache.store([1.0, 0.0], False, {"answer": "stale"})
    generation[0] = "g2"                      # the indexer wrote a new index_id
    assert cache.lookup([1.0, 0.0], False) is None


def test_redis_failure_is_a_miss_not_an_error() -> None:
    cache = _cache(FakeRedis(fail=True), ["g1"])
    cache.store([1.0], False, {"answer": "x"})        # must not raise
    assert cache.lookup([1.0], False) is None


def test_should_cache_never_caches_followups_abstentions_or_fallbacks() -> None:
    assert should_cache(True, None, False)
    assert not should_cache(False, None, False)       # abstention
    assert not should_cache(True, "invalid_model_output", False)
    assert not should_cache(True, None, True)         # follow-up


def test_cosine_handles_degenerate_vectors() -> None:
    assert cosine([], []) == 0.0 and cosine([0, 0], [1, 1]) == 0.0 and cosine([1], [1, 2]) == 0.0
