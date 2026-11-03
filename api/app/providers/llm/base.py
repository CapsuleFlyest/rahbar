"""The LLM provider interface (section 3.5). Swapping providers is one file."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...schemas import Answer, Passage


class ProviderError(Exception):
    """Transport or HTTP failure talking to the model (timeout, refused, 5xx, bad body)."""


@dataclass
class Usage:
    """Token counts a provider reports; the caller turns them into metrics."""

    tokens_in: int = 0
    tokens_out: int = 0


class LLMProvider(Protocol):
    name: str

    def generate(
        self, question: str, passages: list[Passage], usage: Usage | None = None
    ) -> Answer:
        """Answer the question from the passages, as an `Answer`.

        Raises pydantic.ValidationError when the model's reply is not a valid Answer, and
        ProviderError when the call itself fails. The caller retries and falls back."""
        ...
