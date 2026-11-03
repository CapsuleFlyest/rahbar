"""Hosted free-tier provider (Groq, Google AI Studio, OpenRouter): OpenAI-compatible.

The key arrives as LLM_API_KEY from a Kubernetes Secret created on the command
line. It never appears in a file you commit, and never in a log line or error message.
"""

from __future__ import annotations

import httpx

from ..._json import truncate
from ...config import Settings
from ...schemas import Answer, Passage
from ...services.prompt import build_messages
from .base import ProviderError, Usage


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings   # hosted_base_url, llm_model, llm_api_key, temperature
        self._transport = transport

    def generate(
        self, question: str, passages: list[Passage], usage: Usage | None = None
    ) -> Answer:
        s = self.settings
        if not s.hosted_base_url:
            raise ProviderError("HOSTED_BASE_URL is not set")
        payload = {
            "model": s.llm_model,
            # the schema is part of the system prompt; json_object mode guarantees valid JSON
            "messages": build_messages(question, passages),
            "temperature": s.temperature,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {s.llm_api_key}"}
        try:
            with httpx.Client(timeout=s.llm_timeout_seconds, transport=self._transport) as client:
                response = client.post(
                    f"{s.hosted_base_url.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:   # never include request headers (the key)
            raise ProviderError(f"hosted call failed: HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            raise ProviderError(f"hosted call failed: {type(exc).__name__}: "
                                f"{truncate(str(exc))}") from exc
        if usage is not None:
            tokens = body.get("usage") or {}
            usage.tokens_in += int(tokens.get("prompt_tokens") or 0)
            usage.tokens_out += int(tokens.get("completion_tokens") or 0)
        return Answer.model_validate_json(content)
