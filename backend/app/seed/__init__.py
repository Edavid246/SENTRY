"""Seed the gateway database with the fictitious demo corpus (AGENTS.md).

Deterministic uuid5 ids plus a full delete-then-insert make the seed idempotent: running it twice
leaves identical row counts. The audit table is never touched (append-only, SPEC 14.2). Demo data
only: fictitious people, units, documents and records.

  identity.py        levels, compartments, units, users, source systems, documents
  records/           the demo records, one module per domain (records/__init__ orders them)
  loader.py          turns the above into rows and replaces the corpus atomically

Run:  uv run python -m app.seed            (main gateway DB, as owner)
Tests: app.seed.run(test_owner_database_url)
"""

from app.seed.identity import DEMO_PASSWORD
from app.seed.loader import _id, _rows, main, run
from app.seed.records import RECORDS
from app.seed.records.common import _days_from_today

__all__ = ["DEMO_PASSWORD", "RECORDS", "_days_from_today", "_id", "_rows", "main", "run"]
