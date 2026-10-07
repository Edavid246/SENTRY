"""Live hosted-LLM test (SPEC 8.1): real Gemini round trip.

Opt-in only — never runs in the default suite (cost, quota, network):

    GEMINI_API_KEY=... RUN_LIVE_AI=1 uv run pytest tests/ai/test_hosted_live.py -q
"""

import os

import pytest
from app.ai_gateway import ChatMessage, LLMRequest, ProviderError

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_AI") != "1", reason="live AI test; set RUN_LIVE_AI=1 to run"
)


@pytest.fixture(scope="module")
def live_result():
    from app.ai_gateway.gateway import build_llm
    from app.config import get_settings

    settings = get_settings()
    if not settings.hosted_api_key:
        pytest.skip("no hosted API key in environment (set GEMINI_API_KEY)")
    gateway_provider = build_llm()
    request = LLMRequest(
        messages=(ChatMessage("user", "Reply with the single word: ready"),),
        model=settings.llm_model,
        temperature=0.0,
        max_output_tokens=32,
        system="You are a connectivity probe for the demo build.",
    )
    try:
        result = gateway_provider.complete(request)
    except ProviderError as exc:
        pytest.fail(f"hosted provider failed: {exc}")
    return result


def test_live_round_trip(live_result) -> None:
    assert live_result.text.strip()
    assert live_result.provider == "hosted"
    assert live_result.model
    assert not live_result.cached


def test_live_usage_recorded(live_result) -> None:
    assert live_result.usage.prompt_tokens > 0
    assert live_result.usage.completion_tokens > 0
    assert live_result.usage.total_tokens >= (
        live_result.usage.prompt_tokens + live_result.usage.completion_tokens
    )


def test_live_model_version_recorded(live_result) -> None:
    assert live_result.model_version
