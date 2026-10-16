"""What the answer audit event says about the model call behind it (SPEC 8.1, 14.1)."""

from app.ai_gateway.base import LLMResult, TokenUsage
from app.assistant.service import _model_use


def test_a_model_call_is_recorded_with_version_tokens_and_latency() -> None:
    llm = LLMResult(
        text="answer",
        provider="hosted",
        model="m-1",
        model_version="m-1-2026-09",
        usage=TokenUsage(prompt_tokens=120, completion_tokens=30, total_tokens=150),
        latency_ms=412.6,
        cached=True,
    )
    assert _model_use(llm) == {
        "provider": "hosted",
        "model": "m-1",
        "model_version": "m-1-2026-09",
        "cached": True,
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "total_tokens": 150,
        "latency_ms": 413,
    }


def test_no_model_call_records_the_same_fields_empty() -> None:
    assert _model_use(None) == {
        "provider": "",
        "model": "",
        "model_version": "",
        "cached": False,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "latency_ms": 0,
    }
