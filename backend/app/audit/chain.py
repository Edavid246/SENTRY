"""Hash-chained, append-only audit log with two-layer tamper evidence (SPEC 14).

Chain: ``hash = sha256(prev_hash + canonical_json(payload))`` over rows
ordered by ``seq``; the first event chains to the all-zero genesis hash.
Canonical JSON is sorted keys with no whitespace, and payloads only ever
hold JSON-native scalars, so the hash is reproducible outside Python.

Writers serialize on two Postgres advisory locks taken in this order inside
one transaction: CHAIN_LOCK (read tip, compute explicit seqs, insert) then
CHECKPOINT_LOCK (append the checkpoint line to layer 1 and commit it to the
layer-2 git ledger). Holding both across the git subprocess keeps checkpoint
lines in seq order and keeps two writers out of the ledger's index.lock at
once — at the cost of a long-held transaction, which is recorded in
docs/PRODUCTION_DEBT.md.

Failure semantics (approved step-7 design):
- insert failure        -> exception, request fails (blocking)
- checkpoint file error -> AUDIT CHECKPOINT FILE WRITE FAILED log, then
                           AuditWriteError (blocking, distinct log line)
- git ledger failure    -> AUDIT LEDGER GIT COMMIT FAILED log, non-blocking;
                           the next successful commit picks the line up again
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.audit.models import AuditEvent
from app.config import get_settings

logger = logging.getLogger("audit.chain")

GENESIS_PREV_HASH = "0" * 64
CHAIN_LOCK_KEY = 741_741
CHECKPOINT_LOCK_KEY = 741_742
LEDGER_FILENAME = "checkpoints.log"
GIT_TIMEOUT_SECONDS = 10


class AuditWriteError(RuntimeError):
    """Audit persistence failed in a way that blocks the request."""


class _LedgerError(Exception):
    """Internal: the git ledger could not be updated or read."""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical_json(payload)).encode()).hexdigest()


def append_events(engine: Engine, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append one batch of audit events atomically, then checkpoint if due.

    Returns the stored rows (seq/event_id/prev_hash/hash included) in
    insertion order. Raises on insert or checkpoint-file failure.
    """
    if not payloads:
        return []
    settings = get_settings()
    if settings.audit_source:
        payloads = [{**payload, "source": settings.audit_source} for payload in payloads]
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CHAIN_LOCK_KEY})
        conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CHECKPOINT_LOCK_KEY})
        last = conn.execute(
            text("SELECT seq, hash FROM audit_events ORDER BY seq DESC LIMIT 1")
        ).first()
        next_seq = 1 if last is None else int(last[0]) + 1
        prev_hash = GENESIS_PREV_HASH if last is None else str(last[1])
        rows: list[dict[str, Any]] = []
        for offset, payload in enumerate(payloads):
            row_hash = compute_hash(prev_hash, payload)
            rows.append(
                {
                    "seq": next_seq + offset,
                    "event_id": uuid4().hex,
                    "payload": payload,
                    "prev_hash": prev_hash,
                    "hash": row_hash,
                }
            )
            prev_hash = row_hash
        conn.execute(AuditEvent.__table__.insert(), rows)
        # Explicit seqs bypass the serial sequence; keep it in step so any
        # sequence-based insert (schema probes, future writers) lands after
        # the tip instead of colliding with a chain row.
        conn.execute(
            text("SELECT setval(pg_get_serial_sequence('audit_events', 'seq'), :tip, true)"),
            {"tip": rows[-1]["seq"]},
        )
        _maybe_checkpoint(
            tip_seq=rows[-1]["seq"],
            tip_hash=rows[-1]["hash"],
            total_before=next_seq - 1,
            settings=settings,
        )
    return rows


def _maybe_checkpoint(*, tip_seq: int, tip_hash: str, total_before: int, settings) -> None:
    interval = max(1, int(settings.audit_checkpoint_interval))
    if total_before // interval >= tip_seq // interval:
        return
    line = canonical_json({"timestamp": utc_now_iso(), "seq": tip_seq, "hash": tip_hash})
    _append_checkpoint_file(Path(settings.audit_checkpoint_path).expanduser(), line)
    _commit_ledger(
        Path(settings.audit_ledger_path).expanduser(), line, tip_seq=tip_seq, tip_hash=tip_hash
    )


def _append_checkpoint_file(path: Path, line: str) -> None:
    """Layer 1: append + flush + fsync the checkpoint line. Blocking on failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        logger.critical("AUDIT CHECKPOINT FILE WRITE FAILED — blocking request: %s", exc)
        raise AuditWriteError(f"checkpoint file append failed: {exc}") from exc


def _commit_ledger(ledger: Path, line: str, *, tip_seq: int, tip_hash: str) -> None:
    """Layer 2: same line in the external git ledger repo. Non-blocking."""
    try:
        if not (ledger / ".git").is_dir():
            raise _LedgerError(f"ledger repo not initialised at {ledger}")
        target = ledger / LEDGER_FILENAME
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        _git(["add", LEDGER_FILENAME], cwd=ledger)
        _git(["commit", "-m", f"seq={tip_seq} hash={tip_hash}"], cwd=ledger)
        committed = _git(["show", f"HEAD:{LEDGER_FILENAME}"], cwd=ledger)
        tail = [entry for entry in committed.splitlines() if entry.strip()]
        if not tail or tail[-1] != line:
            raise _LedgerError("committed ledger tail does not match the checkpoint line")
    except (OSError, subprocess.SubprocessError, _LedgerError) as exc:
        logger.error("AUDIT LEDGER GIT COMMIT FAILED — non-blocking: %s", exc)


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(  # noqa: S603 — fixed argv, no shell
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise _LedgerError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


_WALK_BATCH = 1000


def _walk_chain(engine: Engine) -> tuple[int, int | None, str | None]:
    """Stream the chain in seq order: (rows walked, first broken seq, its event_id).

    Rows arrive in batches from a server-side cursor, so memory stays flat as
    the log grows. After the first break the walk only counts, so the count
    always covers every event.
    """
    walked = 0
    broken: tuple[int, str] | None = None
    prev_hash = GENESIS_PREV_HASH
    with engine.connect() as conn:
        rows = conn.execution_options(stream_results=True, yield_per=_WALK_BATCH).execute(
            text("SELECT seq, event_id, payload, prev_hash, hash FROM audit_events ORDER BY seq")
        )
        for seq, event_id, payload, stored_prev, stored_hash in rows:
            walked += 1
            if broken is not None:
                continue
            if (
                int(seq) != walked
                or stored_prev != prev_hash
                or stored_hash != compute_hash(str(stored_prev), payload)
            ):
                broken = (int(seq), str(event_id))
            prev_hash = str(stored_hash)
    if broken is None:
        return walked, None, None
    return walked, broken[0], broken[1]


def verify_chain(engine: Engine) -> tuple[bool, int | None]:
    """Re-walk the whole chain in seq order; first break returns its seq."""
    _, broken_seq, _ = _walk_chain(engine)
    return broken_seq is None, broken_seq


def _db_tips(engine: Engine, seq: int) -> tuple[tuple[int, str] | None, tuple[int, str] | None]:
    """Row at `seq` and the current chain tip, or None for each."""
    with engine.connect() as conn:
        at_seq = conn.execute(
            text("SELECT seq, hash FROM audit_events WHERE seq = :seq"), {"seq": seq}
        ).first()
        tip = conn.execute(
            text("SELECT seq, hash FROM audit_events ORDER BY seq DESC LIMIT 1")
        ).first()
    return (
        (int(at_seq[0]), str(at_seq[1])) if at_seq is not None else None,
        (int(tip[0]), str(tip[1])) if tip is not None else None,
    )


def _read_tip_line(path: Path) -> dict[str, Any] | None:
    """Last non-empty checkpoint line; None if the file is missing/empty."""
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except FileNotFoundError:
        return None
    if not lines:
        return None
    parsed = json.loads(lines[-1])  # may raise — caller decides what that means
    return {"seq": int(parsed["seq"]), "hash": str(parsed["hash"])}


def checkpoint_status(engine: Engine) -> tuple[bool | None, dict[str, Any] | None]:
    """(ok, tip): None/None until the first checkpoint exists."""
    try:
        tip = _read_tip_line(Path(get_settings().audit_checkpoint_path).expanduser())
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False, None
    if tip is None:
        return None, None
    row, db_tip = _db_tips(engine, tip["seq"])
    if db_tip is None or tip["seq"] > db_tip[0]:
        return False, tip
    if row is None or row[1] != tip["hash"]:
        return False, tip
    return True, tip


def ledger_status(engine: Engine) -> tuple[bool | None, dict[str, Any] | None]:
    """(ok, tip) for the layer-2 git ledger; None when it cannot be read at all."""
    ledger = Path(get_settings().audit_ledger_path).expanduser()
    if not (ledger / ".git").is_dir():
        return None, None
    try:
        committed = _git(["show", f"HEAD:{LEDGER_FILENAME}"], cwd=ledger)
    except (OSError, subprocess.SubprocessError, _LedgerError):
        return None, None
    tail = [line for line in committed.splitlines() if line.strip()]
    if not tail:
        return None, None
    try:
        parsed = json.loads(tail[-1])
        tip = {"seq": int(parsed["seq"]), "hash": str(parsed["hash"])}
    except (ValueError, KeyError, json.JSONDecodeError):
        return False, None
    try:
        file_tip = _read_tip_line(Path(get_settings().audit_checkpoint_path).expanduser())
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        file_tip = None
    if file_tip is not None and file_tip["seq"] > tip["seq"]:
        return False, tip
    row, db_tip = _db_tips(engine, tip["seq"])
    if db_tip is None or tip["seq"] > db_tip[0]:
        return False, tip
    if row is None or row[1] != tip["hash"]:
        return False, tip
    return True, tip


def verify_report(engine: Engine) -> dict[str, Any]:
    """Everything GET /audit/verify returns (SPEC 14.2 verification job).

    `first_bad_event_id` identifies the first event whose stored row does not
    match the chain (payload edit, rehash or sequence break), so a viewer can
    deep-link straight to it with GET /audit?event_id=...; `checked_count` is
    the number of events the walk covered.
    """
    checked_count, broken_seq, first_bad_event_id = _walk_chain(engine)
    valid = broken_seq is None
    checkpoint_ok, checkpoint_tip = checkpoint_status(engine)
    ledger_ok, ledger_tip = ledger_status(engine)
    return {
        "valid": valid,
        "checked_count": checked_count,
        "first_bad_event_id": first_bad_event_id,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_tip": checkpoint_tip,
        "ledger_ok": ledger_ok,
        "ledger_tip": ledger_tip,
    }


def recent_events(engine: Engine, limit: int, event_id: str | None = None) -> list[dict[str, Any]]:
    """Newest-first audit events for the viewer (SPEC 14 audit viewer API).

    Every item carries its `event_id` so an answer's audit_event_id can
    deep-link to its row; `event_id` narrows the read to that one event.
    """
    where = ""
    params: dict[str, Any] = {"limit": limit}
    if event_id is not None:
        where = " WHERE event_id = :event_id"
        params["event_id"] = event_id
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT seq, event_id, created_at, payload, prev_hash, hash"
                " FROM audit_events"
                f"{where} ORDER BY seq DESC LIMIT :limit"
            ),
            params,
        ).all()
    return [
        {
            "seq": int(seq),
            "event_id": str(event_id_value),
            "created_at": created_at.isoformat(),
            "payload": payload,
            "prev_hash": prev_hash,
            "hash": stored_hash,
        }
        for seq, event_id_value, created_at, payload, prev_hash, stored_hash in rows
    ]
