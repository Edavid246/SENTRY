"""Forensic case workspace: cases, evidence items, custody events."""

from __future__ import annotations

import hashlib

from app.seed.records.common import _GIGA

# Forensic case workspace (Phase D). Fictitious cases for Giga Forensics, CASE/UCO style: a case
# holds evidence items, and each item has a chain of custody. Every record is FORENSICS-only and
# takes its case's classification, so a derived view inherits the highest of them. Dates are fixed
# (a custody trail is history, not a deadline). The sha256 values are hashes of the item reference,
# not of any real content. FR-2026-017 has a planted break: EV-017-01 reaches the lab from a
# courier who never took it from the examiner who last held it.
_FORENSIC = "forensics-demo"


def _case(ref, case_ref, title, opened, state, classification):
    data = {
        "case_ref": case_ref,
        "title": title,
        "opened": opened,
        "state": state,
        "lead_examiner": "A. Danjuma",
    }
    return (ref, "Case", _FORENSIC, classification, ["FORENSICS"], _GIGA, data)


def _evidence(ref, evidence_ref, case_ref, item, kind, status, classification):
    data = {
        "evidence_ref": evidence_ref,
        "case_ref": case_ref,
        "item": item,
        "kind": kind,
        "status": status,
        "sha256": hashlib.sha256(evidence_ref.encode()).hexdigest(),
        "format": "CASE/UCO style (synthetic)",
    }
    return (ref, "EvidenceItem", _FORENSIC, classification, ["FORENSICS"], _GIGA, data)


def _custody(ref, evidence_ref, case_ref, action, date, from_holder, to_holder, classification):
    data = {
        "evidence_ref": evidence_ref,
        "case_ref": case_ref,
        "action": action,
        "from_holder": from_holder,
        "to_holder": to_holder,
        "event_date": date,
        "format": "CASE/UCO style (synthetic)",
    }
    return (ref, "CustodyEvent", _FORENSIC, classification, ["FORENSICS"], _GIGA, data)


_FIELD_TEAM, _LS1, _LS2 = "Field team", "Lab store LS-1", "Lab store LS-2"
RECORDS = [
    _case(
        "REC-098",
        "FR-2026-017",
        "USB drive and router capture",
        "2026-08-19",
        "open",
        "confidential",
    ),
    _case(
        "REC-099",
        "FR-2026-009",
        "Server log archive review",
        "2026-04-02",
        "closed",
        "confidential",
    ),
    _evidence(
        "REC-100",
        "EV-014-02",
        "FR-2026-014",
        "Laptop disk image",
        "computer",
        "in analysis",
        "secret",
    ),
    _evidence(
        "REC-101",
        "EV-014-03",
        "FR-2026-014",
        "Cloud account export",
        "online account",
        "stored",
        "secret",
    ),
    _evidence(
        "REC-102",
        "EV-017-01",
        "FR-2026-017",
        "USB drive image",
        "storage media",
        "in lab",
        "confidential",
    ),
    _evidence(
        "REC-103",
        "EV-017-02",
        "FR-2026-017",
        "Router log capture",
        "network device",
        "in lab",
        "confidential",
    ),
    _evidence(
        "REC-104",
        "EV-009-01",
        "FR-2026-009",
        "Server log archive",
        "log archive",
        "returned",
        "confidential",
    ),
    _custody(
        "REC-105",
        "EV-014-01",
        "FR-2026-014",
        "seized",
        "2026-06-03",
        _FIELD_TEAM,
        "A. Danjuma",
        "secret",
    ),
    _custody(
        "REC-106",
        "EV-014-01",
        "FR-2026-014",
        "checked out for analysis",
        "2026-06-10",
        _LS1,
        "K. Eze",
        "secret",
    ),
    _custody(
        "REC-107",
        "EV-014-02",
        "FR-2026-014",
        "seized",
        "2026-06-03",
        _FIELD_TEAM,
        "A. Danjuma",
        "secret",
    ),
    _custody(
        "REC-108",
        "EV-014-02",
        "FR-2026-014",
        "transferred to lab",
        "2026-06-04",
        "A. Danjuma",
        _LS1,
        "secret",
    ),
    _custody(
        "REC-109",
        "EV-014-03",
        "FR-2026-014",
        "acquired remotely",
        "2026-06-12",
        "Provider portal",
        "K. Eze",
        "secret",
    ),
    _custody(
        "REC-110", "EV-014-03", "FR-2026-014", "stored", "2026-06-12", "K. Eze", _LS2, "secret"
    ),
    _custody(
        "REC-111",
        "EV-017-01",
        "FR-2026-017",
        "seized",
        "2026-08-19",
        _FIELD_TEAM,
        "A. Danjuma",
        "confidential",
    ),
    _custody(
        "REC-112",
        "EV-017-01",
        "FR-2026-017",
        "transferred to lab",
        "2026-08-22",
        "Courier R. Bala",
        _LS1,
        "confidential",
    ),
    _custody(
        "REC-113",
        "EV-017-02",
        "FR-2026-017",
        "seized",
        "2026-08-19",
        _FIELD_TEAM,
        "K. Eze",
        "confidential",
    ),
    _custody(
        "REC-114",
        "EV-017-02",
        "FR-2026-017",
        "transferred to lab",
        "2026-08-20",
        "K. Eze",
        _LS1,
        "confidential",
    ),
    _custody(
        "REC-115",
        "EV-009-01",
        "FR-2026-009",
        "seized",
        "2026-04-02",
        _FIELD_TEAM,
        "A. Danjuma",
        "confidential",
    ),
    _custody(
        "REC-116",
        "EV-009-01",
        "FR-2026-009",
        "transferred to lab",
        "2026-04-03",
        "A. Danjuma",
        _LS1,
        "confidential",
    ),
    _custody(
        "REC-117",
        "EV-009-01",
        "FR-2026-009",
        "returned to client",
        "2026-05-20",
        _LS1,
        "Client Agency D",
        "confidential",
    ),
]
