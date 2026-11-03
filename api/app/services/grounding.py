"""Grounding (section 3.4): relevance floor, validation with one retry, citation check,
and a safe fallback so a user never sees a 500 because the model wrote prose.

Nothing here passes model or document text to eval, exec or SQL.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import unescape

from pydantic import ValidationError

from ..providers.llm.base import LLMProvider, ProviderError, Usage
from ..schemas import Answer, Citation, Passage

log = logging.getLogger("rahbar.grounding")

ABSTAIN_MESSAGE = (
    "I could not find this in the documents I have been given, so I will not guess. "
    "Please check with the relevant office."
)
FALLBACK_MESSAGE = (
    "I could not produce a reliable answer from the documents just now. "
    "Please try again, or rephrase the question."
)


def apply_floor(passages: list[Passage], floor: float) -> list[Passage]:
    """Keep only passages whose similarity clears the relevance floor."""
    return [p for p in passages if p.score >= floor]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip().lower()


def validate_citations(
    answer: Answer, passages: list[Passage]
) -> tuple[list[Citation], int]:
    """Keep only citations that match a passage actually retrieved for this request.

    A citation the retriever never returned is fabricated. The page is taken from the
    matching passage, not from the model. Returns (valid citations, number dropped)."""
    by_key = {(_norm(p.source), _norm(p.section)): p for p in passages}
    valid: list[Citation] = []
    seen: set[tuple[str, str]] = set()
    dropped = 0
    for c in answer.citations:
        key = (_norm(c.source), _norm(c.section))
        passage = by_key.get(key)
        if passage is None:
            dropped += 1
            continue
        if key in seen:
            continue
        seen.add(key)
        valid.append(Citation(source=passage.source, section=passage.section, page=passage.page))
    return valid, dropped


def abstention_answer() -> Answer:
    return Answer(
        reasoning="nothing retrieved cleared the relevance floor",
        answer=ABSTAIN_MESSAGE,
        citations=[],
        answered_from_context=False,
        confidence="low",
    )


def fallback_answer(reason: str) -> Answer:
    return Answer(
        reasoning=f"fallback: {reason}",
        answer=FALLBACK_MESSAGE,
        citations=[],
        answered_from_context=False,
        confidence="low",
    )


@dataclass
class Outcome:
    answer: Answer
    fallback_reason: str | None = None
    citations_dropped: int = 0


def generate_with_validation(
    provider: LLMProvider, question: str, passages: list[Passage], usage: Usage | None = None
) -> Outcome:
    """Generate, validate, retry once on a malformed reply, then fall back. Never raises."""
    answer: Answer | None = None
    for attempt in (1, 2):
        try:
            answer = provider.generate(question, passages, usage=usage)
            break
        except ProviderError as exc:        # timeout, refused, 5xx: a retry will not help now
            log.warning("provider failed", extra={"error": str(exc)})
            return Outcome(fallback_answer("provider_error"), "provider_error")
        except (ValidationError, ValueError) as exc:    # the model wrote prose, not our schema
            log.warning("model output failed validation",
                        extra={"attempt": attempt, "error_type": type(exc).__name__})
        except Exception:                   # a bug must not become a 500 for the user
            log.exception("unexpected provider failure")
            return Outcome(fallback_answer("unexpected_error"), "unexpected_error")
    if answer is None:
        return Outcome(fallback_answer("invalid_model_output"), "invalid_model_output")

    citations, dropped = validate_citations(answer, passages)
    if answer.answered_from_context and not citations:
        # A grounded answer with no verifiable citation is not grounded.
        return Outcome(fallback_answer("no_valid_citation"), "no_valid_citation", dropped)
    cleaned = answer.model_copy(update={"citations": citations})
    return Outcome(cleaned, None, dropped)
