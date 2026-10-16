"""Identifier formats, each written once.

A tool checks a whole parameter with `exact(...)`. The keyword router finds one inside a question
with `mention(...)`: word-bounded, case-insensitive, and its first group is the whole match. The
router reads depots and sites more loosely than the tools accept (`DEPOT_MENTION`); what it finds
goes to the tool, which refuses a malformed one.
"""

from __future__ import annotations

import re

CASE_REF = r"FR-\d{4}-\d{3}"
EVIDENCE_REF = r"EV-\d{3}-\d{2}"
SERIAL = r"[A-Z]{2,4}(?:-[A-Z]{2,4})?-\d{3,5}"
DEPOT = r"DEP-[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8})?"
SITE = r"(?:DEP-[A-Z0-9]{1,8}|UAS-HANGAR)"  # a site's depot code has a single segment
RECORD_ID = r"REC-\d{3,6}"

DEPOT_MENTION = r"DEP-[A-Za-z0-9-]+"
SITE_MENTION = rf"(?:{DEPOT_MENTION}|UAS-HANGAR)"

CONTRACT_STATUSES = ("active", "at_risk", "completed")
# How a status reads in prose: "at risk", "at-risk".
CONTRACT_STATUS_MENTION = "|".join(s.replace("_", "[ -]") for s in CONTRACT_STATUSES)


def exact(pattern: str) -> re.Pattern[str]:
    """The whole value is the identifier (use with `.match`)."""
    return re.compile(f"^{pattern}$")


def mention(pattern: str, *, ignore_case: bool = True) -> re.Pattern[str]:
    """The identifier somewhere in free text, as a whole word; group 1 is the identifier."""
    return re.compile(rf"\b({pattern})\b", re.IGNORECASE if ignore_case else 0)
