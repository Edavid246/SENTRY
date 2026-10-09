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


def route_question(question: str) -> RoutedTool | None:
    """The data tool for a record-style request, or None (knowledge pathway)."""
    if _KNOWLEDGE_RE.search(question):
        return None
    if _FINDING_RE.search(question) or (_FAULT_RE.search(question) and _RISING_RE.search(question)):
        return RoutedTool("correlation_findings", {})
    if not _REQUEST_RE.search(question):
        return None
    params = _unit_path_params(question)
    # Contract rules come before the stock and UAS rules: "deliver" and "inventory" overlap.
    is_delivery = _DELIVERY_RE.search(question) and _OVERDUE_RE.search(question)
    if is_delivery or _CONTRACT_RE.search(question):
        client = _CLIENT_NAME_RE.search(question)
        if client:
            params["client"] = f"Client Agency {client.group(1).upper()}"
    if is_delivery:
        return RoutedTool("deliveries_overdue", params)
    if _CONTRACT_RE.search(question):
        status = _CONTRACT_STATUS_RE.search(question)
        if status:
            params["status"] = status.group(1).lower().replace(" ", "_").replace("-", "_")
        return RoutedTool("contracts_status", params)
    if _EQUIPMENT_RE.search(question) and _MAINTENANCE_RE.search(question):
        within = _WITHIN_RE.search(question)
        if within:
            params["within_days"] = int(within.group(1) or within.group(2))
        return RoutedTool("equipment_due_for_maintenance", params)
    if _CERT_RE.search(question) and _EXPIRED_RE.search(question):
        return RoutedTool("expired_certifications", params)
    if _TRAINING_RE.search(question) and _ACTIVITY_RE.search(question):
        period_days = _period_days(question)
        if period_days is not None:
            params["period_days"] = period_days
        return RoutedTool("training_activity", params)
    if _STOCK_RE.search(question) and _LOW_RE.search(question):
        depot = _DEPOT_RE.search(question)
        if depot:
            params["depot"] = depot.group(0).upper()
        return RoutedTool("stock_below_threshold", params)
    # The connected-tech rules read the question without unit paths: '/eib-group/briech/'
    # names a unit, not a UAS request.
    prose = _PATH_RE.sub(" ", question)
    if _DETECTION_RE.search(prose):
        site = _SITE_RE.search(question)
        if site:
            params["site"] = site.group(0).upper()
        hours = _HOURS_RE.search(question)
        if hours:
            params["period_hours"] = int(hours.group(1))
        return RoutedTool("detections_near_site", params)
    if _UAS_RE.search(prose):
        if _CANCELLED_RE.search(question):
            params["status"] = "cancelled"
        period_days = _period_days(question)
        this = _THIS_PERIOD_RE.search(question)
        if period_days is not None:
            params["period_days"] = period_days
        elif this:
            params["period_days"] = _PERIOD_DAYS[this.group(1).lower()]
        return RoutedTool("uas_missions", params)
    return None
