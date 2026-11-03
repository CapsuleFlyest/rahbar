from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.providers.llm.base import ProviderError
from app.schemas import Answer, Citation
from app.services.grounding import (
    FALLBACK_MESSAGE,
    abstention_answer,
    apply_floor,
    fallback_answer,
    generate_with_validation,
    validate_citations,
)
from conftest import ScriptedProvider, good_answer, make_passage


def _invalid() -> ValidationError:
    try:
        Answer.model_validate_json("not json at all, just prose")
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


def test_floor_drops_weak_passages() -> None:
    kept = apply_floor([make_passage("a", score=0.9), make_passage("b", score=0.3)], 0.5)
    assert [p.chunk_id for p in kept] == ["a"]


def test_fabricated_citation_is_dropped() -> None:
    p = make_passage()
    answer = good_answer(p, citations=[
        Citation(source=p.source, section=p.section, page=1),
        Citation(source="invented.pdf", section="9.9 Nothing", page=1),
    ])
    valid, dropped = validate_citations(answer, [p])
    assert dropped == 1
    assert [(c.source, c.section) for c in valid] == [(p.source, p.section)]
    assert valid[0].page == p.page          # the page comes from the passage, not the model


def test_citation_match_ignores_case_whitespace_and_html_escapes() -> None:
    p = make_passage(section="2 Fees & Refunds")
    answer = good_answer(p, citations=[Citation(source="RULES-2026.pdf",
                                                section="2  fees &amp; refunds", page=None)])
    valid, dropped = validate_citations(answer, [p])
    assert len(valid) == 1 and dropped == 0


def test_all_fabricated_citations_means_not_grounded() -> None:
    p = make_passage()
    forged = good_answer(p, citations=[Citation(source="invented.pdf", section="x", page=1)])
    outcome = generate_with_validation(ScriptedProvider(forged), "q?", [p])
    assert outcome.answer.answered_from_context is False
    assert outcome.fallback_reason == "no_valid_citation"
    assert outcome.citations_dropped == 1


def test_grounded_answer_passes_through() -> None:
    p = make_passage()
    outcome = generate_with_validation(ScriptedProvider(good_answer(p)), "q?", [p])
    assert outcome.fallback_reason is None
    assert outcome.answer.answered_from_context is True
    assert len(outcome.answer.citations) == 1


def test_validation_failure_is_retried_once_then_succeeds() -> None:
    p = make_passage()
    provider = ScriptedProvider(_invalid(), good_answer(p))
    outcome = generate_with_validation(provider, "q?", [p])
    assert provider.calls == 2
    assert outcome.answer.answered_from_context is True


def test_two_validation_failures_give_the_fallback() -> None:
    provider = ScriptedProvider(_invalid(), _invalid())
    outcome = generate_with_validation(provider, "q?", [make_passage()])
    assert provider.calls == 2                     # retried exactly once
    assert outcome.fallback_reason == "invalid_model_output"
    assert outcome.answer.answered_from_context is False
    assert outcome.answer.answer == FALLBACK_MESSAGE


def test_provider_error_falls_back_without_raising() -> None:
    provider = ScriptedProvider(ProviderError("timeout"))
    outcome = generate_with_validation(provider, "q?", [make_passage()])
    assert provider.calls == 1                     # a timeout is not retried
    assert outcome.fallback_reason == "provider_error"


def test_unexpected_provider_bug_falls_back_without_raising() -> None:
    outcome = generate_with_validation(ScriptedProvider(RuntimeError("boom")), "q?",
                                       [make_passage()])
    assert outcome.fallback_reason == "unexpected_error"


def test_abstain_and_fallback_answers_are_never_grounded() -> None:
    assert abstention_answer().answered_from_context is False
    assert abstention_answer().citations == []
    assert fallback_answer("x").answered_from_context is False


@pytest.mark.parametrize("flag", [True, False])
def test_model_abstention_is_preserved(flag: bool) -> None:
    p = make_passage()
    ans = good_answer(p, answered_from_context=False, citations=[], answer="Not covered.")
    outcome = generate_with_validation(ScriptedProvider(ans), "q?", [p])
    assert outcome.answer.answered_from_context is False
    assert outcome.fallback_reason is None
