"""Deterministic keyword router for the demo (docs/PRODUCTION_DEBT.md).

SPEC 8.2 has the model select the tool; the demo routes by keyword instead,
which keeps the data path predictable and keeps model output out of the
authorization decision. Routing is conservative: only record-style requests
reach a tool, and anything that mentions a document, policy, directive, SOP or
manual always goes to the knowledge pathway.

Parameter extraction is equally literal: a path-looking token becomes
`unit_path` and is handed to the tool unchanged, so a hostile value such as
"../../secret" reaches the tool's validation and is refused there, not
silently dropped here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_KNOWLEDGE_RE = re.compile(
    r"\b(documents?|policy|policies|directives?|sops?|manuals?|procedures?|"
    r"regulations?|guidelines?)\b",
    re.IGNORECASE,
)
_REQUEST_RE = re.compile(
    r"\b(show|list|display|which|give me|how many|what|prepare|summar\w+)\b", re.IGNORECASE
)
_EQUIPMENT_RE = re.compile(r"\bequipment\b", re.IGNORECASE)
_MAINTENANCE_RE = re.compile(r"\b(maintenance|servicing|service)\b", re.IGNORECASE)
_CERT_RE = re.compile(r"\b(certifications?|certificates?|qualifications?)\b", re.IGNORECASE)
_EXPIRED_RE = re.compile(r"\b(expired|expire|expires|lapsed)\b", re.IGNORECASE)
_STOCK_RE = re.compile(
    r"\b(stock|inventory|supplies|spares?|spare parts?|shortages?)\b", re.IGNORECASE
)
_LOW_RE = re.compile(r"\b(below|low|short|shortages?|under|depleted|running out)\b", re.IGNORECASE)
_DEPOT_RE = re.compile(r"\bDEP-[A-Za-z0-9-]+\b", re.IGNORECASE)
_FINDING_RE = re.compile(r"\b(findings?|correlations?)\b", re.IGNORECASE)
_FAULT_RE = re.compile(r"\bfaults?\b", re.IGNORECASE)
_RISING_RE = re.compile(
    r"\b(rising|rise|rose|increas\w+|spiking|growing|trend\w*)\b", re.IGNORECASE
)
_TRAINING_RE = re.compile(r"\b(training|courses?)\b", re.IGNORECASE)
_ACTIVITY_RE = re.compile(r"\b(activity|activities|events?|sessions?|summary)\b", re.IGNORECASE)
_PERIOD_RE = re.compile(
    r"\b(?:last|past)\s+(?:(\d{1,6})\s+days?|(quarter|month|week|year))\b", re.IGNORECASE
)
_PERIOD_DAYS = {"week": 7, "month": 30, "quarter": 90, "year": 365}
_WITHIN_RE = re.compile(
    r"\b(?:within|in|over)\s+(?:the\s+)?(?:next\s+)?(\d{1,6})\s+days?\b|"
    r"\bnext\s+(\d{1,6})\s+days?\b",
    re.IGNORECASE,
)
_UAS_RE = re.compile(r"\b(uas|drones?|uavs?|missions?|flights?)\b", re.IGNORECASE)
_CANCELLED_RE = re.compile(r"\b(cancell?ed|aborted|scrubbed)\b", re.IGNORECASE)
_DETECTION_RE = re.compile(
    r"\b(detections?|detected|sightings?|surveillance|sensors?)\b", re.IGNORECASE
)
_SITE_RE = re.compile(r"\b(DEP-[A-Za-z0-9-]+|UAS-HANGAR)\b", re.IGNORECASE)
_HOURS_RE = re.compile(r"\b(?:last|past)\s+(\d{1,4})\s+hours?\b", re.IGNORECASE)
_THIS_PERIOD_RE = re.compile(r"\bthis\s+(week|month)\b", re.IGNORECASE)
_DELIVERY_RE = re.compile(r"\b(deliver\w*|shipments?)\b", re.IGNORECASE)
_OVERDUE_RE = re.compile(r"\b(overdue|late|delayed|behind schedule|past due)\b", re.IGNORECASE)
_CONTRACT_RE = re.compile(r"\bcontracts?\b", re.IGNORECASE)
_CLIENT_NAME_RE = re.compile(r"\bClient Agency ([A-Z])\b", re.IGNORECASE)
_CONTRACT_STATUS_RE = re.compile(r"\b(at[ -]risk|active|completed)\b", re.IGNORECASE)
_SERIAL_WORD_RE = re.compile(r"\b(serial|trace|traceability|provenance)\b", re.IGNORECASE)
_SERIAL_NO_RE = re.compile(r"\b([A-Z]{2,4}(?:-[A-Z]{2,4})?-\d{3,5})\b", re.IGNORECASE)
_HOLD_RE = re.compile(r"\bholds?\b", re.IGNORECASE)
_PRODUCTION_RE = re.compile(r"\b(qc|quality|production|batch(?:es)?|lots?|runs?)\b", re.IGNORECASE)
_CUSTODY_RE = re.compile(r"\bcustody\b", re.IGNORECASE)
_EVIDENCE_PROSE_RE = re.compile(
    r"\b(answers?|citations?|sources?|reports?|training|reasoning|basis|summary)\b|summar\w+",
    re.IGNORECASE,
)
_CUSTODY_BREAK_RE = re.compile(
    r"\b(breaks?|broken|gaps?|discrepanc\w+|unexplained|inconsisten\w+)\b", re.IGNORECASE
)
_EVIDENCE_NO_RE = re.compile(r"\bEV-\d{3}-\d{2}\b", re.IGNORECASE)
_CASE_NO_RE = re.compile(r"\bFR-\d{4}-\d{3}\b", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"\bevidence\b", re.IGNORECASE)
_CASES_RE = re.compile(
    r"\b(forensic|forensics)\b.*\bcases?\b|\bcases?\b.*\bforensic", re.IGNORECASE
)
_PATH_RE = re.compile(r"(?<![\w])(?:\.\.?/|/)[\w./-]+")


_DRAFT_RE = re.compile(r"\b(prepare|draft|write|compile|produce|generate)\b", re.IGNORECASE)
_REPORT_RE = re.compile(r"\b(report|summary)\b", re.IGNORECASE)


def _unit_path_params(question: str) -> dict[str, Any]:
    path = _PATH_RE.search(question)
    return {"unit_path": path.group(0).rstrip(".,;:)")} if path else {}


def _period_days(question: str) -> int | None:
    period = _PERIOD_RE.search(question)
    if period is None:
        return None
    return int(period.group(1)) if period.group(1) else _PERIOD_DAYS[period.group(2).lower()]


@dataclass(frozen=True, slots=True)
class RoutedTool:
    tool: str
    params: dict[str, Any]


def route_report(question: str) -> RoutedTool | None:
    """A request to draft a training-summary report (the tool it drafts from), or None.

    Asking to prepare/draft a report or summary of training activity is the reporting
    pathway; "show training events" stays a plain data query (route_question).
    """
    if not (_DRAFT_RE.search(question) and _REPORT_RE.search(question)):
        return None
    if not (_TRAINING_RE.search(question) and _ACTIVITY_RE.search(question)):
        return None
    params = _unit_path_params(question)
    period_days = _period_days(question)
    if period_days is not None:
        params["period_days"] = period_days
    return RoutedTool("training_activity", params)


@dataclass(frozen=True, slots=True)
class _Question:
    """A question as the rules read it."""

    text: str
    unit: dict[str, Any]  # the `unit_path` parameter, if the question names a unit

    @property
    def prose(self) -> str:
        """The question without unit paths: '/eib-group/briech/' names a unit, not a UAS request."""
        return _PATH_RE.sub(" ", self.text)

    def has(self, pattern: re.Pattern[str]) -> bool:
        return pattern.search(self.text) is not None

    def tool(self, name: str, **params: Any) -> RoutedTool:
        return RoutedTool(name, {**self.unit, **params})


Rule = Callable[[_Question], RoutedTool | None]


def _custody_trail(q: _Question) -> RoutedTool | None:
    evidence_no = _EVIDENCE_NO_RE.search(q.text)
    return (
        q.tool("custody_trail", evidence_ref=evidence_no.group(0).upper()) if evidence_no else None
    )


def _custody_gaps(q: _Question) -> RoutedTool | None:
    return q.tool("custody_gaps") if q.has(_CUSTODY_BREAK_RE) else None


def _case_ref(q: _Question) -> dict[str, str]:
    case_no = _CASE_NO_RE.search(q.text)
    return {"case_ref": case_no.group(0).upper()} if case_no else {}


def _evidence_items(q: _Question) -> RoutedTool | None:
    # "evidence" is also ordinary prose ("the evidence behind this answer"): without a case number
    # it must read as a forensic record request, not as talk about an answer.
    if not (q.has(_EVIDENCE_RE) and q.has(_REQUEST_RE)):
        return None
    case = _case_ref(q)
    if q.has(_EVIDENCE_PROSE_RE) and not case:
        return None
    return q.tool("evidence_items", **case)


def _forensic_cases(q: _Question) -> RoutedTool | None:
    case = _case_ref(q)
    named_case = bool(case) and "case" in q.text.lower()
    if q.has(_REQUEST_RE) and (q.has(_CASES_RE) or named_case):
        return q.tool("forensic_cases", **case)
    return None


def _serial_trace(q: _Question) -> RoutedTool | None:
    serial = _SERIAL_NO_RE.search(q.text)
    if serial and q.has(_SERIAL_WORD_RE):
        return q.tool("serial_trace", serial=serial.group(1).upper())
    return None


def _production_holds(q: _Question) -> RoutedTool | None:
    return q.tool("production_qc_holds") if q.has(_HOLD_RE) and q.has(_PRODUCTION_RE) else None


def _client(q: _Question) -> dict[str, str]:
    client = _CLIENT_NAME_RE.search(q.text)
    return {"client": f"Client Agency {client.group(1).upper()}"} if client else {}


# Contract rules come before the stock and UAS rules: "deliver" and "inventory" overlap.
def _deliveries(q: _Question) -> RoutedTool | None:
    if q.has(_DELIVERY_RE) and q.has(_OVERDUE_RE):
        return q.tool("deliveries_overdue", **_client(q))
    return None


def _contracts(q: _Question) -> RoutedTool | None:
    if not q.has(_CONTRACT_RE):
        return None
    status = _CONTRACT_STATUS_RE.search(q.text)
    params: dict[str, Any] = _client(q)
    if status:
        params["status"] = status.group(1).lower().replace(" ", "_").replace("-", "_")
    return q.tool("contracts_status", **params)


def _maintenance(q: _Question) -> RoutedTool | None:
    if not (q.has(_EQUIPMENT_RE) and q.has(_MAINTENANCE_RE)):
        return None
    within = _WITHIN_RE.search(q.text)
    return q.tool(
        "equipment_due_for_maintenance",
        **({"within_days": int(within.group(1) or within.group(2))} if within else {}),
    )


def _certifications(q: _Question) -> RoutedTool | None:
    return q.tool("expired_certifications") if q.has(_CERT_RE) and q.has(_EXPIRED_RE) else None


def _training(q: _Question) -> RoutedTool | None:
    if not (q.has(_TRAINING_RE) and q.has(_ACTIVITY_RE)):
        return None
    period_days = _period_days(q.text)
    return q.tool(
        "training_activity", **({} if period_days is None else {"period_days": period_days})
    )


def _stock(q: _Question) -> RoutedTool | None:
    if not (q.has(_STOCK_RE) and q.has(_LOW_RE)):
        return None
    depot = _DEPOT_RE.search(q.text)
    return q.tool("stock_below_threshold", **({"depot": depot.group(0).upper()} if depot else {}))


# The connected-tech rules read the question without unit paths.
def _detections(q: _Question) -> RoutedTool | None:
    if _DETECTION_RE.search(q.prose) is None:
        return None
    params: dict[str, Any] = {}
    if site := _SITE_RE.search(q.text):
        params["site"] = site.group(0).upper()
    if hours := _HOURS_RE.search(q.text):
        params["period_hours"] = int(hours.group(1))
    return q.tool("detections_near_site", **params)


def _missions(q: _Question) -> RoutedTool | None:
    if _UAS_RE.search(q.prose) is None:
        return None
    params: dict[str, Any] = {}
    if q.has(_CANCELLED_RE):
        params["status"] = "cancelled"
    this = _THIS_PERIOD_RE.search(q.text)
    period_days = _period_days(q.text)
    if period_days is not None:
        params["period_days"] = period_days
    elif this:
        params["period_days"] = _PERIOD_DAYS[this.group(1).lower()]
    return q.tool("uas_missions", **params)


# Tried in order, first hit wins; the order is part of the behavior.
# Custody rules run when the question says "custody" even without a request verb.
_CUSTODY_RULES: tuple[Rule, ...] = (_custody_trail, _custody_gaps)
# Forensic rules come before the serial rule: "EV-014-01" looks like a serial number.
_REQUEST_RULES: tuple[Rule, ...] = (
    _evidence_items,
    _forensic_cases,
    _serial_trace,
    _production_holds,
    _deliveries,
    _contracts,
    _maintenance,
    _certifications,
    _training,
    _stock,
    _detections,
    _missions,
)


def route_question(question: str) -> RoutedTool | None:
    """The data tool for a record-style request, or None (knowledge pathway)."""
    if _KNOWLEDGE_RE.search(question):
        return None
    if _FINDING_RE.search(question) or (_FAULT_RE.search(question) and _RISING_RE.search(question)):
        return RoutedTool("correlation_findings", {})
    is_request = bool(_REQUEST_RE.search(question) or _SERIAL_WORD_RE.search(question))
    is_custody = bool(_CUSTODY_RE.search(question))
    if not (is_request or is_custody):
        return None
    q = _Question(question, _unit_path_params(question))
    # "custody" alone opens the gate; with no EV number and no break word it is a knowledge
    # question, not a record request.
    rules = (_CUSTODY_RULES if is_custody else ()) + (_REQUEST_RULES if is_request else ())
    return next((routed for rule in rules if (routed := rule(q)) is not None), None)
