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


def test_live_round_trip_records_usage_and_version() -> None:
    from app.ai_gateway.gateway import build_llm
    from app.config import get_settings

    settings = get_settings()
    if not settings.hosted_api_key:
        pytest.skip("no hosted API key in environment (set GEMINI_API_KEY)")
    request = LLMRequest(
        messages=(ChatMessage("user", "Reply with the single word: ready"),),
        model=settings.llm_model,
        temperature=0.0,
        max_output_tokens=32,
        system="You are a connectivity probe for the demo build.",
    )
    try:
        result = build_llm().complete(request)
    except ProviderError as exc:
        pytest.fail(f"hosted provider failed: {exc}")
    assert result.text.strip()
    assert result.provider == "hosted"
    assert result.model
    assert not result.cached
    assert result.usage.prompt_tokens > 0
    assert result.usage.completion_tokens > 0
    assert result.usage.total_tokens >= result.usage.prompt_tokens + result.usage.completion_tokens
    assert result.model_version
