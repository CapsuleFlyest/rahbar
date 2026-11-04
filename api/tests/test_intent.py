from __future__ import annotations

import pytest

from app.services.intent import is_followup, wants_older_version


@pytest.mark.parametrize("q", [
    "What was the attendance rule in 2023?",
    "What did the previous version of the rules say about exhaustion?",
    "Is the superseded policy still valid?",
])
def test_older_version_is_detected(q: str) -> None:
    assert wants_older_version(q)


@pytest.mark.parametrize("q", [
    "What DC does the Hide action need?",
    "How much is the fee per credit hour?",
    "Is attendance mandatory in the current rules?",
])
def test_current_questions_do_not_ask_for_old_versions(q: str) -> None:
    assert not wants_older_version(q)


@pytest.mark.parametrize("q", [
    "And what about the MS programme?",
    "what if I fail it",
    "Is that allowed?",
])
def test_followups_are_detected(q: str) -> None:
    assert is_followup(q)


def test_standalone_questions_are_not_followups() -> None:
    assert not is_followup("What is the minimum attendance needed to sit the final exam?")
    assert not is_followup("Define exhaustion")
