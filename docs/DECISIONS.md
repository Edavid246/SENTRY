# Decisions log

Dated one-line entries for places where the build deliberately departs from a
default in docs/SPEC.md. Invariants (see AGENTS.md) never appear here: changing one
needs a conversation first.

Format: `YYYY-MM-DD — what changed — why`

- 2026-10-09 — No deadline: every deadline/cut-line reference removed from the docs; work is not trimmed for time.
- 2026-10-09 — One product account: only `owner` is seeded; the other five users live in `ARCHIVED_USERS` (app/seed.py) and are loaded only by tests (`include_archived=True`) so the authorization matrix keeps running. `scripts/prefill_cache.py` skips archived users.
- 2026-10-09 — Planned: owner-first group home (Briech UAS, EIB Stratoc, Giga Forensics, Poctova, Field Operations cards) with per-division dashboards, forensic case workspace and per-division reports with export; workflows/approvals stay cut. Plan: ~/.claude/plans/i-didn-t-tell-you-functional-lantern.md.
- 2026-10-09 — Phase B: login now lands on a group home (`/home`, `GET /api/v1/home/summary`): one card per division the caller can see, an alert count only when something needs attention (equipment, deliveries, QC holds, stock, cancelled UAS missions, open findings). Certifications are deliberately not counted (background compliance). Site teams (units below a subsidiary) count as Field Operations; a finding stays with its subsidiary. Hidden divisions are absent, never locked; a caller with one division skips the grid. `/dashboard` is now labelled "Overview" until Phase C reworks it into per-division and compliance views.
- 2026-10-09 — AGENTS.md split into invariants vs defaults; spec binds only on invariants — spec is a v0.1 draft and "stop and ask" on every difference was blocking work.
- 2026-10-09 — Pivot Task 3: readiness fixture tile replaced by a real per-subsidiary "Group status" tile (api key `readiness` kept); fixtures module deleted — no real readiness source exists, open-item counts are honest and audited.
- 2026-10-09 — Pivot Task 1: units renamed to the client's group (EIB Group, Briech UAS, EIB Stratoc, Stratoc Site Team 4, Giga Forensics, Poctova, Group IT, Group Audit); users renamed by role (`owner`, `coo`, ...); classification keys unchanged, display names Open/Internal/Confidential/Government-sensitive; compartments CLIENT-A..D added (generic agency labels) — demo is for one private group owner, not an army HQ; role strings kept because authz/policy.py and the shell depend on them.
- 2026-10-09 — Pivot: the demo is framed for one private principal who owns a defence/security group (Briech UAS, EIB Stratoc, Giga Forensics, Poctova), not an army HQ; the SPEC's military assumptions (Brigade/Battalion hierarchy, commander-first readiness view, army role titles) are superseded for the demo — the client is a group owner serving several government agencies.
- 2026-10-09 — Real subsidiary names are used over fictitious, labelled-demo data; agencies are generic labels (Client Agency A-D) mapped to CLIENT-A..D compartments, and no real agency name is attached to invented contract data.
- 2026-10-09 — Pivot Task 2: state filter lists all 36 states + FCT as a validated enum (backend/app/geo/states.py); demo data stays in the existing fictional rural Niger State sites, and no real deployment locations are derived from open sources.
- 2026-10-09 — Pivot Task 4: Contract and Delivery entity types with typed tools `contracts_status` and `deliveries_overdue`; client separation by CLIENT-x compartments; routing rules placed before the stock and UAS rules because "deliver"/"inventory" overlap; dashboard gains an "Overdue deliveries" tile.
- 2026-10-09 — Pivot Task 5: ProductionRun and SerialUnit entity types with tools `serial_trace` and `production_qc_holds`; a serial the caller may not see returns an empty table, identical to a nonexistent one (no existence leak); serials delivered to a client carry that client's compartment.
- 2026-10-09 — Pivot Task 6: group assets (command-and-control vehicle, airstrip lighting, airframe flight hours, jet fuel and oil stock) are seed rows only, answered by the existing equipment and stock tools; Briech asset rows are Secret so only the owner sees them.
