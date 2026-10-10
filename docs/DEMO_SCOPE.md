# Demo scope — what works today

Living inventory for the demo build.
Updated at every step. Component-level swap points live in `docs/STUBS.md`;
accepted production shortcuts live in `docs/PRODUCTION_DEBT.md` and are repeated
in each step's report.

> **Demo data only.** Every person, unit, document and record is fictitious.
> **The dev profile is not sovereign** — dev calls the hosted Gemini model
> through the AI gateway (AGENTS.md: never claim the dev profile is sovereign).
> SPEC §18 step 10 (sovereignty) must not be presented as working software.

## Built (real, authorized, audited, tested)

| Area | What works today |
|---|---|
| Classification & compartments | `classification_levels` ranks + compartment sets on documents, records, chunks; derived items inherit the union of their inputs. |
| Access context | Login → token → `AccessContext` (clearance, compartments, unit path, data scope, permissions) from the seeded users, with `/api/v1/me` returning display name, unit breadcrumb and permissions for the UI. |
| Authorization | `LocalPolicy.decide` before any read, `LocalPolicy.row_filter` **inside** the SQL together with Postgres row-level security; detail and cited-passage reads answer 404, never 403. |
| Audit (SPEC §14) | Hash-chained, append-only events for every query, retrieval, answer, approval and policy decision; `GET /api/v1/audit` (filterable by `event_id` for deep links) and `GET /api/v1/audit/verify` returning `valid`, `checked_count`, `first_bad_event_id` plus checkpoint and git-ledger tips. |
| AI gateway | `LLMProvider`/`EmbeddingProvider` interfaces; dev `HostedProvider` (Gemini; cache fallback or `LLM_CACHE_ONLY` replay flagged `cached=true`), local embeddings only; model and provider stored on every answer event. |
| Knowledge pathway | Question → embedding → hybrid retrieval (vector + full text, RRF) **with the authorization filter inside the query** → cited answer; `found` and `degraded` come from code paths, not from the answer text. |
| Citations & provenance | Inline citations with chunk id / document ref / page / section, re-resolvable through the same row filter; `GET /api/v1/documents/{ref}/chunks/{chunk_id}` opens the exact cited passage. |
| Assistant conversations | `POST /api/v1/assistant/query` (with history), `GET /api/v1/assistant/conversations` and `.../{id}` returning own turns with citations; cross-user reads answer 404. |
| Manipulation defences (SPEC §8.3) | Requests to ignore permissions are refused with access unchanged and recorded as a notable event; answers citing outside the evidence set are blocked (`found=false`, decision `deny`). |
| Data pathway (SPEC §8.2, §11) | `POST /api/v1/assistant/query` routes record-style requests to typed, parameterized tools (`equipment_due_for_maintenance`, `expired_certifications`, `stock_below_threshold`, `training_activity`, `uas_missions`, `detections_near_site`, `contracts_status`, `deliveries_overdue`, `serial_trace`, `production_qc_holds`, `production_runs`, `uas_fleet`, `sensors_status`, `field_personnel`, `forensic_cases`, `evidence_items`, `custody_gaps`, `custody_trail`) in `backend/app/data_queries/`. Tools reach records only through the adapter interface (`connectors/base.py`; `DemoReferenceAdapter` is the only reader of `canonical_records`), which applies `row_filter` + RLS. The response carries `result_table` (deterministic tool output) and a gateway-written explanation; a bad or out-of-scope `unit_path` is a safe refusal (`refused=true`, no SQL, no model call). One `data_query` audit event per call. |
| Connected technology data (SPEC §10.5, §11.3) | Synthetic surveillance detections, UAS missions with tracks, and forensics evidence/custody records (labelled demo data; see the forensic case workspace row) are read only through the adapter. `uas_missions` and `detections_near_site` answer "cancelled UAS missions this week" and "detections near DEP-B4"; `GET /api/v1/connected/map` returns the caller's sensors, detections and mission tracks as GeoJSON (policy row filter + RLS, audited with the returned ids, empty for roles without data access). UAS-OPS and Secret records never reach a caller without the clearance and compartment, and the Secret MSN-106 appears only for the group owner. The `/map` page renders it with MapLibre over an offline street basemap (an OpenStreetMap extract of the demo area, label fonts and sprites, all served by the app from `web/public/basemap/`; no external tiles, fonts or other hosts, checked by the UI smoke test). The demo sites sit on open rural land in Niger State, chosen so no real town or facility reads as a demo site: layer toggles, click for classification badge and a link to the record. A Replay button runs the stubbed live feed: `GET /api/v1/connected/replay` (backed by adapter `stream()`) returns visible detections in time order; the page advances a replay clock (30 simulated minutes per second) and polls, so detections appear over time. |
| Correlation (SPEC §10.6, §18.6) | The seed plants rising Stratoc Site Team 4 faults, two lapsed Vehicle Maintainer certifications and a short stock line (EIB Stratoc faults flat as control). `POST /api/v1/correlation/run` (group owner only, on demand) computes the `rising_faults` finding from the adapter and the audited typed tools and stores it with its evidence references and the analysis parameters; `GET /api/v1/correlation/findings[/{id}]` reads it through the policy row filter + RLS (404, never 403, when hidden). It is Secret because one input is Secret: derived items take the highest classification and the union of compartments (`app/correlation/derive.py`, tested directly). The Findings page lists them; the assistant answers about visible findings; the UI has a finding page with an evidence list. Run it once before the demo ("Run correlation" on the Findings page). Two more analyses run with it: `repeated_custody_gaps` (the same recorded holder in custody breaks in two or more cases: Courier R. Bala in FR-2026-014 and FR-2026-017, a Secret finding at Giga) and `qc_hold_overdue_delivery` (a production run on QC hold plus an overdue delivery for the same product in the same unit, with the contract status: Poctova PR-PO-032 / DL-204 / CT-203, and Briech PR-BR-015 / DL-101). The Findings menu page lists every finding the caller may see. |
| Contracts, deliveries, production (pivot) | Contracts and deliveries by client agency (generic Client Agency A-D, CLIENT-A..D compartments), production runs with QC holds and serial traceability, and group assets (C2 vehicle, airstrip, airframe hours, fuel) are answered by typed tools through the adapter. A serial the user may not see answers exactly like a missing one. A state filter on the map, replay and UAS tools lists all 36 states and the FCT; data sits in the fictional rural Niger State sites. |
| Group home and division dashboards | Login lands on `/home`: a card per division the caller can see (Briech UAS, EIB Stratoc, Giga Forensics, Poctova, Field Operations), with one alert number only when something needs attention. A card opens `/d/<division>`, built from audited typed tools (`GET /api/v1/divisions/{key}`); every row links to its record and evidence panel. A division the caller cannot see answers 404, like one that does not exist. Only the `owner` account is seeded; the others are archived (docs/STUBS.md). |
| Forensic case workspace | Giga's three fictional cases, six evidence items and chain-of-custody events (FORENSICS compartment, owner only). Typed tools `forensic_cases`, `evidence_items`, `custody_gaps`, `custody_trail`; `GET /api/v1/cases/{case_ref}` and the `/cases/<ref>` page show each item's custody timeline. Two planted breaks (FR-2026-017 EV-017-01, and FR-2026-014 EV-014-02, both via Courier R. Bala) are each a transfer whose recorded holder is not whoever last received the item. The assistant answers "which evidence has a custody break?". |
| Division reports | `/reports/<division>` (`GET /api/v1/reports/{key}`): the division page as a DRAFT FOR HUMAN REVIEW document, deterministic (no model), marked with the derived classification and compartments. Export to PDF or DOCX (`/export?format=`), the marking on every page; each export writes its own audit event. No approval flow. |
| Route convention | All routers under `/api/v1` (no root aliases), `/healthz` only at the root; no CORS middleware — same-origin proxy only. |
| Authorization tests | RLS-only and filter-only layers checked against a hand-authored oracle (`tests/authz/`), plus API, adversarial and tamper-evidence tests. |

## Stubbed (interface kept; swap point named)

| Item | Demo behaviour now | Swap point |
|---|---|---|
| Identity | Seeded users, shared demo password, HS256 dev JWT (`DevTokenValidator`); **no logout/revocation** — a UI logout will only clear the token client-side (docs/PRODUCTION_DEBT.md). | Keycloak OIDC/JWKS behind `TokenValidator`. |
| Policy engine | `LocalPolicy`, Python ABAC behind the `Policy` protocol. | `OpaPolicy` implementing the same `decide`/`row_filter`. |
| Tool routing | Deterministic keyword router (SPEC: the model selects the tool); logged in `docs/PRODUCTION_DEBT.md`. | Model-driven tool selection over the same registry. |
| Live streams (SPEC §10.5) | Timed replay of the seeded detections behind adapter `stream()` and `GET /api/v1/connected/replay` (stateless polling, policy row filter + RLS, audited per non-empty batch). No real feed. | Real adapter stream. |
| Job queue | `scripts/ingest_documents.py` run by hand. | Procrastinate worker. |
| On-prem model | `LocalVLLMProvider` present but fails closed (`ProviderNotConfiguredError`). | vLLM behind `LLMProvider`. |
| Reranker | Reciprocal rank fusion inside the retrieval SQL, no reranker (DEMO CUT). | `LocalRerankerProvider` after fusion. |
| Provenance store | Citations inline + in the answer audit event; no answer/evidence tables. | Answer/Evidence tables with claim-level links. |
| Map | Built: `/map` page (MapLibre, self-hosted npm package, GeoJSON from `GET /api/v1/connected/map`, offline OpenStreetMap basemap for the demo area served by the app, no external tiles). Nav item is live for roles with read access. | Tile pipeline covering the real area of operations (docs/PRODUCTION_DEBT.md). |

## Not built yet (part of the demo build)

| Item | Demo script step |
|---|---|
| Real live feeds (replay of synthetic detections is built) | §18.5 |
| Model-written narrative in division reports (reports are deterministic today) | §18.4 |
| Evaluation additions beyond the current authorization/retrieval/adversarial suite | §16 |

## Not built (spec modules outside the demo)

> All module data is demo data standing in for the client's existing systems.

| Spec module | Status in the demo |
|---|---|
| Module workspaces (Personnel, Logistics, Training) | Not shown in the UI (nav entries hidden). |
| Map and connected-systems view | Map view and timed detection replay built (MapLibre + GeoJSON over a locally hosted basemap, no external tiles). |
| Workflows and approvals | Cut (AGENTS.md DEMO CUT). |
| OCR / scanned-document ingestion | Cut. |
| Reranker | Cut; fusion only. |
| Keycloak (OIDC, real SSO) | Stubbed: seeded login behind `AccessContext`. |
| OPA policy engine | Stubbed: `LocalPolicy` behind the `Policy` interface. |
| Local vLLM provider | Interface only; fails closed. |
| Observability (metrics, tracing) | Cut. |
| Kubernetes and air-gapped profile | Cut; Docker Compose dev profile only, not sovereign. |

## Demo answer cache (prefill)

The hosted model is slow and quota-limited, so the demo can replay answers recorded
earlier. This is a convenience, not a gate: if something is missing, the demo carries on.

```bash
set -a && . ./.env && set +a
uv run python scripts/prefill_cache.py            # record (live Gemini, a few minutes)
uv run python scripts/prefill_cache.py --verify   # cache-only check
```

What to know (facts, not rules):
- Cache keys hash the exact model request (prompt + retrieved evidence + question). Changing
  prompts, the corpus, chunking, retrieval, tools or seed data changes the keys, so re-run
  the prefill after such a change. Cosmetic and UI changes do not matter.
- Record mode reuses answers already cached, so a re-run only pays for what is missing. The
  Gemini free tier allows about 20 requests a day (a full run needs about 19); a 429 means
  wait for the 00:00 UTC reset. To start afresh, delete `data/demo_llm_cache.json`.
- A failed or truncated answer is reported, never cached. Prefill and verify events carry a
  `source: "prefill"` tag in the audit viewer.
- `DEMO_DATE=2026-10-07` in `.env` pins the business date so keys do not drift with the
  calendar. Dev profile only.
- Plain re-ingest is safe: chunk ids are stable.

**If a question misses the cache on the day**, in order of preference:
1. If the Gemini key and quota are available, run without `LLM_CACHE_ONLY` and let the
   question go live. It is a dev-profile demo; the live model is allowed.
2. Otherwise the chat shows the calm "recorded answers" panel. Say so plainly and move to
   the next step. The script is a guide, not a contract; any step can be skipped or
   reordered.

Follow-up questions have their own cache keys, so lead with the scripted wording. Ad-lib
questions are fine when the live model is on.

## Run checklist

Required (the demo does not work without these):
1. `docker compose -f infra/compose.yaml up -d db`, then `cd backend && uv run alembic upgrade head`.
2. Seed and ingest: `set -a && . ./.env && set +a; uv run python -m app.seed`, then
   `uv run python scripts/ingest_documents.py`.
3. Start the API (`uv run uvicorn app.main:app --port 8001`; Windows without uv on PATH:
   `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8001 --app-dir backend`) and the
   UI (`cd web && npm run dev`, :3000).
4. Log in as `owner`, click "Run correlation" on the Findings page (the reseed clears
   findings), and check `FND-RISING-FAULTS-SITE-4` appears, labelled Secret.
5. Audit viewer: run verify. Expect `valid`, `checkpoint_ok` and `ledger_ok` true. The git
   ledger path is `C:\Users\PC\projects\gateway-audit-ledger` on this machine; elsewhere run
   `scripts/setup_audit_ledger.sh <path>` and set `AUDIT_LEDGER_PATH`.

Recommended (cheap insurance):
6. `prefill_cache.py`, then `--verify`, if anything that affects keys changed since the last
   good run.
7. One click-through of the scripted questions, as the users who ask them.

## Cut entirely (AGENTS.md DEMO CUT)

Workflows, OCR, reranker, observability, Kubernetes, air-gapped deployment
profile. Map tiles are locally hosted for the demo area only (SPEC §6: "MapLibre with
locally hosted map tiles"); nothing is fetched from an external tile service.

## Trimmed demo script (spec §18)

1. Login lands on the group home: a card per division the caller can see, alerts only where something needs attention; a card opens that division (`/d/<division>`), with its sections, record links and compliance — **works**. The Compliance page (`/compliance`) shows maintenance and certifications across all divisions.
2. Knowledge pathway with citations + open a cited page — **works against the API today**.
3. Data pathway — **works against the API today** (equipment due for maintenance, expired certifications, overdue deliveries, contracts by client, serial trace, production QC holds; map state filter). Needs a live or cached model for the explanation; the table is deterministic.
4. Reporting — built. "Prepare a summary of training activity for this command over the last quarter" drafts a report (`app/reporting/training.py`) from the `training_activity` rows plus retrieved training documents, both under the caller's row filter + RLS. The draft is bannered DRAFT FOR HUMAN REVIEW, carries the highest classification and union of compartments of every input (also stored on the conversation), cites passages, lists its source records and documents, and is blocked if it cites anything outside its inputs. Plain "show me the training activity" stays a data query. Audited as pathway `report` with record ids, chunk ids and provider. The wording is cached like other answers: run the prefill (user step) for it to work without a live model.
5. Connected systems — **works**: the map (`/map`) with timed detection replay; Giga's forensic case workspace is the evidence side: open Giga Forensics, follow the custody break to FR-2026-017 and its timeline, ask the assistant "Which evidence has a custody break?".
5b. Division report — **works**: open a division, "Prepare report", export PDF or Word; the marking is on every page and the export is in the audit log.
6. Correlation finding — **works**: the group owner clicks "Run correlation" on the Findings page (or `POST /api/v1/correlation/run`), opens the finding, follows evidence links; ask "Why are maintenance faults rising at one site?".
7. Security moment (same question, lower clearance) — **works against the API today**.
8. Manipulation attempt — **works against the API today**.
9. Audit trail + chain verification — **works against the API today**.
10. Sovereignty — **do not claim**: dev profile uses the hosted model.

### 2026-10-07 — Draft report label covers every retrieved passage, retrieval is a fixed keyword
- **Issue:** the training-summary draft retrieves document passages with the fixed query
  "training" (not model-chosen) and labels the draft with the highest classification and
  union of compartments of *all* records and passages supplied to the model, not only the
  ones it cited. The label can therefore be higher than the cited material needs. The
  report is plain text, one template, one report type; no editing, export or approval flow.
- **Why acceptable:** over-labelling is the safe direction (AGENTS.md derived items), and a
  fixed query keeps the prompt, and so the recorded answer, stable for the demo.
- **Production needs:** model- or user-selected sources with an explicit evidence list,
  label from the sources actually used, report templates, export, and a human review and
  approval step recorded in the audit log.
