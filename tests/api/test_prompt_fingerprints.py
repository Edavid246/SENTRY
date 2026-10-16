"""Prompt fingerprints: the exact model requests the scripted demo questions produce.

Why this exists (docs/REFACTOR_PLAN.md, step 0.1). The demo LLM cache is keyed by the hash
of the exact model request (app/ai_gateway/cache.py). If a change moves a system prompt, the
evidence format, a chunk id, a seeded row, a date or the order of tool rows by one byte, every
recorded answer for that question silently becomes a cache miss. This test asks every built
question in data/demo_questions.json, as its asker and as the owner (the account the prefill
records for), and compares each model request with tests/snapshots/prompt_fingerprints.json.

The database is reseeded with DEMO_DATE pinned to the demo date, so the snapshot holds on any
calendar day; it is restored to the live date afterwards. The seed computes its dates when
app.seed is imported, so the pinned seed runs in a fresh interpreter.

A failure means a prompt changed. If that was intended, re-record with UPDATE_SNAPSHOTS=1 and
re-run the cache prefill (docs/DEMO_SCOPE.md); otherwise the change altered behaviour.

Limit: the test database has no embedding weights, so retrieval runs keyword-only, and the long
scripted knowledge questions find nothing that way (every word must be in one passage). A short
keyword question is added so the knowledge prompt, the evidence format, the chunk ids and the
keyword ranking are pinned; the vector ranking the live demo uses is not. Follow-up turns are not
asked: today a turn's two messages can come back in either order (docs/PRODUCTION_DEBT.md).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.ai_gateway import LLMResponseCache
from fakes import FakeLLM
from test_auth_endpoints import auth_header

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = REPO_ROOT / "data" / "demo_questions.json"
DEMO_DATE = "2026-10-07"  # the demo's pinned business date (docs/DEMO_SCOPE.md)
EXTRA_USERS = ("owner",)  # recorded for besides each question's asker (the prefill's account)
SKIPPED_PATHWAYS = frozenset({"audit"})  # asks no model (the prefill skips it too)
# A knowledge question keyword-only retrieval can answer, as two clearances (see the limit above).
KEYWORD_QUESTION = ("knowledge-keyword-servicing", "servicing maintenance", ("owner", "coo"))


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _pairs() -> list[tuple[str, str, str]]:
    """(label, user, question) for every built question, one per distinct (user, question)."""
    entries = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    labels: dict[tuple[str, str], str] = {}
    for entry in entries:
        if entry["status"] != "built" or entry["pathway"] in SKIPPED_PATHWAYS:
            continue
        for user in dict.fromkeys((entry["asked_by"], *EXTRA_USERS)):
            labels.setdefault((user, entry["question"]), entry["id"])
    label, question, users = KEYWORD_QUESTION
    for user in users:
        labels.setdefault((user, question), label)
    return [(f"{label} / {user}", user, question) for (user, question), label in labels.items()]


@pytest.fixture(scope="module")
def pinned_corpus(client, settings) -> Iterator[None]:
    """The test database seeded on DEMO_DATE; reseeded on the live date afterwards."""
    from app.config import get_settings
    from app.seed import run as run_seed

    url = settings.test_owner_database_url
    seed = "import sys; from app.seed import run; run(sys.argv[1], include_archived=True)"
    done = subprocess.run(
        [sys.executable, "-c", seed, url],
        env={**os.environ, "DEMO_DATE": DEMO_DATE},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    previous = os.environ.get("DEMO_DATE")
    os.environ["DEMO_DATE"] = DEMO_DATE
    get_settings.cache_clear()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DEMO_DATE", None)
        else:
            os.environ["DEMO_DATE"] = previous
        get_settings.cache_clear()
        # This process imported app.seed on the live date, so its rows are the session's seed.
        run_seed(url, include_archived=True)


def test_scripted_questions_send_the_recorded_prompts(
    client, models, pinned_corpus, ingested, snapshot
) -> None:
    llm = FakeLLM()
    models(llm)
    headers: dict[str, dict[str, str]] = {}

    def login(user: str) -> dict[str, str]:
        if user not in headers:
            headers[user] = auth_header(client, user)
        return headers[user]

    # The findings question needs the correlation run first, as in the prefill.
    assert client.post("/api/v1/correlation/run", headers=login("owner")).status_code == 200

    systems: dict[str, list[str]] = {}
    pairs: dict[str, Any] = {}
    for label, user, question in _pairs():
        before = len(llm.requests)
        response = client.post(
            "/api/v1/assistant/query", json={"question": question}, headers=login(user)
        )
        calls = []
        for request in llm.requests[before:]:
            system = request.system or ""
            systems[_digest(system)] = system.split("\n")
            calls.append(
                {
                    "key": LLMResponseCache.key(request)[:16],
                    "system": _digest(system),
                    "messages": [
                        {"role": message.role, "text": message.text.split("\n")}
                        for message in request.messages
                    ],
                }
            )
        pairs[label] = {"status": response.status_code, "calls": calls}

    snapshot("prompt_fingerprints", {"demo_date": DEMO_DATE, "systems": systems, "pairs": pairs})
