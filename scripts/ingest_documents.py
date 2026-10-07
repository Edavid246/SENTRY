"""Ingest the demo document corpus into the knowledge tables (SPEC §9.1).

Runs as the database owner: ingestion is a privileged background job, and the
runtime role has SELECT-only grants on documents/chunks. Idempotent — a
document whose file hash is unchanged and whose chunks are all embedded is
skipped.

Run:  uv run python scripts/ingest_documents.py
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.db import make_engine
from app.knowledge.ingest import ingest_documents

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = get_settings()
    engine = make_engine(settings.owner_database_url)
    try:
        results = ingest_documents(engine, REPO_ROOT / "data" / "documents")
    finally:
        engine.dispose()
    print(f"INGESTED {results}")


if __name__ == "__main__":
    main()
