"""chunk, embed, store and the end-to-end run, with fake Chroma and a fake embedding server."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from tests.fakes import FakeClient

from pipeline import embed as embed_module
from pipeline import run as run_module
from pipeline.chunk import amplification, chunk, count_tokens
from pipeline.config import IndexerSettings, get_settings
from pipeline.embed import embed
from pipeline.models import Chunk, Document, Page
from pipeline.store import store

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def make_doc(text: str, source: str = "rules.md", superseded: bool = False) -> Document:
    return Document(source=source, doc_version="2026", superseded=superseded,
                    pages=[Page(source=source, page=1, text=text)])


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


# ---------------------------------------------------------------- chunk
def test_chunks_respect_the_size_budget_and_keep_metadata() -> None:
    text = "## 1. Attendance\n\n" + "\n\n".join(words(30, f"p{i}x") for i in range(10))
    chunks = chunk(make_doc(text, superseded=True), size=80, overlap=10)
    assert len(chunks) > 1
    for c in chunks:
        assert count_tokens(c.text) <= 80 + 12          # budget plus the overlap carried in
        assert (c.source, c.section, c.doc_version, c.superseded) == (
            "rules.md", "1. Attendance", "2026", True)
        assert c.page == 1


def test_sections_are_never_merged_across_a_heading() -> None:
    text = "## 1. Attendance\n\nattend 80 percent\n\n## 2. Academic warning\n\nCGPA below 2.00"
    chunks = chunk(make_doc(text), size=200, overlap=20)
    assert [c.section for c in chunks] == ["1. Attendance", "2. Academic warning"]
    assert "CGPA" not in chunks[0].text and "attend 80" not in chunks[1].text


def test_neighbouring_chunks_in_one_section_share_overlap_words() -> None:
    text = "## Rules\n\n" + words(300)
    chunks = chunk(make_doc(text), size=100, overlap=20)
    first_tail = set(chunks[0].text.split()[-20:])
    assert len(first_tail & set(chunks[1].text.split())) >= 15


def test_a_definition_shorter_than_the_budget_is_not_cut_in_half() -> None:
    definition = "Grapple. " + words(120)
    chunks = chunk(make_doc(f"## Conditions\n\n{definition}"), size=400, overlap=40)
    assert len(chunks) == 1 and definition in chunks[0].text


def test_table_rows_stay_together_and_split_with_the_header_repeated() -> None:
    rows = "\n".join(f"| Item{i} | {i} gp |" for i in range(60))
    table = "| Item | Cost |\n| --- | --- |\n" + rows
    chunks = chunk(make_doc(f"## Armor\n\n{table}"), size=60, overlap=0)
    assert len(chunks) > 1
    assert all("| Item | Cost |" in c.text for c in chunks)


def test_chunk_ids_are_stable_and_unique() -> None:
    doc = make_doc("## A\n\n" + words(500))
    first = [c.id for c in chunk(doc, 100, 10)]
    assert first == [c.id for c in chunk(doc, 100, 10)]
    assert len(set(first)) == len(first)


def test_fixed_strategy_cuts_plain_windows() -> None:
    doc = make_doc("## A\n\n" + words(250))
    chunks = chunk(doc, size=100, overlap=0, strategy="fixed")
    assert len(chunks) >= 3 and all(count_tokens(c.text) <= 101 for c in chunks)


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValueError):
        chunk(make_doc("## A\n\ntext"), size=50, overlap=50)


def test_amplification_is_stored_words_over_original_words() -> None:
    doc = make_doc("## A\n\n" + words(300))
    chunks = chunk(doc, 100, 20)
    assert amplification(doc, chunks) > 1.0


# ---------------------------------------------------------------- embed
def settings(**overrides: object) -> IndexerSettings:
    return replace(get_settings(), embed_model="nomic-embed-text",
                   ollama_url="http://ollama.test", embed_batch_size=2, **overrides)  # type: ignore[arg-type]


def test_embed_batches_and_prefixes_documents_for_nomic() -> None:
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)["input"]
        calls.append(batch)
        return httpx.Response(200, json={"embeddings": [[1.0, 2.0] for _ in batch]})

    vectors = embed(["a", "b", "c"], settings(), transport=httpx.MockTransport(handler))
    assert len(vectors) == 3 and [len(c) for c in calls] == [2, 1]
    assert calls[0][0] == "search_document: a"


def test_embed_without_prefix_for_other_models() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.extend(json.loads(request.content)["input"])
        return httpx.Response(200, json={"embeddings": [[1.0]]})

    other = replace(settings(), embed_model="mxbai-embed-large")
    embed(["a"], other, transport=httpx.MockTransport(handler))
    assert seen == ["a"]


def test_embed_detects_a_vector_count_mismatch() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"embeddings": [[1.0]]}))
    with pytest.raises(RuntimeError, match="mismatch"):
        embed(["a", "b"], settings(), transport=transport)


def test_embed_retries_a_server_error_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embed_module.time, "sleep", lambda s: None)
    answers = [httpx.Response(500), httpx.Response(200, json={"embeddings": [[1.0, 2.0]]})]
    transport = httpx.MockTransport(lambda r: answers.pop(0))
    assert embed(["a"], settings(), transport=transport) == [[1.0, 2.0]]


def test_embed_gives_up_after_repeated_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embed_module.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="failed after"):
        embed(["a"], settings(), transport=httpx.MockTransport(lambda r: httpx.Response(503)))


# ---------------------------------------------------------------- store
def chunks_for(*ids: str) -> list[Chunk]:
    return [Chunk(id=i, text=f"text {i}", source="s.md", section="1", page=1,
                  doc_version="2026", superseded=False) for i in ids]


def test_store_records_the_pin_in_collection_metadata() -> None:
    client = FakeClient()
    assert store(chunks_for("a", "b"), [[1.0, 0.0], [0.0, 1.0]], settings(), client) == 2
    meta = client.collections["rahbar"].metadata
    assert meta["embed_model"] == "nomic-embed-text" and meta["dimension"] == 2
    assert meta["hnsw:space"] == "cosine" and meta["index_id"] and meta["chunk_count"] == 2


def test_reindex_with_the_same_pin_upserts_and_prunes_without_deleting() -> None:
    client = FakeClient()
    store(chunks_for("a", "b", "c"), [[1.0, 0.0]] * 3, settings(), client)
    first_id = client.collections["rahbar"].metadata["index_id"]
    store(chunks_for("b", "c", "d"), [[1.0, 0.0]] * 3, settings(), client)
    collection = client.collections["rahbar"]
    assert sorted(collection.rows) == ["b", "c", "d"]
    assert client.deleted == []                         # never emptied while the API serves
    assert collection.metadata["index_id"] != first_id  # the API's cache generation moves on


def test_changing_the_embedding_model_recreates_the_collection() -> None:
    client = FakeClient()
    store(chunks_for("a"), [[1.0, 0.0]], settings(), client)
    other = replace(settings(), embed_model="mxbai-embed-large")
    store(chunks_for("a"), [[1.0, 0.0, 0.0]], other, client)
    assert client.deleted == ["rahbar"]
    assert client.collections["rahbar"].metadata["embed_model"] == "mxbai-embed-large"


@pytest.mark.parametrize(("chunks", "vectors"), [
    ([], []), (chunks_for("a"), []), (chunks_for("a", "a"), [[1.0], [1.0]]),
    (chunks_for("a", "b"), [[1.0], [1.0, 2.0]])])
def test_store_refuses_bad_input(chunks: list[Chunk], vectors: list[list[float]]) -> None:
    with pytest.raises(ValueError):
        store(chunks, vectors, settings(), FakeClient())


# ---------------------------------------------------------------- end to end on the fixtures
def test_run_pipeline_indexes_the_fixture_corpus_with_correct_flags(
        monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_embed(texts: list[str], _settings: IndexerSettings) -> list[list[float]]:
        return [[float(len(t) % 7), 1.0] for t in texts]

    monkeypatch.setattr("pipeline.embed.embed", fake_embed)
    client = FakeClient()
    cfg = replace(get_settings(), corpus_dir=str(FIXTURES), embed_model="nomic-embed-text")
    count = run_module.run_pipeline(cfg, client)
    rows = client.collections[cfg.collection].rows
    assert count == len(rows) > 5
    flags = {m["source"]: m["superseded"] for _, _, m in rows.values()}
    assert flags and any(flags.values()) and not all(flags.values())  # one old, one current
    assert all(m["section"] for _, _, m in rows.values())
