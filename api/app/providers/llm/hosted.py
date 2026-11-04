"""Hosted free-tier provider (Groq, Google AI Studio, OpenRouter): OpenAI-compatible.

The key arrives as LLM_API_KEY from a Kubernetes Secret created on the command
line. It never appears in a file you commit, and never in a log line or error message.

Free tiers are rate limited per minute, so a 429 is normal, not an error: we wait
(Retry-After when the server sends it) and retry a bounded number of times, inside one
total time budget (LLM_TIMEOUT_SECONDS) so the user never waits past the Ingress timeout.
"""

from __future__ import annotations

import time

import httpx

from ..._json import truncate
from ...config import Settings
from ...schemas import Answer, Passage
from ...services.prompt import build_messages
from .base import ProviderError, Usage

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_sleep = time.sleep      # a module attribute so tests can replace it


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds the server asked us to wait, or None when it did not say (or said it oddly)."""
    try:
        return max(0.0, float(response.headers["retry-after"]))
    except (KeyError, ValueError):
        return None


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings   # hosted_base_url, llm_model, llm_api_key, temperature, retries
        self._transport = transport

    def generate(
        self, question: str, passages: list[Passage], usage: Usage | None = None
    ) -> Answer:
        s = self.settings
        if not s.hosted_base_url:
            raise ProviderError("HOSTED_BASE_URL is not set")
        if not s.llm_api_key:
            raise ProviderError("LLM_API_KEY is not set (create it with: make secret)")
        payload = {
            "model": s.llm_model,
            # the schema is part of the system prompt; json_object mode guarantees valid JSON
            "messages": build_messages(question, passages),
            "temperature": s.temperature,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {s.llm_api_key}"}
        url = f"{s.hosted_base_url.rstrip('/')}/chat/completions"
        started = time.monotonic()
        attempt = 0
        while True:
            remaining = s.llm_timeout_seconds - (time.monotonic() - started)
            try:
                with httpx.Client(timeout=max(remaining, 1.0), transport=self._transport) as client:
                    response = client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    body = response.json()
                    content = body["choices"][0]["message"]["content"]
                break
            except httpx.HTTPStatusError as exc:   # never include request headers (the key)
                status = exc.response.status_code
                delay = self._wait_before_retry(exc.response, attempt, started)
                if status in RETRYABLE_STATUS and attempt < s.llm_max_retries and delay is not None:
                    _sleep(delay)
                    attempt += 1
                    continue
                suffix = f" after {attempt} retries" if attempt else ""
                raise ProviderError(f"hosted call failed: HTTP {status}{suffix}") from exc
            except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
                raise ProviderError(f"hosted call failed: {type(exc).__name__}: "
                                    f"{truncate(str(exc))}") from exc
        if usage is not None:
            tokens = body.get("usage") or {}
            usage.tokens_in += int(tokens.get("prompt_tokens") or 0)
            usage.tokens_out += int(tokens.get("completion_tokens") or 0)
        return Answer.model_validate_json(content)

    def _wait_before_retry(
        self, response: httpx.Response, attempt: int, started: float
    ) -> float | None:
        """How long to wait before retrying, or None when waiting is pointless:
        the server asked for longer than we allow, or the total budget would be spent."""
        s = self.settings
        asked = _retry_after(response)
        delay = asked if asked is not None else float(2 ** attempt)      # 1, 2, 4 ...
        if delay > s.llm_retry_max_wait_seconds:
            return None
        elapsed = time.monotonic() - started
        if elapsed + delay >= s.llm_timeout_seconds:
            return None
        return delay
