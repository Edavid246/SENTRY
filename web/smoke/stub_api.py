"""Run the real API with only the two model calls stubbed (UI smoke test).

Authorization, retrieval, typed tools, audit and RLS are all the real code; the
stub replaces just generate_answer / explain_result, which would otherwise need
a hosted-model key. Every answer is built from the chunks retrieval returned
for the caller, so what the UI shows still differs per user.

    .venv/Scripts/python.exe web/smoke/stub_api.py   (from the repo root)

With STUB_MODE=unavailable both model calls raise ProviderUnavailableError, which is
exactly what a cache miss in cache-only mode does, so the real 503 mapping is exercised
(web/smoke/cache_miss.mjs).
"""

import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.ai_gateway.base import ProviderUnavailableError  # noqa: E402
from app.api import assistant  # noqa: E402
from app.data_queries.explain import Explanation  # noqa: E402
from app.knowledge.answer import CitedAnswer  # noqa: E402
from app.main import app  # noqa: E402


def fake_generate_answer(question, chunks, *, gateway=None, history=()):
    if not chunks:
        return CitedAnswer(
            answer="No information found in approved sources.",
            citations=(),
            found=False,
            blocked=False,
        )
    picked = list(chunks)[:6]
    lines = [
        f"{c.document_title} sets out requirements relevant to your question "
        f"[{c.chunk_id}: {c.document_title}, page {c.page}]."
        for c in picked
    ]
    return CitedAnswer(
        answer="STUBBED MODEL (UI smoke test). " + " ".join(lines),
        citations=tuple(picked),
        found=True,
        blocked=False,
        model="stub",
        provider="stub",
    )


def fake_explain_result(question, result, *, gateway=None):
    if not result.rows:
        return Explanation(text="No matching records were found within your authorization.")
    return Explanation(
        text=f"STUBBED MODEL (UI smoke test). {len(result.rows)} records matched.",
        provider="stub",
        model="stub",
    )


def unavailable(*args, **kwargs):
    raise ProviderUnavailableError("cache-only mode: no cached answer (smoke stub)")


if os.environ.get("STUB_MODE") == "unavailable":
    assistant.generate_answer = unavailable
    assistant.explain_result = unavailable
else:
    assistant.generate_answer = fake_generate_answer
    assistant.explain_result = fake_explain_result

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
