"""The hosted (Groq) provider against a fake HTTP server: no network, no key, no sleeping."""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import good_answer, make_passage
from pydantic import ValidationError

from app.config import Settings
from app.providers.llm import hosted
from app.providers.llm.base import ProviderError, Usage
from app.providers.llm.hosted import HostedProvider

SECRET = "gsk_super_secret_key_123"


def settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "hosted_base_url": "https://llm.test/openai/v1", "llm_api_key": SECRET,
        "llm_model": "test-model", "llm_max_retries": 2, "llm_retry_max_wait_seconds": 5.0,
        "llm_timeout_seconds": 30.0,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def ok_body() -> dict[str, object]:
    return {"choices": [{"message": {"content": good_answer().model_dump_json()}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30}}


class Server:
    """Replies with the given responses in order (the last one repeats) and records requests."""

    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.responses) - 1)
        return self.responses[index]

    def provider(self, **overrides: object) -> HostedProvider:
        return HostedProvider(settings(**overrides), transport=httpx.MockTransport(self))


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(hosted, "_sleep", recorded.append)
    return recorded


def ask(provider: HostedProvider, usage: Usage | None = None) -> object:
    return provider.generate("What DC does Hide need?", [make_passage()], usage=usage)


def test_success_sends_json_mode_key_and_counts_tokens(sleeps: list[float]) -> None:
    server = Server(httpx.Response(200, json=ok_body()))
    usage = Usage()
    answer = ask(server.provider(), usage)
    request = server.requests[0]
    sent = json.loads(request.content)
    assert str(request.url) == "https://llm.test/openai/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["model"] == "test-model"
    assert answer.answered_from_context is True    # type: ignore[attr-defined]
    assert (usage.tokens_in, usage.tokens_out) == (120, 30)
    assert sleeps == []


def test_429_waits_retry_after_then_succeeds(sleeps: list[float]) -> None:
    server = Server(httpx.Response(429, headers={"retry-after": "2"}),
                    httpx.Response(200, json=ok_body()))
    ask(server.provider())
    assert len(server.requests) == 2
    assert sleeps == [2.0]


def test_5xx_without_retry_after_backs_off_exponentially(sleeps: list[float]) -> None:
    server = Server(httpx.Response(503), httpx.Response(502), httpx.Response(200, json=ok_body()))
    ask(server.provider())
    assert len(server.requests) == 3
    assert sleeps == [1.0, 2.0]


def test_persistent_429_gives_up_after_max_retries(sleeps: list[float]) -> None:
    server = Server(httpx.Response(429, headers={"retry-after": "1"}))
    with pytest.raises(ProviderError) as info:
        ask(server.provider())
    assert len(server.requests) == 3                  # first try + 2 retries
    assert "429" in str(info.value) and "2 retries" in str(info.value)
    assert SECRET not in str(info.value)


def test_retry_after_longer_than_allowed_fails_fast(sleeps: list[float]) -> None:
    server = Server(httpx.Response(429, headers={"retry-after": "30"}))
    with pytest.raises(ProviderError, match="429"):
        ask(server.provider())
    assert len(server.requests) == 1 and sleeps == []


def test_wait_that_would_blow_the_total_budget_fails_fast(sleeps: list[float]) -> None:
    server = Server(httpx.Response(429, headers={"retry-after": "4"}))
    with pytest.raises(ProviderError):
        ask(server.provider(llm_timeout_seconds=3.0))
    assert len(server.requests) == 1 and sleeps == []


def test_401_is_not_retried_and_never_leaks_the_key(sleeps: list[float]) -> None:
    server = Server(httpx.Response(401, json={"error": {"message": f"bad key {SECRET}"}}))
    with pytest.raises(ProviderError) as info:
        ask(server.provider())
    assert len(server.requests) == 1 and sleeps == []
    assert "401" in str(info.value) and SECRET not in str(info.value)


def test_missing_key_fails_before_any_request(sleeps: list[float]) -> None:
    server = Server(httpx.Response(200, json=ok_body()))
    with pytest.raises(ProviderError, match="LLM_API_KEY"):
        ask(server.provider(llm_api_key=""))
    assert server.requests == []


def test_prose_instead_of_json_is_a_validation_error_for_the_caller_to_retry(
    sleeps: list[float],
) -> None:
    body = {"choices": [{"message": {"content": "Sure! The DC is 15."}}]}
    server = Server(httpx.Response(200, json=body))
    with pytest.raises(ValidationError):
        ask(server.provider())
