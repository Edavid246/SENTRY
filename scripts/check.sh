#!/usr/bin/env bash
# Local check gate: lint, format, tests, air-gap scan.
# Used in place of CI (no git remote yet; GitHub Actions intentionally skipped).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "== ruff check"
uv run ruff check .

echo "== ruff format --check"
uv run ruff format --check .

echo "== pytest"
uv run pytest -q "$@"

echo "== web: eslint + tsc --noEmit"
export NEXT_TELEMETRY_DISABLED=1
(
  cd web
  [ -d node_modules ] || npm ci
  npm run lint
  npm run typecheck
)

echo "== air-gap scan (no external CDNs, fonts, tiles, telemetry)"
pattern='fonts\.googleapis|fonts\.gstatic|cdn\.jsdelivr|unpkg\.com|cdnjs\.|maps\.googleapis|maps\.google|tile\.openstreetmap|api\.mapbox|googletagmanager|google-analytics'
if grep -rEn --exclude=check.sh --exclude-dir=node_modules --exclude-dir=.next "$pattern" backend web infra scripts tests 2>/dev/null; then
  echo "FAIL: external resource reference found (AGENTS.md air-gap rules)"
  exit 1
fi
echo "air-gap scan: clean"

echo "check.sh: all checks passed"
