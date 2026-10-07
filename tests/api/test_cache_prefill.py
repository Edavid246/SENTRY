"""Cache prefill rehearsal through the real pipeline (scripts/prefill_cache.py).

A fake LLM stands in for Gemini, everything else is real: login, routing,
authorization-filtered retrieval (FTS-only here), evidence prompt, tool
explanation, audit. It proves the property the prefill relies on:

  * record mode stores one entry per distinct model request, and the same
    (user, question) asked again in a NEW conversation produces the same key;
  * cache-only mode (provider disabled) then answers every planned pair from
    the cache and never raises ProviderUnavailableError;
  * a recorded request is the exact prompt sent to the model, so it holds only
    sources the asking user is cleared for (Principle Zero).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from app.ai_gateway import AIGateway, LLMResponseCache, ProviderUnavailableError
from app.ai_gateway.base import ChatMessage, LLMRequest, LLMResult
from test_assistant_endpoints import _ask

REPO = Path(__file__).resolve().parents[2]
# FTS-only retrieval ANDs every word, so the rehearsal uses a short knowledge query.
SHORT_KNOWLEDGE_QUESTION = "servicing maintenance"


def _load_prefill():
    spec = importlib.util.spec_from_file_location(
        "prefill_cache", REPO / "scripts/prefill_cache.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RecordingFake:
    provider_name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        marker = request.messages[-1].text
        # Cite whatever chunk the evidence offers, so the real validators run.
        chunk_id = ""
        if "BEGIN EVIDENCE CHUNK " in marker:
            chunk_id = marker.split("BEGIN EVIDENCE CHUNK ", 1)[1].split(" ", 1)[0]
        text = f"Fake answer [{chunk_id}: demo, page 1]" if chunk_id else "Fake explanation."
        return LLMResult(text=text, provider="fake", model=request.model, model_version="fake-1")


@pytest.fixture
def pipeline(monkeypatch, tmp_path, ingested):
    monkeypatch.setattr("app.knowledge.retrieve._query_embedding", lambda question: None)
    cache = LLMResponseCache(tmp_path / "cache.json")
    fake = RecordingFake()
    state = {"gateway": AIGateway(fake, cache=cache, record=True)}
    monkeypatch.setattr("app.knowledge.answer.get_gateway", lambda: state["gateway"])
    monkeypatch.setattr("app.data_queries.explain.get_gateway", lambda: state["gateway"])
    return state, cache, fake


def test_prefill_plan_covers_built_assistant_questions_for_both_users() -> None:
    module = _load_prefill()
    questions = json.loads((REPO / "data/demo_questions.json").read_text(encoding="utf-8"))
    pairs = module.plan_pairs(questions["questions"])
    assert pairs, "no built assistant questions to prefill"
    seen = {(pair.user, pair.question) for pair in pairs}
    assert len(seen) == len(pairs)  # de-duplicated
    built = [
        q for q in questions["questions"] if q["status"] == "built" and q["pathway"] != "audit"
    ]
    for entry in built:
        for user in ("a.bello", "t.adeyemi"):
            assert (user, entry["question"]) in seen
    assert not any(pair.user == "f.danjuma" for pair in pairs)  # audit viewer, not the assistant


def test_record_then_cache_only_answers_every_pair(client, pipeline) -> None:
    module = _load_prefill()
    questions = json.loads((REPO / "data/demo_questions.json").read_text(encoding="utf-8"))
    pairs = module.plan_pairs(questions["questions"])
    pairs += [
        module.Pair(u, SHORT_KNOWLEDGE_QUESTION, ("short",)) for u in ("a.bello", "t.adeyemi")
    ]
    state, cache, fake = pipeline

    for pair in pairs:
        assert _ask(client, pair.user, pair.question).status_code == 200, pair
    recorded = json.loads(cache.path.read_text(encoding="utf-8"))
    assert state["gateway"].recorded_count >= 1 and recorded
    assert any("EVIDENCE" in v["request"]["messages"][-1][1] for v in recorded.values())
    assert "\r\n" not in cache.path.read_text(encoding="utf-8")

    # Provider disabled: same pairs, fresh conversations, nothing may be missing.
    calls_before = fake.calls
    state["gateway"] = AIGateway(fake, cache=cache, cache_only=True)
    for pair in pairs:
        response = _ask(client, pair.user, pair.question)
        assert response.status_code == 200, (pair, response.text)
        assert response.json()["answer"].strip()
    assert fake.calls == calls_before
    assert state["gateway"].replayed_count >= 1


def test_cache_only_miss_is_provider_unavailable_not_a_made_up_answer(client, pipeline) -> None:
    state, cache, fake = pipeline
    state["gateway"] = AIGateway(fake, cache=cache, cache_only=True)
    response = _ask(client, "a.bello", SHORT_KNOWLEDGE_QUESTION)
    assert response.status_code == 503
    assert fake.calls == 0
    with pytest.raises(ProviderUnavailableError):
        state["gateway"].complete(LLMRequest(messages=(ChatMessage("user", "never recorded"),)))


def test_recorded_prompts_hold_only_what_the_user_may_see(client, pipeline) -> None:
    """Principle Zero in the cache: a recorded request is the exact prompt sent to the
    model, so it must never contain a source the asking user is not cleared for."""
    state, cache, fake = pipeline
    assert _ask(client, "t.adeyemi", SHORT_KNOWLEDGE_QUESTION).status_code == 200
    recorded = json.loads(cache.path.read_text(encoding="utf-8"))
    assert recorded
    for entry in recorded.values():
        prompt = entry["request"]["messages"][-1][1]
        assert "source: DOC-201" not in prompt and "source: DOC-203" not in prompt


def test_prefill_script_tags_its_audit_events(monkeypatch) -> None:
    import os

    module = _load_prefill()
    for name in ("AUDIT_SOURCE", "LLM_CACHE_ONLY", "LLM_CACHE_RECORD", "HOSTED_API_KEY"):
        monkeypatch.setenv(name, "x")  # registers the variable so monkeypatch restores it
    module._prepare_environment(True)
    assert os.environ["AUDIT_SOURCE"] == "prefill-verify"
    monkeypatch.setenv("HOSTED_API_KEY", "x")
    module._prepare_environment(False)
    assert os.environ["AUDIT_SOURCE"] == "prefill"
