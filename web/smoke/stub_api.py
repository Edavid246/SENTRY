"""Run the real API with only the model stubbed (UI smoke test).

Authorization, retrieval, typed tools, audit and RLS are all the real code; the
stub replaces only the language model, at the model seam (app.api.deps.get_models),
which would otherwise need a hosted-model key. It answers from the prompt it is
given, so every answer is built from the chunks retrieval returned for the caller
and what the UI shows still differs per user.

    .venv/Scripts/python.exe web/smoke/stub_api.py   (from the repo root)

With STUB_MODE=unavailable every model call raises ProviderUnavailableError, which is
exactly what a cache miss in cache-only mode does, so the real 503 mapping is exercised
(web/smoke/cache_miss.mjs).
"""

import json
import os
import re
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.ai_gateway.base import LLMResult, ProviderUnavailableError  # noqa: E402
from app.ai_gateway.port import ModelPort  # noqa: E402
from app.api.deps import get_models  # noqa: E402
from app.main import app  # noqa: E402

_EVIDENCE_RE = re.compile(r"BEGIN EVIDENCE CHUNK ([0-9a-f-]{36}) =====\ntitle: ([^\n]*)")
_PREFIX = "STUBBED MODEL (UI smoke test)."


class StubLLM:
    """Answers each pathway's prompt from what the prompt contains, like a careful model."""

    def complete(self, request):
        prompt = request.messages[-1].text
        if "QUERY RESULT" in prompt:
            table = json.loads(prompt.split("\n", 3)[3].rsplit("\n\nExplain", 1)[0])
            text = f"{_PREFIX} {len(table['rows'])} records matched."
        elif "TRAINING TABLE" in prompt:
            records = sorted(set(re.findall(r"REC-\d{3,6}", prompt)))
            lines = ["SUMMARY", _PREFIX, "", "ACTIVITY IN THE PERIOD"]
            lines += [f"Training event ({r})." for r in records]
            lines += ["", "APPLICABLE REQUIREMENTS"]
            if chunk := _EVIDENCE_RE.search(prompt):
                lines.append(f"Directive requirement [{chunk.group(1)}: Training, page 1].")
            text = "\n".join(lines)
        else:
            cited = [
                f"{title} sets out requirements relevant to your question"
                f" [{chunk_id}: {title}, page 1]."
                for chunk_id, title in _EVIDENCE_RE.findall(prompt)[:6]
            ]
            text = f"{_PREFIX} " + " ".join(cited)
        return LLMResult(text=text, provider="stub", model="stub")


class DownLLM:
    def complete(self, request):
        raise ProviderUnavailableError("cache-only mode: no cached answer (smoke stub)")


llm = DownLLM() if os.environ.get("STUB_MODE") == "unavailable" else StubLLM()
app.dependency_overrides[get_models] = lambda: ModelPort(llm=llm)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
