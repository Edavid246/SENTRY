#!/usr/bin/env python3
"""Prefill (or verify) the demo LLM cache through the REAL assistant pipeline.

Cache keys hash the exact model request (system prompt + retrieved evidence +
question), and the evidence differs per user, so entries are only valid when
recorded by logging in as each demo user and asking each "built" question in
data/demo_questions.json. Nothing is synthesised: a failure is reported, never
papered over with a placeholder answer.

Run from the repository root with the dev stack's database up and seeded/ingested
(README quick start) and the API key in the environment (never printed):

    set -a && . ./.env && set +a
    uv run python scripts/prefill_cache.py            # record live answers into the cache
    uv run python scripts/prefill_cache.py --verify   # cache-only: provider disabled, key ignored

The script drives the FastAPI app in-process (same code, same database, same
audit trail as the server); POST /api/v1/assistant/query is what gets called.
Record mode sets LLM_CACHE_RECORD=1 and is refused unless APP_PROFILE=dev.
Demo-only shortcut: docs/PRODUCTION_DEBT.md. All data is fictitious demo data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
QUESTIONS_FILE = REPO / "data" / "demo_questions.json"
DEFAULT_USERS = ("a.bello", "t.adeyemi")
DEMO_PASSWORD = "Demo!Gateway2026"  # README: dev seed password, not a secret
# Pathways that are not assistant queries (the audit viewer asks no model).
NON_ASSISTANT_PATHWAYS = frozenset({"audit"})
RETRY_STATUSES = (429, 503)
RETRY_WAITS = (5.0, 15.0, 30.0)


@dataclass(frozen=True, slots=True)
class Pair:
    user: str
    question: str
    labels: tuple[str, ...]  # question ids that share this (user, text)


def plan_pairs(questions: list[dict], extra_users: tuple[str, ...] = DEFAULT_USERS) -> list[Pair]:
    """Every (user, question) to prefill: built assistant questions x (asker + extra users)."""
    ordered: dict[tuple[str, str], list[str]] = {}
    for entry in questions:
        if entry.get("status") != "built" or entry.get("pathway") in NON_ASSISTANT_PATHWAYS:
            continue
        users = [entry["asked_by"], *extra_users]
        for user in dict.fromkeys(users):
            ordered.setdefault((user, entry["question"]), []).append(entry["id"])
    return [Pair(user, text, tuple(ids)) for (user, text), ids in ordered.items()]


def skipped_entries(questions: list[dict]) -> list[dict]:
    return [
        q
        for q in questions
        if q.get("status") != "built" or q.get("pathway") in NON_ASSISTANT_PATHWAYS
    ]


@dataclass(slots=True)
class Outcome:
    pair: Pair
    ok: bool
    http: int
    source: str  # "recorded" | "already recorded" | "cache" | "no model call" | "-"
    found: bool | None
    refused: bool | None
    detail: str
    seconds: float


def _prepare_environment(verify: bool) -> None:
    # Every audit event this run writes is tagged, so auditors can tell it apart.
    os.environ["AUDIT_SOURCE"] = "prefill-verify" if verify else "prefill"
    if verify:
        # Provider disabled: ignore any key in the environment and never record.
        for name in ("HOSTED_API_KEY", "GEMINI_API_KEY", "LLM_CACHE_RECORD"):
            os.environ.pop(name, None)
        os.environ["LLM_CACHE_ONLY"] = "1"
        return
    if not (os.environ.get("HOSTED_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        raise SystemExit(
            "No API key in the environment (HOSTED_API_KEY or GEMINI_API_KEY). Load your .env "
            "first:  set -a && . ./.env && set +a"
        )
    os.environ.pop("LLM_CACHE_ONLY", None)
    os.environ["LLM_CACHE_RECORD"] = "1"
    # Generous: a live call has been seen to take minutes (docs/PRODUCTION_DEBT.md).
    os.environ.setdefault("HOSTED_TIMEOUT_SECONDS", "180")


def _no_model_call(body: dict, insufficient: str, no_rows: str) -> bool:
    """Answers that legitimately involve no model call (so nothing to cache)."""
    answer = str(body.get("answer", ""))
    return (
        answer.startswith("That request was refused")  # data-pathway refusal
        or answer == no_rows
        or (body.get("found") is False and answer == insufficient)  # no authorized evidence
    )


def _ask(client, token: str, pair: Pair, *, retry: bool) -> tuple[int, dict, str]:
    headers = {"Authorization": f"Bearer {token}"}
    attempts = 1 + (len(RETRY_WAITS) if retry else 0)
    for attempt in range(attempts):
        response = client.post(
            "/api/v1/assistant/query", json={"question": pair.question}, headers=headers
        )
        detail = ""
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code != 200:
            detail = str(payload.get("detail", response.text))[:120]
            if "not configured" in detail:
                raise SystemExit(f"Provider not configured on this machine: {detail}")
            if response.status_code in RETRY_STATUSES and attempt + 1 < attempts:
                wait = RETRY_WAITS[attempt]
                print(
                    f"      HTTP {response.status_code}; retry {attempt + 1}/{attempts - 1}"
                    f" in {wait:g}s"
                )
                time.sleep(wait)
                continue
        return response.status_code, payload, detail
    raise AssertionError("unreachable")


def run(pairs: list[Pair], *, verify: bool, pause: float) -> list[Outcome]:
    from app.ai_gateway.gateway import get_gateway
    from app.config import get_settings
    from app.data_queries.explain import NO_ROWS_ANSWER
    from app.main import app
    from fastapi.testclient import TestClient

    settings = get_settings()
    insufficient = settings.assistant_insufficient_message
    gateway = get_gateway()
    outcomes: list[Outcome] = []
    tokens: dict[str, str] = {}
    with TestClient(app, raise_server_exceptions=False) as client:
        # The planted finding exists only once a commander has run the correlation job;
        # the findings question needs it in place (idempotent, so safe on every run).
        boss = client.post(
            "/api/v1/auth/login", json={"username": "a.bello", "password": DEMO_PASSWORD}
        )
        if boss.status_code == 200:
            client.post(
                "/api/v1/correlation/run",
                headers={"Authorization": f"Bearer {boss.json()['access_token']}"},
            )
        for index, pair in enumerate(pairs):
            if pair.user not in tokens:
                login = client.post(
                    "/api/v1/auth/login", json={"username": pair.user, "password": DEMO_PASSWORD}
                )
                if login.status_code != 200:
                    raise SystemExit(f"Login failed for {pair.user}: HTTP {login.status_code}")
                tokens[pair.user] = login.json()["access_token"]
            if index and not verify:
                time.sleep(pause)
            before = (gateway.recorded_count, gateway.replayed_count)
            started = time.perf_counter()
            try:
                status, body, detail = _ask(client, tokens[pair.user], pair, retry=not verify)
            except SystemExit:
                raise
            except Exception as exc:  # report, never hide (DB down, etc.)
                status, body, detail = 0, {}, f"{type(exc).__name__}: {str(exc)[:100]}"
            seconds = time.perf_counter() - started
            recorded = gateway.recorded_count - before[0]
            replayed = gateway.replayed_count - before[1]

            ok, source = False, "-"
            if status == 200 and str(body.get("answer", "")).strip():
                if verify and replayed:
                    ok, source = True, "cache"
                elif not verify and recorded:
                    ok, source = True, "recorded"
                elif not verify and replayed:
                    # Same request already in the cache: reused, no model call spent.
                    ok, source = True, "already recorded"
                elif _no_model_call(body, insufficient, NO_ROWS_ANSWER) and not (
                    recorded or replayed
                ):
                    ok, source = True, "no model call"
                else:
                    detail = "answer returned but the model result was not " + (
                        "replayed from the cache" if verify else "recorded"
                    )
            elif status == 503 and verify:
                detail = "CACHE MISS (provider disabled): " + detail
            outcome = Outcome(
                pair, ok, status, source, body.get("found"), body.get("refused"), detail, seconds
            )
            outcomes.append(outcome)
            print(
                f"{'PASS' if ok else 'FAIL'}  {pair.user:<10} {pair.labels[0]:<40} "
                f"HTTP {status} {source}{('  ' + detail) if detail else ''}  ({seconds:.1f}s)"
            )
    return outcomes


def print_table(outcomes: list[Outcome]) -> None:
    print()
    header = (
        f"{'user':<10} {'question':<40} {'HTTP':<5} {'source':<14} "
        f"{'found':<6} {'refused':<8} result"
    )
    print(header)
    print("-" * len(header))
    for item in outcomes:
        print(
            f"{item.pair.user:<10} {item.pair.labels[0]:<40} {item.http:<5} {item.source:<14} "
            f"{str(item.found):<6} {str(item.refused):<8} {'OK' if item.ok else 'FAIL'}"
        )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description="Prefill or verify the demo LLM cache")
    parser.add_argument(
        "--verify", action="store_true", help="cache-only: provider disabled, record nothing"
    )
    parser.add_argument("--pause", type=float, default=4.0, help="seconds between live calls")
    parser.add_argument(
        "--users",
        default=",".join(DEFAULT_USERS),
        help="demo users asked every built question, besides its own asker",
    )
    args = parser.parse_args()

    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]
    users = tuple(name.strip() for name in args.users.split(",") if name.strip())
    pairs = plan_pairs(questions, users)

    _prepare_environment(args.verify)
    os.chdir(REPO)  # the cache path in settings is relative to the repo root
    try:
        from app.config import get_settings

        settings = get_settings()
    except ValueError as exc:  # pydantic ValidationError: record refused outside dev
        raise SystemExit(f"Refused: {exc}") from exc

    mode = "VERIFY (cache-only, hosted provider disabled)" if args.verify else "RECORD (live)"
    print(f"== prefill_cache: {mode}")
    print(f"   cache file : {settings.llm_response_cache_path}")
    print(f"   model      : {settings.llm_model}")
    print(f"   pairs      : {len(pairs)}")
    for entry in skipped_entries(questions):
        print(f"   skipped    : {entry['id']} ({entry['status']}, {entry['pathway']} pathway)")

    outcomes = run(pairs, verify=args.verify, pause=args.pause)
    print_table(outcomes)
    failed = [item for item in outcomes if not item.ok]
    print()
    print(f"{len(outcomes) - len(failed)}/{len(outcomes)} passed")
    if failed:
        print("FAILED pairs (no placeholder answers were written):", file=sys.stderr)
        for item in failed:
            print(
                f"  {item.pair.user} / {item.pair.labels[0]}: HTTP {item.http} {item.detail}",
                file=sys.stderr,
            )
        raise SystemExit(1)
    if not args.verify:
        print("Next: uv run python scripts/prefill_cache.py --verify")


if __name__ == "__main__":
    main()
