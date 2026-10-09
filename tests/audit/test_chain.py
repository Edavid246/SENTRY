"""Hash chain, checkpoint file, and git ledger tamper evidence (SPEC 14).

Every tampering test restores the original rows in a `finally` block so the
shared gateway_test chain stays clean for the next test — deletion, hash
flips, and a full re-chain are all exercised and then undone.

The suite also proves the two failure modes the demo must distinguish:
- a tamper that re-hashes every downstream row is still caught (contiguity)
- tail truncation leaves a DB-valid chain while checkpoint_ok/ledger_ok go false
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any

import pytest
from app.audit.chain import (
    GENESIS_PREV_HASH,
    append_events,
    canonical_json,
    checkpoint_status,
    compute_hash,
    ledger_status,
    verify_chain,
    verify_report,
)
from app.config import get_settings
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.usefixtures("migrated")


def _count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one())


def _append(engine: Engine, amount: int, actor: str = "chain-test") -> list[dict[str, Any]]:
    payloads = [
        {"actor": actor, "action": "test", "resource": "audit", "decision": "allow", "n": i}
        for i in range(amount)
    ]
    return append_events(engine, payloads)


def _fetch(engine: Engine, seq: int) -> dict[str, Any]:
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT seq, event_id, payload, prev_hash, hash"
                    " FROM audit_events WHERE seq = :seq"
                ),
                {"seq": seq},
            )
            .mappings()
            .first()
        )
    assert row is not None, f"row {seq} missing"
    return dict(row)


def _restore(engine: Engine, rows: list[dict[str, Any]]) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_events (seq, event_id, payload, prev_hash, hash)"
                " VALUES (:seq, :event_id, CAST(:payload AS jsonb), :prev_hash, :hash)"
            ),
            [{**row, "payload": canonical_json(row["payload"])} for row in rows],
        )


def test_canonical_json_is_sorted_and_compact() -> None:
    assert canonical_json({"b": 1, "a": [2, 1]}) == '{"a":[2,1],"b":1}'


def test_genesis_hash_format() -> None:
    payload = {"action": "login", "actor": "owner"}
    expected = hashlib.sha256((GENESIS_PREV_HASH + canonical_json(payload)).encode()).hexdigest()
    assert compute_hash(GENESIS_PREV_HASH, payload) == expected
    assert len(expected) == 64


def test_append_batches_chain_cleanly(app_engine: Engine) -> None:
    base = _count(app_engine)
    first = _append(app_engine, 3, actor="chain-a")
    second = _append(app_engine, 4, actor="chain-b")
    rows = first + second
    assert [row["seq"] for row in rows] == list(range(base + 1, base + 8))
    if base == 0:
        assert rows[0]["prev_hash"] == GENESIS_PREV_HASH
    for previous, current in zip(rows[:-1], rows[1:], strict=True):
        assert current["prev_hash"] == previous["hash"]
    valid, broken = verify_chain(app_engine)
    assert (valid, broken) == (True, None)


def test_byte_flip_is_detected_and_restored(app_engine: Engine, owner_engine: Engine) -> None:
    rows = _append(app_engine, 2, actor="flip")
    target = rows[-1]
    flipped = "0" if target["hash"][-1] != "0" else "1"
    try:
        with owner_engine.begin() as conn:
            conn.execute(
                text("UPDATE audit_events SET hash = :hash WHERE seq = :seq"),
                {"hash": target["hash"][:-1] + flipped, "seq": target["seq"]},
            )
        assert verify_chain(app_engine) == (False, target["seq"])
    finally:
        with owner_engine.begin() as conn:
            conn.execute(
                text("UPDATE audit_events SET hash = :hash WHERE seq = :seq"),
                {"hash": target["hash"], "seq": target["seq"]},
            )
    assert verify_chain(app_engine) == (True, None)


def test_verify_report_names_the_first_bad_event(app_engine: Engine, owner_engine: Engine) -> None:
    """The viewer-facing verify contract: a healthy report, then one that
    pins the deep-linkable event_id of the first tampered row."""
    healthy = verify_report(app_engine)
    assert healthy["valid"] is True
    assert healthy["first_bad_event_id"] is None
    assert healthy["checked_count"] == _count(app_engine)

    rows = _append(app_engine, 2, actor="report")
    # Flip a row that is not a checkpoint/ledger tip: those layers store the
    # tip row's hash, so tampering with the tip would (correctly) break them
    # too. This proves a plain payload/hash edit is caught by the chain walk
    # alone, leaving the external layers green.
    _, checkpoint_tip = checkpoint_status(app_engine)
    _, ledger_tip = ledger_status(app_engine)
    tip_seqs = {tip["seq"] for tip in (checkpoint_tip, ledger_tip) if tip is not None}
    candidates = [row for row in rows if row["seq"] not in tip_seqs]
    target = candidates[0] if candidates else rows[-1]
    flipped = "0" if target["hash"][-1] != "0" else "1"
    try:
        with owner_engine.begin() as conn:
            conn.execute(
                text("UPDATE audit_events SET hash = :hash WHERE seq = :seq"),
                {"hash": target["hash"][:-1] + flipped, "seq": target["seq"]},
            )
        broken = verify_report(app_engine)
        assert broken["valid"] is False
        assert broken["first_bad_event_id"] == target["event_id"]
        assert broken["checked_count"] == _count(app_engine)
        if candidates:
            assert broken["checkpoint_ok"] is healthy["checkpoint_ok"]
            assert broken["ledger_ok"] is healthy["ledger_ok"]
    finally:
        with owner_engine.begin() as conn:
            conn.execute(
                text("UPDATE audit_events SET hash = :hash WHERE seq = :seq"),
                {"hash": target["hash"], "seq": target["seq"]},
            )
    restored = verify_report(app_engine)
    assert restored["valid"] is True
    assert restored["first_bad_event_id"] is None


def test_middle_delete_is_detected_and_restored(app_engine: Engine, owner_engine: Engine) -> None:
    rows = _append(app_engine, 3, actor="delete")
    victim = rows[1]
    try:
        with owner_engine.begin() as conn:
            conn.execute(text("DELETE FROM audit_events WHERE seq = :seq"), {"seq": victim["seq"]})
        # The first surviving row after the gap reports the break.
        assert verify_chain(app_engine) == (False, victim["seq"] + 1)
    finally:
        _restore(app_engine, [victim])
    assert verify_chain(app_engine) == (True, None)


def test_full_rechain_is_still_caught_by_contiguity(
    app_engine: Engine, owner_engine: Engine
) -> None:
    rows = _append(app_engine, 3, actor="rechain")
    victim = rows[1]
    downstream_seqs = [row["seq"] for row in rows if row["seq"] > victim["seq"]]
    originals = [_fetch(app_engine, seq) for seq in downstream_seqs]
    try:
        with owner_engine.begin() as conn:
            conn.execute(text("DELETE FROM audit_events WHERE seq = :seq"), {"seq": victim["seq"]})
            previous = (
                conn.execute(
                    text("SELECT hash FROM audit_events WHERE seq = :seq"),
                    {"seq": victim["seq"] - 1},
                ).scalar_one_or_none()
                or GENESIS_PREV_HASH
            )
            for seq in downstream_seqs:
                payload = conn.execute(
                    text("SELECT payload FROM audit_events WHERE seq = :seq"), {"seq": seq}
                ).scalar_one()
                rehashed = compute_hash(str(previous), payload)
                conn.execute(
                    text(
                        "UPDATE audit_events SET prev_hash = :prev, hash = :hash WHERE seq = :seq"
                    ),
                    {"prev": previous, "hash": rehashed, "seq": seq},
                )
                previous = rehashed
        # Linkage and hashes are now perfect: only seq contiguity is broken.
        valid, broken = verify_chain(app_engine)
        assert (valid, broken) == (False, victim["seq"] + 1)
    finally:
        with owner_engine.begin() as conn:
            for original in originals:
                conn.execute(
                    text(
                        "UPDATE audit_events SET prev_hash = :prev, hash = :hash WHERE seq = :seq"
                    ),
                    {
                        "prev": original["prev_hash"],
                        "hash": original["hash"],
                        "seq": original["seq"],
                    },
                )
        _restore(app_engine, [victim])
    assert verify_chain(app_engine) == (True, None)


def test_tail_truncation_leaves_db_valid_but_fails_both_layers(
    app_engine: Engine, owner_engine: Engine
) -> None:
    interval = max(1, get_settings().audit_checkpoint_interval)
    rows = _append(app_engine, interval, actor="tail")
    # A batch of exactly `interval` events always crosses a bucket boundary,
    # so the last row above is checkpointed to file and committed to git.
    tip = rows[-1]
    doomed = rows[-3:]
    try:
        with owner_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM audit_events WHERE seq = ANY(:seqs)"),
                {"seqs": [row["seq"] for row in doomed]},
            )
        # Remaining chain (1..tip-3) is internally consistent: the DB says valid.
        assert verify_chain(app_engine) == (True, None)
        checkpoint_ok, checkpoint_tip = checkpoint_status(app_engine)
        assert checkpoint_ok is False
        assert checkpoint_tip == {"seq": tip["seq"], "hash": tip["hash"]}
        ledger_ok, ledger_tip = ledger_status(app_engine)
        assert ledger_ok is False
        assert ledger_tip == {"seq": tip["seq"], "hash": tip["hash"]}
    finally:
        _restore(app_engine, doomed)
    assert verify_chain(app_engine) == (True, None)
    assert checkpoint_status(app_engine) == (True, {"seq": tip["seq"], "hash": tip["hash"]})
    assert ledger_status(app_engine) == (True, {"seq": tip["seq"], "hash": tip["hash"]})


def test_concurrent_appends_serialise_without_gaps(settings) -> None:
    engine = create_engine(
        settings.test_app_database_url,
        pool_size=10,
        max_overflow=5,
        connect_args={"connect_timeout": 3},
    )
    base = _count(engine)
    errors: list[BaseException] = []

    def worker(worker_id: int) -> None:
        try:
            for i in range(5):
                append_events(
                    engine,
                    [{"actor": f"thread-{worker_id}", "action": "test", "n": i}],
                )
        except BaseException as exc:  # noqa: BLE001 — re-raised in the main thread
            errors.append(exc)

    try:
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert not errors, errors
        assert all(not thread.is_alive() for thread in threads)
        with engine.connect() as conn:
            total = int(conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one())
            highest = conn.execute(text("SELECT max(seq) FROM audit_events")).scalar_one()
            distinct = conn.execute(
                text("SELECT count(DISTINCT seq) FROM audit_events WHERE seq > :base"),
                {"base": base},
            ).scalar_one()
        assert total == base + 40
        assert int(highest) == base + 40
        assert int(distinct) == 40
        assert verify_chain(engine) == (True, None)
    finally:
        engine.dispose()


def test_verify_walks_the_chain_once_streamed_with_no_extra_count(app_engine: Engine) -> None:
    """The verify job must scale with the log: one streamed walk over audit_events
    (not a fetch-all) that also yields checked_count, so there is no count(*)."""
    from sqlalchemy import event as sa_event

    walks: list[tuple[str, bool]] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:
        if "audit_events" in statement:
            walks.append((statement, bool(context.execution_options.get("stream_results"))))

    sa_event.listen(app_engine, "before_cursor_execute", capture)
    try:
        report = verify_report(app_engine)
    finally:
        sa_event.remove(app_engine, "before_cursor_execute", capture)
    assert report["valid"] is True and report["checked_count"] == _count(app_engine)
    assert not [s for s, _ in walks if "count(" in s.lower()]
    full_walks = [
        (s, streamed) for s, streamed in walks if "ORDER BY seq" in s and "LIMIT" not in s
    ]
    assert len(full_walks) == 1
    assert full_walks[0][1] is True, "the chain walk must stream its rows"
