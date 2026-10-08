"""A fake model for the API tests: answers each pathway's prompt like a well-behaved model.

It is installed at the model seam (`app.api.deps.get_models`, see the `models`
fixture in conftest.py), so the real pathway code runs around it: the evidence
builder, the citation guard, the explanation and report assembly.
"""

from __future__ import annotations

import json
import re

from app.ai_gateway.base import LLMRequest, LLMResult

_CHUNK_RE = re.compile(r"BEGIN EVIDENCE CHUNK ([0-9a-f-]{36})")
OUTSIDE_CHUNK = "00000000-0000-0000-0000-000000000000"


class FakeLLM:
    """`knowledge` picks the knowledge-pathway behaviour:

    * "cite_first": cite the first evidence passage with a real marker;
    * "cite_outside": cite a chunk that was never given (the guard must block it).
    `fail` raises that error on every call (provider down / not configured).
    """

    def __init__(self, *, knowledge: str = "cite_first", fail: Exception | None = None) -> None:
        self.knowledge = knowledge
        self.fail = fail
        self.requests: list[LLMRequest] = []
        self.explained: list[str] = []  # tool of every result the model was asked to explain
        self.explained_rows: list[dict] = []

    def complete(self, request: LLMRequest) -> LLMResult:
        self.requests.append(request)
        if self.fail is not None:
            raise self.fail
        prompt = request.messages[-1].text
        if "QUERY RESULT" in prompt:
            text = self._explain(prompt)
        elif "TRAINING TABLE" in prompt:
            text = self._report(prompt)
        else:
            text = self._answer(prompt)
        return LLMResult(text=text, provider="stub", model="stub-1")

    def _explain(self, prompt: str) -> str:
        payload = json.loads(prompt.split("\n", 3)[3].rsplit("\n\nExplain", 1)[0])
        self.explained.append(payload["tool"])
        self.explained_rows.extend(payload["rows"])
        return f"Stub: {len(payload['rows'])} record(s) from {payload['tool']}."

    def _report(self, prompt: str) -> str:
        records = sorted(set(re.findall(r"REC-\d{3,6}", prompt)))
        lines = ["SUMMARY", "Stub summary.", "", "ACTIVITY IN THE PERIOD"]
        lines += [f"Event ({r})." for r in records]
        lines += ["", "APPLICABLE REQUIREMENTS"]
        if chunk := _CHUNK_RE.search(prompt):
            lines.append(f"Requirement [{chunk.group(1)}: Training Directive, page 1].")
        return "\n".join(lines)

    def _answer(self, prompt: str) -> str:
        question = prompt.split("\n", 1)[0].removeprefix("Question: ")
        if self.knowledge == "cite_outside":
            return f"See [{OUTSIDE_CHUNK}: Secret Plan, page 9]."
        chunk = _CHUNK_RE.search(prompt)
        cite = f" [{chunk.group(1)}: demo, page 1]" if chunk else ""
        return f"Stub answer for: {question}{cite}"
