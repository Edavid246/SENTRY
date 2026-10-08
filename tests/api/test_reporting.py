"""Reporting pathway (SPEC 8.2 "Draft report", demo step 18.4): training-summary draft.

The model is a stub that reads the prompt it is given, so these prove what matters
without a key: the model only sees what the caller may see; the draft is marked DRAFT
and carries the derived label of every input; a draft citing something outside its
inputs is blocked; and the whole thing is audited with its provenance.
"""

from __future__ import annotations

import re

import pytest
from app.ai_gateway.base import LLMResult, ProviderUnavailableError
from app.data_queries.routing import route_question, route_report
from test_assistant_endpoints import _ask, _audit, _latest
from test_auth_endpoints import auth_header

REPORT_QUESTION = "Prepare a summary of training activity for this command over the last quarter."


class StubGateway:
    """Cites every record in the table and the first evidence chunk, like a good draft."""

    def __init__(self, *, cite_extra: str = "", fail: bool = False) -> None:
        self.prompts: list[str] = []
        self.cite_extra = cite_extra
        self.fail = fail

    def complete(self, request) -> LLMResult:
        if self.fail:
            raise ProviderUnavailableError("down")
        prompt = request.messages[-1].text
        self.prompts.append(prompt)
        records = sorted(set(re.findall(r"REC-\d{3,6}", prompt)))
        chunk = re.search(r"BEGIN EVIDENCE CHUNK ([0-9a-f-]{36})", prompt)
        lines = ["SUMMARY", "Stub summary.", "", "ACTIVITY IN THE PERIOD"]
        lines += [f"Event ({r})." for r in records]
        lines += ["", "APPLICABLE REQUIREMENTS"]
        if chunk:
            lines.append(f"Requirement [{chunk.group(1)}: Training Directive, page 1].")
        lines.append(self.cite_extra)
        return LLMResult(text="\n".join(lines), provider="stub", model="stub-1")


@pytest.fixture
def gateway(models) -> StubGateway:
    stub = StubGateway()
    models(stub)
    return stub


def _report(client, username: str, question: str = REPORT_QUESTION):
    response = _ask(client, username, question)
    assert response.status_code == 200, response.text
    return response.json()


def test_bello_gets_a_marked_draft_with_the_derived_label(client, gateway) -> None:
    body = _report(client, "a.bello")
    assert body["report"]["draft"] is True
    assert set(body["report"]["record_ids"]) == {"REC-002", "REC-043", "REC-044"}
    assert body["report"]["classification_code"] in {"confidential", "secret"}
    assert "UAS-OPS" in body["report"]["compartments"]  # REC-044 is a UAS-OPS record
    assert body["answer"].startswith("DRAFT FOR HUMAN REVIEW")
    assert "Classification: " + body["report"]["classification_code"].upper() in body["answer"]
    assert "SOURCES (all demo data)" in body["answer"]
    assert body["found"] is True and body["refused"] is False
    assert {c["chunk_id"] for c in body["citations"]}  # a cited document passage
    assert {row["id"] for row in body["result_table"]["rows"]} == {"REC-002", "REC-043", "REC-044"}


def test_adeyemi_draft_is_smaller_and_the_model_never_saw_uas_ops(client, gateway) -> None:
    body = _report(client, "t.adeyemi")
    assert body["report"]["record_ids"] == ["REC-002"]
    assert "UAS-OPS" not in body["report"]["compartments"]
    assert body["report"]["classification_code"] in {"unclassified", "restricted"}
    prompt = gateway.prompts[-1]
    assert "REC-044" not in prompt and "REC-043" not in prompt
    assert "UAS-OPS" not in prompt and "UAS Wing" not in prompt
    # Her evidence is limited too: the confidential Q3 readiness summary never reaches the model.
    assert "Training Readiness Summary Q3" not in prompt
    assert "Training Readiness Summary Q3" in str(
        _report(client, "a.bello") and gateway.prompts[-1]
    )


def test_a_citation_outside_the_inputs_blocks_the_draft(client, models) -> None:
    stub = StubGateway(cite_extra="Also (REC-999).")
    models(stub)
    body = _report(client, "t.adeyemi")
    assert body["refused"] is True and body["found"] is False
    assert "Draft blocked" in body["answer"]
    assert body["citations"] == []
    assert "REC-999" not in body["answer"]


def test_a_fabricated_chunk_citation_blocks_the_draft(client, models) -> None:
    fake = "[00000000-0000-0000-0000-000000000000: Fake, page 1]"
    stub = StubGateway(cite_extra=fake)
    models(stub)
    assert _report(client, "a.bello")["refused"] is True


def test_model_outage_is_a_503_and_nothing_is_invented(client, models) -> None:
    stub = StubGateway(fail=True)
    models(stub)
    assert _ask(client, "a.bello", REPORT_QUESTION).status_code == 503


@pytest.mark.parametrize("username", ["s.eze", "f.danjuma"])
def test_roles_without_data_access_are_refused(client, gateway, username) -> None:
    assert _ask(client, username, REPORT_QUESTION).status_code == 403
    assert gateway.prompts == []


def test_report_is_audited_with_its_provenance(client, gateway) -> None:
    body = _report(client, "t.adeyemi")
    events = _audit(client)
    answer = _latest(events, actor="t.adeyemi", action="answer", pathway="report")
    payload = answer["payload"]
    assert payload["record_ids"] == ["REC-002"]
    assert payload["classification"] == body["report"]["classification_code"]
    assert payload["provider"] == "stub" and payload["blocked"] is False
    assert set(payload["citations"]) <= set(payload["chunk_ids"])
    retrieval = _latest(events, actor="t.adeyemi", action="retrieve")
    assert retrieval["seq"] < answer["seq"]
    assert "REC-044" not in str(payload)


def test_stored_conversation_inherits_the_derived_label(client, gateway) -> None:
    body = _report(client, "a.bello")
    detail = client.get(
        f"/api/v1/assistant/conversations/{body['conversation_id']}",
        headers=auth_header(client, "a.bello"),
    ).json()
    assert detail["classification_code"] == body["report"]["classification_code"]
    assert "UAS-OPS" in detail["compartments"]


def test_report_routing_is_only_for_drafting_requests() -> None:
    routed = route_report(REPORT_QUESTION)
    assert routed is not None and routed.kind == "training_summary"
    assert routed.params == {"period_days": 90}
    assert route_report("Draft a summary of training activity in the last 30 days").params == {
        "period_days": 30
    }
    # Plain data requests and other report subjects are untouched.
    assert route_report("Show me the training activity over the last quarter") is None
    assert route_report("Prepare a report on equipment awaiting maintenance") is None
    assert route_question("Show me the training activity over the last quarter") is not None
