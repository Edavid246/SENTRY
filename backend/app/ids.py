"""Deterministic ids for demo entities (uuid5), shared by the seed and document ingest.

Both must derive the same unit and source-system ids, or ingested documents stop joining to
seeded units. One definition keeps them in step.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5


def entity_id(kind: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"defence-gateway:{kind}")


def unit_id(path: str) -> UUID:
    return entity_id(f"unit:{path}")


def source_id(name: str) -> UUID:
    return entity_id(f"source-system:{name}")
