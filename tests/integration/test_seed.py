"""Seed tests: corpus counts, idempotency, invariants and demo credentials.

Gold visibility sets live in tests/authz/expected.py (step 4); these tests
only prove the corpus itself is well-formed.
"""

from app.authz.models import (
    ClassificationLevel,
    Compartment,
    Unit,
    User,
    UserCompartment,
)
from app.connectors.models import CanonicalRecord, SourceSystem
from app.knowledge.models import Chunk, Document
from app.seed import DEMO_PASSWORD, _rows
from argon2 import PasswordHasher
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine

EXPECTED_COUNTS = {
    ClassificationLevel: 4,
    Compartment: 6,
    Unit: 8,
    User: 6,
    UserCompartment: 8,
    SourceSystem: 8,
    Document: 16,
    Chunk: 32,
    CanonicalRecord: 97,
}


def _counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            table.__name__: conn.execute(select(func.count()).select_from(table)).scalar_one()
            for table in EXPECTED_COUNTS
        } | {
            "AuditEvent": conn.execute(
                select(func.count()).select_from(text("audit_events"))
            ).scalar_one()
        }


def test_seed_corpus_counts(seeded: None, owner_engine: Engine, settings) -> None:
    from app.seed import run as run_seed

    audit_before = _counts(owner_engine)["AuditEvent"]
    run_seed(settings.test_owner_database_url)
    counts = _counts(owner_engine)
    for table, expected in EXPECTED_COUNTS.items():
        assert counts[table.__name__] == expected, table.__name__
    # Seed never writes audit (append-only). The API tests write real audit
    # events earlier in the session, so prove it by count delta, not by 0.
    assert counts["AuditEvent"] == audit_before


def test_seed_is_idempotent(seeded: None, owner_engine: Engine, settings) -> None:
    from app.seed import run as run_seed

    before = _counts(owner_engine)
    run_seed(settings.test_owner_database_url)
    after = _counts(owner_engine)
    assert after == before


def test_chunks_inherit_parent_document_markings(seeded: None, owner_engine: Engine) -> None:
    """Approved amendment: chunk classification/compartments/unit must equal
    the parent document's — the derived-item inheritance rule at its base."""
    with owner_engine.connect() as conn:
        violations = conn.execute(
            text(
                "SELECT count(*) FROM chunks ch JOIN documents d ON d.id = ch.document_id "
                "WHERE ch.classification_code IS DISTINCT FROM d.classification_code "
                "OR ch.unit_id IS DISTINCT FROM d.unit_id "
                "OR ch.compartments IS DISTINCT FROM d.compartments"
            )
        ).scalar()
    assert violations == 0


def test_maintenance_keyword_hits_exactly_three_chunks(seeded: None, owner_engine: Engine) -> None:
    """The retrieval demo's planted match: exactly one 'maintenance' chunk in
    each of DOC-001/DOC-006/DOC-013 and nowhere else."""
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT d.source_ref, count(*) FROM chunks ch "
                "JOIN documents d ON d.id = ch.document_id "
                "WHERE ch.text ILIKE '%maintenance%' AND d.source_ref LIKE 'DOC-0%' "
                "GROUP BY d.source_ref ORDER BY d.source_ref"
            )
        ).all()
    assert rows == [("DOC-001", 1), ("DOC-006", 1), ("DOC-013", 1)]


def test_demo_user_scopes_and_clearances(seeded: None, owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT username, data_scope, clearance_code FROM users ORDER BY username")
        ).all()
    assert rows == [
        ("briech.lead", "standard", "confidential"),
        ("coo", "standard", "restricted"),
        ("group.audit", "audit", "restricted"),
        ("group.it", "none", None),
        ("logistics.head", "standard", "confidential"),
        ("owner", "standard", "secret"),
    ]


def test_demo_password_verifies_for_every_user(seeded: None, owner_engine: Engine) -> None:
    hasher = PasswordHasher()
    with owner_engine.connect() as conn:
        hashes = conn.execute(text("SELECT password_hash FROM users")).scalars().all()
    assert len(hashes) == 6
    for pw_hash in hashes:
        assert hasher.verify(pw_hash, DEMO_PASSWORD) is True


def test_content_hashes_are_stable(seeded: None, owner_engine: Engine) -> None:
    """Deterministic uuid5 ids + content hashes: reseeding cannot drift."""
    doc_rows = _rows()[Document]
    expected = {r["source_ref"]: r["content_hash"] for r in doc_rows}
    with owner_engine.connect() as conn:
        actual = dict(conn.execute(text("SELECT source_ref, content_hash FROM documents")).all())
    assert actual == expected
    assert all(len(value) == 64 for value in expected.values())
