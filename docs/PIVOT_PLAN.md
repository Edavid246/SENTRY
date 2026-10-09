# Plan: re-point the demo from "army HQ" to the client's group (EIB-style operator)

## Context
The client is one private operator (not military) who owns a defence/security group: a UAS maker
(Briech UAS), a surveillance/intelligence arm (EIB Stratoc), a forensics arm (Giga Forensics) and a
protective-gear maker (Poctova), serving several government agencies, with attached troops at
field sites. Our engine (adapters, typed tools, RLS, audit, citations, correlation, map/replay) fits
him. The mismatch is the surrounding layer: Brigade/Battalion hierarchy, army-style users and
"Secret" naming, a Readiness/Training/Certification-first dashboard, and no concept of contracts,
production/serials, client separation or state.

Intended outcome: same real engine, but it reads as HIS group, with new
contract/delivery, manufacturing-traceability and asset views, and a state filter.
Decisions already taken with the user: use real subsidiary names over fictitious, labelled-demo
data; full rename including unit paths; owner-first login with a restricted second user kept in
reserve; sovereignty is stated verbally by the user (no code); state filter lists all 36 states + FCT
while data stays in the existing fictional rural sites.

Invariants stay untouched (Principle Zero, 404-not-403, derived-label inheritance, audit on every
tool call, adapter-only reads, validated params, demo data labelled). Spec departures get dated lines
in docs/DECISIONS.md.

## Constraints that shape the order
- Gemini free tier ~20 calls/day, full prefill ~19, resets 00:00 UTC (01:00 Nigeria time). Any change
  to seed rows, unit names, system prompts or documents changes cache keys
  (ai_gateway/cache.py key = model + messages + params). Task 1 therefore invalidates most entries.
  Plan: do ALL data/prompt changes first, run prefill (user step, needs their key) once after the last
  data change, Cache is a convenience; live Gemini is the fallback.
- Per working protocol: one task at a time, scripts/check.sh green, commit, then stop for go-ahead.

## Tasks

### Task 1 - Rename and relabel (the mechanical pivot)
Files: backend/app/seed.py (single seed source), backend/app/dashboard/fixtures.py,
backend/app/units.py (slug usage), data/documents/manifest.json, scripts/generate_demo_documents.py,
data/SOURCES.md, data/demo_questions.json, backend/app/knowledge/answer.py +
data_queries/explain.py + reporting/training.py (system prompts say "defence headquarters"),
web/src/app/chat/page.tsx (suggested question), web/src/lib/clearance.ts, web/smoke/*.
- Units (paths change; UUIDs derive from paths): Command A -> EIB Group `/eib-group/`;
  UAS Wing -> Briech UAS `/eib-group/briech/`; Brigade 2 -> EIB Stratoc `/eib-group/stratoc/`;
  Battalion 4 -> Stratoc Site Team 4 `/eib-group/stratoc/site-4/`; HQ IT -> Group IT `/group-it/`;
  HQ Inspectorate -> Group Audit `/group-audit/`; add Giga Forensics `/eib-group/giga/` and
  Poctova `/eib-group/poctova/` (forensics records move to Giga where unambiguous).
- Users: keep role strings (coupled to authz/policy.py and Shell.tsx); change usernames/display
  names/titles: commander -> "Group Owner" (`owner`); the limited second user ("COO view") is the
  existing training/Bn-4-scoped user; others become Head of Production & Logistics, Briech UAS Lead,
  Group IT, Group Audit. Update tests/prefill DEFAULT_USERS/smoke accordingly.
- Classification: keep the four-level scheme (config data, spec default); relabel display names
  (Open / Internal / Confidential / Government-sensitive) in DB label + clearance.ts. Keys unchanged.
- Add client compartments (e.g. CLIENT-A..D, generic agency labels) alongside UAS-OPS and FORENSICS;
  owner holds all. Used by Tasks 4-5. No real agency names attached to invented contract data.
- Rewrite document text / titles from Brigade/Battalion to group terms; re-ingest.
- Correlation finding id FND-RISING-FAULTS-BN-4 -> ...-SITE-4 (derived from unit_slug); update
  smoke.mjs.
- Tests: update hard-coded names/counts: tests/integration/test_seed.py EXPECTED_COUNTS,
  tests/authz/expected.py oracle (hand-authored; recompute by hand, do not generate from code),
  tests/api/test_dashboard.py, test_data_pathway.py, test_correlation.py, test_reporting.py,
  knowledge/test_retrieve.py, unit/test_rls_statements.py.
- Prefill is NOT run yet.
Verify: scripts/check.sh green (ruff, pytest incl. tests/authz, web lint/typecheck/build, air-gap grep).

### Task 2 - State filter
- New backend/app/geo/states.py: the 36 states + FCT as a constant list (validated enum).
- Seed: add `state` to sensor/detection/mission/site record data (existing fictional rural sites -> Niger).
- api/connected.py: `GET /connected/map?state=` and replay accept optional validated `state`;
  tools `uas_missions` / `detections_near_site` gain optional `state` param (filter in Python after
  adapter.search, as `stock_below_threshold` does; reuse `_check_names`, `_pattern`). Unknown state ->
  ToolParamError -> audited deny, no SQL.
- web: dropdown on /map listing all states; empty selection = all. Regenerate web/src/lib/api-types.ts
  (npm run gen:api).
- Tests: tool + endpoint tests incl. invalid state, and that the filter never widens visibility
  (row filter + RLS still applied).

### Task 3 - Group dashboard
- Replace the READINESS fixture tile (dashboard/fixtures.py, currently PLACEHOLDER) with a
  "Group status" tile: one item per subsidiary, counts computed from existing typed tools via a
  generalised `_tool_tile` grouping (api/dashboard.py), each count carrying inherited
  classification + compartment union. Keep maintenance, expired-qualification and findings tiles.
- Retitle tiles in backend copy; dashboard/page.tsx key names stay unless a tile is added.
- Tests: tests/api/test_dashboard.py for owner vs limited user (fewer subsidiaries/counts).

### Task 4 - Contracts and deliveries
- Seed: entity types `Contract`, `Delivery` (~8 and ~12 fictional rows, labelled demo; generic agencies
  "Client Agency A-D" mapped to the client compartments; values illustrative).
- Add to `ENTITY_TYPES` and `DATE_FIELDS` (due_date) in connectors/demo.py.
- Tools in data_queries/tools.py: `deliveries_overdue` and `contracts_status` (optional `client`,
  `status` params, validated); register in registry.py; routing regexes in routing.py placed BEFORE
  `_STOCK_RE`/`_UAS_RE` (they overlap "inventory", "deliver"); add scripted question in
  data/demo_questions.json.
- Dashboard tile "Overdue deliveries" (new `ToolTile`, new field in `DashboardTiles`, add to audit
  item_ids); update api types.
- Tests: oracle additions in tests/authz/expected.py + test_seed counts; per-tool, per-user (limited
  user sees only own-compartment clients), refusal and routing tests in test_data_pathway.py.

### Task 5 - Manufacturing and serial traceability
- Seed: entity types `ProductionRun`, `SerialUnit` (airframes from Briech, protective gear/uniform lots
  from Poctova) with qc_status, delivered_to client, delivery ref.
- Tools: `serial_trace` (param: serial, validated pattern) and `production_qc_holds`; same
  registration/routing/question/test checklist as Task 4. Evidence rows link to
  `/records/{source_ref}`.

### Task 6 - Assets (seed-only, no new tool)
- Add Equipment/StockItem rows for the command-and-control vehicle, helipad, jet-fuel depot stock and
  airframe flight hours so existing tools (`equipment_due_for_maintenance`, `stock_below_threshold`,
  `uas_missions`) answer asset questions. Update oracle/counts.

### Task 7 - Docs, memory, prefill
- docs/DECISIONS.md dated lines: pivot to single-principal group framing; real subsidiary names over
  demo data; full unit rename; client compartments; generic agencies. Mark SPEC military assumptions as
  superseded there.
- docs/DEMO_SCOPE.md (built table, demo script wording), docs/STUBS.md (any new stub), docs/PRODUCTION_DEBT.md
  only for security-relevant items (e.g. generic-agency mapping, placeholder tiles).
- Update memory notes (project pivot, new unit names/usernames).
- Handoff: give the user the prefill commands (record, then --verify) to run with their key after the
  last data change; re-run the run checklist.

## Explicitly deferred (after discovery)
Field-site/troop rosters and check-ins, forensic case UI beyond current evidence view, Poctova
complement-vs-replace question, real systems/adapters, connectivity/offline mode, local model.
Do NOT derive real deployment locations from open sources.

## End-to-end verification
1. `scripts/check.sh` green after every task (authz tests included).
2. Fresh DB: alembic upgrade head -> `python -m app.seed` -> `scripts/ingest_documents.py`.
3. Run API + web; log in as `owner`: dashboard tiles, Run correlation (finding labelled), map with state
   filter, new questions (overdue deliveries, serial trace) return tables + citations/evidence links.
4. Log in as the limited user: same questions return fewer rows; hidden records 404 (never 403).
5. Audit viewer: verify -> valid, checkpoint_ok, ledger_ok.
6. After prefill (user step): `prefill_cache.py --verify` with LLM_CACHE_ONLY.
