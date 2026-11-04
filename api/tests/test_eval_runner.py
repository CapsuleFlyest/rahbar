"""The eval runner is part of the CI gate, so its scoring and retry logic are tested too."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

_PATH = Path(__file__).resolve().parents[2] / "eval" / "run_eval.py"
_spec = importlib.util.spec_from_file_location("run_eval", _PATH)
assert _spec and _spec.loader
run_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_eval)

GOOD = {"answer": "DC 15.", "answered_from_context": True, "citations": [], "retrieved": []}
FALLBACK = {"answer": run_eval.FALLBACK_MARKER + " just now.", "answered_from_context": False,
            "citations": [], "retrieved": []}


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waits: list[float] = []
    monkeypatch.setattr(run_eval.time, "sleep", waits.append)
    return waits


def _client(responses: list[httpx.Response]) -> httpx.Client:
    queue = list(responses)
    return httpx.Client(transport=httpx.MockTransport(lambda request: queue.pop(0)))


def test_ask_retries_a_429_and_honours_retry_after(no_waiting: list[float]) -> None:
    client = _client([httpx.Response(429, headers={"Retry-After": "40"}),
                      httpx.Response(200, json=GOOD)])
    result = run_eval.ask(client, "http://api", "q?", retries=2, retry_wait=1.0)
    assert result["answer"] == "DC 15." and result["fallback"] is False
    assert no_waiting == [40.0]


def test_ask_retries_a_fallback_answer_until_a_real_one_arrives() -> None:
    client = _client([httpx.Response(200, json=FALLBACK), httpx.Response(200, json=GOOD)])
    assert run_eval.ask(client, "http://api", "q?", retries=2, retry_wait=1.0)["fallback"] is False


def test_ask_flags_a_fallback_that_never_goes_away() -> None:
    client = _client([httpx.Response(200, json=FALLBACK)] * 3)
    assert run_eval.ask(client, "http://api", "q?", retries=2, retry_wait=1.0)["fallback"] is True


def test_a_fallback_is_not_an_honest_abstention() -> None:
    honest = dict(GOOD, answered_from_context=False)
    rows = [
        {"id": "a", "type": "abstain", "must_abstain": True, "relevant": [], "response": honest},
        {"id": "b", "type": "abstain", "must_abstain": True, "relevant": [],
         "response": dict(FALLBACK, fallback=True)},
    ]
    results = run_eval.summarise(rows)
    assert results["abstention_correctness"] == 0.5 and results["fallback_answers"] == 1
    assert run_eval.gate(results, None)      # the gate fails: 50% < 100%


def test_recall_and_citation_validity_and_gate() -> None:
    retrieved = [{"source": "A.pdf", "section": "Hide [Action]"},
                 {"source": "A.pdf", "section": "Help"}]
    relevant = [{"source": "a.pdf", "section": "Hide"}, {"source": "a.pdf", "section": "Grapple"}]
    assert run_eval.recall_at_k(relevant, retrieved, 5) == 0.5
    assert run_eval.recall_at_k([], retrieved, 5) is None
    ok = {"citations": [{"source": "A.pdf", "section": "Help"}], "retrieved": retrieved}
    bad = {"citations": [{"source": "A.pdf", "section": "Invented"}], "retrieved": retrieved}
    assert run_eval.citation_validity(ok) == 1.0 and run_eval.citation_validity(bad) == 0.0
    baseline = {"recall_at_5": 0.9}
    assert run_eval.gate({"recall_at_5": 0.80, "citation_validity": 1.0}, baseline)
    assert not run_eval.gate({"recall_at_5": 0.86, "citation_validity": 1.0}, baseline)
