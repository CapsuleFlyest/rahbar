"""Cheap, deterministic reading of the question (no model call)."""

from __future__ import annotations

import re

_OLD_YEAR = re.compile(r"\b(20(?:1\d|2[0-5]))\b")
_OLD_WORD = re.compile(
    r"\b(old(?:er)?|previous(?:ly)?|earlier|prior|superseded|former(?:ly)?|repealed|"
    r"outdated|legacy|replaced)\b",
    re.I,
)
_DOC_WORD = re.compile(r"\b(version|edition|rules?|polic(?:y|ies)|handbook|regulations?|"
                       r"srd|compendium|errata|report)\b", re.I)

_FOLLOWUP_OPENERS = re.compile(
    r"^\s*(and\b|also\b|then\b|but\b|what about\b|how about\b|what if\b|so\b)", re.I
)
_PRONOUN_REF = re.compile(r"\b(it|that|this|those|they|them|these|its|their)\b", re.I)


def wants_older_version(question: str) -> bool:
    """True when the user explicitly asks about an older edition, so superseded documents
    must NOT be filtered out (section 3.2, step 4)."""
    if _OLD_YEAR.search(question):
        return True
    return bool(_OLD_WORD.search(question) and _DOC_WORD.search(question))


def is_followup(question: str) -> bool:
    """Heuristic: a follow-up depends on an earlier turn, so its answer is not a property of
    the question alone and must never be cached (section 3.3)."""
    if _FOLLOWUP_OPENERS.match(question):
        return True
    words = question.split()
    return len(words) <= 6 and bool(_PRONOUN_REF.search(question))
