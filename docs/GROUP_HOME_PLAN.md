# Plan: owner-first group home with per-division dashboards

## Context
The current dashboard (`web/src/app/dashboard/page.tsx`, `backend/app/api/dashboard.py`) is one flat page of
generic tiles (readiness, maintenance, certifications, deliveries, findings). Nothing is clickable, and it
answers an HQ question ("how is the organisation?") rather than the owner's ("how is each of my businesses?").
There is also no deadline any more: the Monday 12 Oct limit is gone, so nothing is cut for time.

Outcome: after sign-in the owner sees her businesses as cards. Each card opens a dashboard built for that
business. Every number links to the list behind it, then the record, then the evidence panel. Certifications
and maintenance stay, but as background compliance, not headline tiles.

## Decisions taken with the user (2026-10-09)
- No deadline anywhere in the docs. (Done: AGENTS.md, DEMO_SCOPE, PIVOT_PLAN, PRODUCTION_DEBT.)
- One login account: `owner`. Other accounts are archived (kept in code, not seeded, cannot log in).
- Landing: 2x2 grid Briech UAS, EIB Stratoc, Giga Forensics, Poctova, plus a fifth wide card for the troops,
  linked to Stratoc. Working name "Field Operations" (user may prefer "Troops"; confirm).
- Card content: one number to scan, shown only when there is a genuine alert. No alert = no number.
- Stratoc is surveillance/intelligence, NOT only troops. Troops are a separate card with a `supporting`
  tag per field site (default Stratoc). Stratoc card shows "N sites, M personnel"; tapping opens Field
  Operations filtered to Stratoc.
- Features brought in: forensic case workspace, reports for every division with export.
- Features NOT brought in: workflows/approvals (managers do that). Roster/check-in tool replaced by
  read-only summaries and reports (my reading of the user's answer to item 1; confirm).
- Certifications and maintenance move to background: a small compliance section per division plus one
  group-wide Compliance page.

## Phase A - housekeeping (partly done, uncommitted)
1. Docs: deadline removed from AGENTS.md, docs/DEMO_SCOPE.md, docs/PIVOT_PLAN.md, docs/PRODUCTION_DEBT.md.
   Still to do: rename "Demo-day" wording left in docs/PIVOT_PLAN.md/DECISIONS.md if any; update memory
   notes `demo-deadline-and-gaps` and `client-pivot-plan` (drop the deadline); add a dated line to
   docs/DECISIONS.md (no deadline; one account; new landing).
2. Accounts: `backend/app/seed/identity.py` now has `USERS = [owner]` and `ARCHIVED_USERS`, with
   `run(url, include_archived=False)`. `tests/conftest.py` and `tests/integration/test_seed.py` seed with
   `include_archived=True`, so the authorization matrix (invariant) keeps running. Still to do:
   `scripts/prefill_cache.py` DEFAULT_USERS ("owner","coo"), `web/smoke/smoke.mjs`, README login list,
   and the login page, so nothing references an unseeded user. Note in docs/STUBS.md how to restore one.

## Phase B - navigation shell and group home
- New landing route `web/src/app/page.tsx` / `/home` (reuse `web/src/lib/home.ts: homePath`): grid of cards.
- New endpoint `GET /api/v1/home/summary` in `backend/app/api/` (pattern: `dashboard.py` `_tool_tile`,
  `_group_status_tile`): per division, the one alert number or none. Built only from typed tools, so
  authorization and audit are unchanged. A card renders only if the caller's access context sees that
  division (hidden = absent, never "locked"; hidden records stay 404). A user who sees one division skips
  the grid.
- `Shell.tsx` nav: Home, division switcher (back/jump between divisions), Assistant, Map, Audit, Compliance.

## Phase C - division dashboards (route `/d/[division]`)
All figures link through to a list (`/d/[division]/list?...`) and on to `/records/[ref]` and the evidence panel.
Reuse existing typed tools in `backend/app/data_queries/tools/ (one module per domain, `@tool`)` and registry; add small tools only where
missing.
- **Briech UAS:** fleet availability, missions (`uas_missions`), aircraft due for maintenance
  (`equipment_due_for_maintenance`), airframe hours, deliveries/contracts (`deliveries_overdue`,
  `contracts_status`), link to the map.
- **EIB Stratoc:** detections (`detections_near_site`), the correlation finding (`/findings/[id]`,
  Run correlation button kept), sensors/sites, "N sites, M personnel" link to Field Operations.
- **Poctova:** production runs, QC holds (`production_qc_holds`), serial trace (`serial_trace`), stock
  (`stock_below_threshold`), overdue deliveries.
- **Giga Forensics:** forensic case workspace (below).
- **Field Operations (fifth card):** field sites with `supporting` subsidiary tag, attached personnel
  counts, last-seen/overdue summary as read-only figures. Filter by supporting subsidiary.
- Each division has a small Compliance section (its own expiring certifications, due maintenance).
- Group Compliance page: the old certification/maintenance tiles, full list, group-wide.

## Phase D - forensic case workspace (Giga)
- Seed richer fictional case data in `backend/app/seed/identity.py` (cases, evidence items, custody events), all
  `FORENSICS` compartment, `/eib-group/giga/`, labelled demo. Reuse the CASE/UCO-style `EvidenceItem` and
  `CustodyEvent` records (REC-046..062 range today, see seed.py near line 778).
- Typed tools: cases open/by status, custody gaps, evidence by case. Derived items inherit the highest
  classification and union of compartments (invariant).
- UI: case list, case detail with custody timeline, link to audit chain for the custody story.

## Phase E - reports per division with export
- Generalise `backend/app/reporting/training.py` into a per-division report (briefing draft from typed-tool
  rows plus retrieved documents, DRAFT FOR HUMAN REVIEW banner, inherited classification/compartments,
  provenance and audit as today).
- Export to PDF and DOCX. Runtime then needs `reportlab` and `python-docx` (today demo-tooling only):
  update docs/STUBS.md and add a dated entry to docs/PRODUCTION_DEBT.md for exported files carrying
  classification markings and leaving the system.
- Reports are informational only; no approval flow (humans decide, assistant informs).

## Invariants and constraints to respect throughout
Principle Zero (filter inside the query + RLS), 404 not 403, derived-item inheritance, audit event on every
query/answer, adapters read-only, typed parameterised tools only, no external CDN/fonts/tiles, demo data
labelled fictitious, never read .env. Do not derive real deployment locations from open sources. Seed or
prompt changes invalidate the LLM cache keys: finish data changes first, then the user re-runs prefill with
their key (free tier ~20 calls/day).

## Order of work (one task at a time, check.sh green, commit, stop for go-ahead)
1. Phase A finish + decisions/memory. 2. Phase B. 3. Phase C one division at a time: Poctova, Briech,
Stratoc, Field Operations, then group Compliance. 4. Phase D. 5. Phase E. 6. Docs/STUBS/DEBT, prefill handoff.

## Verification
- `scripts/check.sh` (ruff, pytest incl. authz suite, web eslint/tsc/build, air-gap scan) after each task.
- New tests: home summary per user (owner sees 5 cards; archived roles see fewer, hidden = absent),
  division endpoints, report export markings, forensic custody inheritance. Extend `tests/authz/expected.py`
  by hand (not derived from the seed).
- Run API + web, sign in as `owner`: click through card -> division -> list -> record -> evidence; audit
  verify shows valid, checkpoint_ok, ledger_ok. Update the web smoke test (`web/smoke/smoke.mjs`).
- Reseed + ingest, run correlation once, then prefill (user step).

## Open points for the user
1. Card name: "Field Operations" or "Troops"? 2. Confirm item 1 reading (summaries/reports instead of a
roster tool). 3. Phase D adds new fictional case data: OK?
