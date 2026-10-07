#!/usr/bin/env bash
# One-time setup of the external git audit ledger (SPEC 14.2 layer 2).
#
# The ledger is deliberately a separate repository OUTSIDE gateway-mvp so a
# tamper attempt against the application repo cannot touch it. It starts with
# no commits: the application creates checkpoints.log on the first checkpoint
# and commits it with a "seq=N hash=..." message.
set -euo pipefail

LEDGER_DIR="${1:-${AUDIT_LEDGER_PATH:-$HOME/projects/gateway-audit-ledger}}"

if [ -d "$LEDGER_DIR/.git" ]; then
  echo "audit ledger already initialised: $LEDGER_DIR"
  exit 0
fi

mkdir -p "$LEDGER_DIR"
git init -b main "$LEDGER_DIR"
git -C "$LEDGER_DIR" config user.name "gateway-audit"
git -C "$LEDGER_DIR" config user.email "gateway-audit@localhost"
echo "initialised empty git audit ledger at $LEDGER_DIR"
