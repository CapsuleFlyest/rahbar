"""Ollama provider: ollama-host or ollama-incluster (section 3.5).

Structure is enforced with Ollama's `format` parameter (the Answer JSON schema), then
validated again with Pydantic: structure can be guaranteed, truth cannot.
"""

from __future__ import annotations

import httpx

from ...config import Settings
from ...schemas import Answer, Passage
from ..._json import truncate
from ...services.prompt import build_messages
from .base import ProviderError, Usage


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings   # ollama_url, llm_model, temperature, llm_timeout_seconds
        self._transport = transport

    def generate(
        self, question: str, passages: list[Passage], usage: Usage | None = None
    ) -> Answer:
        s = self.settings
        payload = {
            "model": s.llm_model,
            "messages": build_messages(question, passages),
            "stream": False,
            "format": Answer.model_json_schema(),
            "options": {"temperature": s.temperature},
        }
        try:
            with httpx.Client(timeout=s.llm_timeout_seconds, transport=self._transport) as client:
                response = client.post(f"{s.ollama_url.rstrip('/')}/api/chat", json=payload)
                response.raise_for_status()
                body = response.json()
                content = body["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise ProviderError(f"ollama call failed: {type(exc).__name__}: "
                                f"{truncate(str(exc))}") from exc
        if usage is not None:
            usage.tokens_in += int(body.get("prompt_eval_count") or 0)
            usage.tokens_out += int(body.get("eval_count") or 0)
        return Answer.model_validate_json(content)
