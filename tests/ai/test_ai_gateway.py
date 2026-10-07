"""Hermetic AI gateway tests: hosted request/response contract, retries,
cache fallback and cache-key sensitivity (httpx.MockTransport, no network)."""

import json

import httpx
import pytest
from app.ai_gateway import (
    AIGateway,
    ChatMessage,
    HostedProvider,
    LLMRequest,
    LLMResponseCache,
    LLMResult,
    LocalVLLMProvider,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TokenUsage,
)
from app.ai_gateway.gateway import build_llm
from app.config import get_settings

API_KEY = "test-key-abc123"
GOOD_BODY = {
    "candidates": [{"content": {"parts": [{"text": "runway 09 clear"}]}}],
    "usageMetadata": {
        "promptTokenCount": 11,
        "candidatesTokenCount": 7,
        "totalTokenCount": 18,
    },
    "modelVersion": "gemini-3.5-flash-001",
}


def make_request(**overrides) -> LLMRequest:
    defaults = {
        "messages": (ChatMessage("user", "status of runway 09?"),),
        "model": "gemini-3.5-flash",
        "temperature": 0.0,
        "max_output_tokens": 256,
        "system": "be terse",
    }
    defaults.update(overrides)
    return LLMRequest(**defaults)


def make_provider(handler, api_key: str = API_KEY) -> HostedProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HostedProvider(
        api_key=api_key,
        base_url="https://example.test/v1beta",
        model="gemini-3.5-flash",
        timeout_seconds=5.0,
        client=client,
    )


def ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=GOOD_BODY)


class FakeLLM:
    provider_name = "fake"

    def __init__(self, *outcomes: Exception | LLMResult) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResult:
        self.calls.append(request)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def ok_result(text: str = "live answer") -> LLMResult:
    return LLMResult(
        text=text,
        provider="fake",
        model="gemini-3.5-flash",
        model_version="v-test",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def test_hosted_request_shape() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=GOOD_BODY)

    provider = make_provider(handler)
    request = make_request(
        messages=(ChatMessage("user", "question"), ChatMessage("assistant", "earlier answer"))
    )
    provider.complete(request)

    sent = captured[0]
    assert str(sent.url) == "https://example.test/v1beta/models/gemini-3.5-flash:generateContent"
    assert API_KEY not in str(sent.url)
    assert sent.headers["x-goog-api-key"] == API_KEY
    body = json.loads(sent.content)
    assert body["contents"] == [
        {"role": "user", "parts": [{"text": "question"}]},
        {"role": "model", "parts": [{"text": "earlier answer"}]},
    ]
    assert body["systemInstruction"] == {"parts": [{"text": "be terse"}]}
    assert body["generationConfig"] == {"temperature": 0.0, "maxOutputTokens": 256}


def test_hosted_parses_text_usage_and_version() -> None:
    result = make_provider(ok_handler).complete(make_request())
    assert result.text == "runway 09 clear"
    assert result.provider == "hosted"
    assert result.model == "gemini-3.5-flash"
    assert result.model_version == "gemini-3.5-flash-001"
    assert result.usage == TokenUsage(prompt_tokens=11, completion_tokens=7, total_tokens=18)
    assert not result.cached


def test_hosted_missing_candidate_text_raises() -> None:
    provider = make_provider(lambda request: httpx.Response(200, json={"candidates": []}))
    with pytest.raises(ProviderResponseError):
        provider.complete(make_request())


def test_hosted_rate_limit_carries_retry_after() -> None:
    provider = make_provider(
        lambda request: httpx.Response(429, headers={"retry-after": "2"}, json={})
    )
    with pytest.raises(ProviderRateLimitError) as excinfo:
        provider.complete(make_request())
    assert excinfo.value.retry_after == 2.0
    assert API_KEY not in str(excinfo.value)


def test_hosted_server_error_is_unavailable() -> None:
    provider = make_provider(lambda request: httpx.Response(503, json={}))
    with pytest.raises(ProviderUnavailableError):
        provider.complete(make_request())


def test_hosted_client_error_message_has_no_key() -> None:
    provider = make_provider(
        lambda request: httpx.Response(
            400, json={"error": {"message": f"bad request for {API_KEY}"}}
        )
    )
    with pytest.raises(ProviderError) as excinfo:
        provider.complete(make_request())
    assert "400" in str(excinfo.value)
    assert API_KEY not in str(excinfo.value)


def test_hosted_timeout_is_provider_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ProviderTimeoutError) as excinfo:
        make_provider(handler).complete(make_request())
    assert API_KEY not in str(excinfo.value)


def test_missing_key_fails_closed() -> None:
    with pytest.raises(ProviderNotConfiguredError) as excinfo:
        make_provider(ok_handler, api_key="")
    assert "API key" in str(excinfo.value)


def test_gateway_retries_then_succeeds() -> None:
    fake = FakeLLM(
        ProviderTimeoutError("first"),
        ProviderUnavailableError("second"),
        ok_result(),
    )
    sleeps: list[float] = []
    gateway = AIGateway(fake, max_retries=2, sleep=sleeps.append)
    result = gateway.complete(make_request())
    assert result.text == "live answer"
    assert len(fake.calls) == 3
    assert sleeps == [0.5, 1.0]
    assert result.latency_ms >= 0.0


def test_gateway_honours_retry_after_capped() -> None:
    fake = FakeLLM(
        ProviderRateLimitError("limited", retry_after=30.0),
        ProviderRateLimitError("limited", retry_after=1.0),
        ok_result(),
    )
    sleeps: list[float] = []
    gateway = AIGateway(fake, max_retries=2, retry_after_cap=5.0, sleep=sleeps.append)
    gateway.complete(make_request())
    assert sleeps == [5.0, 1.0]


def test_gateway_falls_back_to_cache_after_retries(tmp_path) -> None:
    cache = LLMResponseCache(tmp_path / "cache.json")
    request = make_request()
    cache.record(request, text="canned answer", model_version="v-canned")
    fake = FakeLLM(ProviderTimeoutError("down"))
    gateway = AIGateway(fake, cache=cache, max_retries=1, sleep=lambda delay: None)
    result = gateway.complete(request)
    assert result.cached
    assert result.text == "canned answer"
    assert result.model_version == "v-canned"
    assert result.provider == "fake"
    assert result.model == request.model
    assert "PRODUCTION_DEBT" in result.notice
    assert len(fake.calls) == 2


def test_gateway_without_cache_propagates_error(tmp_path) -> None:
    fake = FakeLLM(ProviderTimeoutError("down"))
    gateway = AIGateway(
        fake, cache=LLMResponseCache(tmp_path / "missing.json"), max_retries=1, sleep=lambda d: None
    )
    with pytest.raises(ProviderTimeoutError):
        gateway.complete(make_request())


def test_gateway_never_masks_not_configured(tmp_path) -> None:
    cache = LLMResponseCache(tmp_path / "cache.json")
    request = make_request()
    cache.record(request, text="canned answer")
    fake = FakeLLM(ProviderNotConfiguredError("stub"))
    gateway = AIGateway(fake, cache=cache, max_retries=5, sleep=lambda delay: None)
    with pytest.raises(ProviderNotConfiguredError):
        gateway.complete(request)


def test_gateway_resolves_configured_model() -> None:
    fake = FakeLLM(ok_result())
    gateway = AIGateway(fake, max_retries=0, sleep=lambda delay: None)
    request = make_request(model="")
    result = gateway.complete(request)
    expected = get_settings().llm_model
    assert expected
    assert fake.calls[0].model == expected
    assert result.model == expected


def test_cache_key_sensitivity_to_full_request_shape() -> None:
    base = make_request()
    variants = {
        "temperature": make_request(temperature=0.7),
        "max_output_tokens": make_request(max_output_tokens=64),
        "model": make_request(model="other-model"),
        "messages": make_request(messages=(ChatMessage("user", "different"),)),
        "system": make_request(system="different system"),
        "extra_message": make_request(
            messages=(ChatMessage("user", "status of runway 09?"), ChatMessage("user", "more"))
        ),
    }
    keys = {name: LLMResponseCache.key(value) for name, value in variants.items()}
    assert len(set(keys.values())) == len(variants)
    assert len({LLMResponseCache.key(base), *keys.values()}) == len(variants) + 1
    assert LLMResponseCache.key(base) == LLMResponseCache.key(make_request())


def test_cache_record_and_replay_roundtrip(tmp_path) -> None:
    path = tmp_path / "cache.json"
    cache = LLMResponseCache(path)
    request = make_request()
    key = cache.record(request, text="recorded", model_version="v1")
    assert key == LLMResponseCache.key(request)
    stored = json.loads(path.read_text())
    assert stored[key]["response"]["text"] == "recorded"
    assert LLMResponseCache(path).get(key)["response"]["text"] == "recorded"


def test_local_vllm_stub_fails_closed() -> None:
    provider = LocalVLLMProvider(base_url="http://localhost:8000/v1", model="some-model")
    with pytest.raises(ProviderNotConfiguredError):
        provider.complete(make_request())


def test_factory_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "does-not-exist")
    get_settings.cache_clear()
    try:
        with pytest.raises(ProviderNotConfiguredError):
            build_llm()
    finally:
        get_settings.cache_clear()


def test_factory_local_vllm(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "local_vllm")
    get_settings.cache_clear()
    try:
        provider = build_llm()
        assert isinstance(provider, LocalVLLMProvider)
        with pytest.raises(ProviderNotConfiguredError):
            provider.complete(make_request())
    finally:
        get_settings.cache_clear()


def test_factory_hosted_requires_key(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "hosted")
    monkeypatch.delenv("HOSTED_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ProviderNotConfiguredError):
            build_llm()
    finally:
        get_settings.cache_clear()
