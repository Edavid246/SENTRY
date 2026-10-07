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
_REQUEST_RE = re.compile(r"\b(show|list|display|which|give me|how many|what)\b", re.IGNORECASE)
_EQUIPMENT_RE = re.compile(r"\bequipment\b", re.IGNORECASE)
_MAINTENANCE_RE = re.compile(r"\b(maintenance|servicing|service)\b", re.IGNORECASE)
_CERT_RE = re.compile(r"\b(certifications?|certificates?|qualifications?)\b", re.IGNORECASE)
_EXPIRED_RE = re.compile(r"\b(expired|expire|expires|lapsed)\b", re.IGNORECASE)
_STOCK_RE = re.compile(
    r"\b(stock|inventory|supplies|spares?|spare parts?|shortages?)\b", re.IGNORECASE
)
_LOW_RE = re.compile(r"\b(below|low|short|shortages?|under|depleted|running out)\b", re.IGNORECASE)
_DEPOT_RE = re.compile(r"\bDEP-[A-Za-z0-9-]+\b", re.IGNORECASE)
_WITHIN_RE = re.compile(
    r"\b(?:within|in|over)\s+(?:the\s+)?(?:next\s+)?(\d{1,6})\s+days?\b|"
    r"\bnext\s+(\d{1,6})\s+days?\b",
    re.IGNORECASE,
)
_PATH_RE = re.compile(r"(?<![\w])(?:\.\.?/|/)[\w./-]+")


@dataclass(frozen=True, slots=True)
class RoutedTool:
    tool: str
    params: dict[str, Any]


def route_question(question: str) -> RoutedTool | None:
    """The data tool for a record-style request, or None (knowledge pathway)."""
    if _KNOWLEDGE_RE.search(question) or not _REQUEST_RE.search(question):
        return None
    params: dict[str, Any] = {}
    path = _PATH_RE.search(question)
    if path:
        params["unit_path"] = path.group(0).rstrip(".,;:)")
    if _EQUIPMENT_RE.search(question) and _MAINTENANCE_RE.search(question):
        within = _WITHIN_RE.search(question)
        if within:
            params["within_days"] = int(within.group(1) or within.group(2))
        return RoutedTool("equipment_due_for_maintenance", params)
    if _CERT_RE.search(question) and _EXPIRED_RE.search(question):
        return RoutedTool("expired_certifications", params)
    if _STOCK_RE.search(question) and _LOW_RE.search(question):
        depot = _DEPOT_RE.search(question)
        if depot:
            params["depot"] = depot.group(0).upper()
        return RoutedTool("stock_below_threshold", params)
    return None
