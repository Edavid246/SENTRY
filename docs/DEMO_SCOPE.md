# Demo scope — what works today

Living inventory for the demo build (DEMO CUT deadline: Monday 12 October 2026).
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
| Data pathway (SPEC §8.2, §11) | `POST /api/v1/assistant/query` routes record-style requests to typed, parameterized tools (`equipment_due_for_maintenance`, `expired_certifications`, `stock_below_threshold`, `training_activity`, `uas_missions`, `detections_near_site`) in `backend/app/data_queries/`. Tools reach records only through the adapter interface (`connectors/base.py`; `DemoReferenceAdapter` is the only reader of `canonical_records`), which applies `row_filter` + RLS. The response carries `result_table` (deterministic tool output) and a gateway-written explanation; a bad or out-of-scope `unit_path` is a safe refusal (`refused=true`, no SQL, no model call). One `data_query` audit event per call. |
| Dashboard (SPEC §18.1) | `GET /api/v1/dashboard/summary`: four tiles (readiness, maintenance backlog, expiring certifications, recent findings), permission-aware per caller, audited (decide + query with item ids), 403 for roles without data access. Maintenance backlog (overdue equipment) and certifications (expired, not "expiring": the tool reports lapsed ones) are **real** typed-tool results grouped by unit, `stub: false`, each count inheriting the highest classification and union of compartments of its records. Readiness and recent findings are still placeholder fixtures (`stub: true`, tagged PLACEHOLDER DATA); findings become real in D2. Result-table rows link to `GET /api/v1/records/{source_ref}` (adapter + row filter, 404 when not visible). Login lands here. |
| Connected technology data (SPEC §10.5, §11.3) | Synthetic surveillance detections, UAS missions with tracks, and forensics evidence/custody records (REC-046..062, labelled demo data) are read only through the adapter. `uas_missions` and `detections_near_site` answer "cancelled UAS missions this week" and "detections near DEP-B4"; `GET /api/v1/connected/map` returns the caller's sensors, detections and mission tracks as GeoJSON (policy row filter + RLS, audited with the returned ids, empty for roles without data access). UAS-OPS and Secret records never reach a caller without the clearance and compartment, and the Secret MSN-106 appears only for the commander. The `/map` page renders it with MapLibre (flat background and local graticule, no tiles, glyphs or sprites): layer toggles, click for classification badge and a link to the record. No timed replay yet. |
| Correlation (SPEC §10.6, §18.6) | The seed plants rising Bn 4 faults, two lapsed Vehicle Maintainer certifications and a short stock line (Bde 2 faults flat as control). `POST /api/v1/correlation/run` (commander only, on demand) computes the `rising_faults` finding from the adapter and the audited typed tools and stores it with its evidence references and the analysis parameters; `GET /api/v1/correlation/findings[/{id}]` reads it through the policy row filter + RLS (404, never 403, when hidden). It is Secret because one input is Secret: derived items take the highest classification and the union of compartments (`app/correlation/derive.py`, tested directly). Dashboard findings tile is real; the assistant answers about visible findings; the UI has a finding page with an evidence list. Run it once before the demo (dashboard "Run correlation"). |
| Route convention | All routers under `/api/v1` (no root aliases), `/healthz` only at the root; no CORS middleware — same-origin proxy only. |
| Authorization tests | RLS-only and filter-only layers checked against a hand-authored oracle (`tests/authz/`), plus API, adversarial and tamper-evidence tests. |

## Stubbed (interface kept; swap point named)

| Item | Demo behaviour now | Swap point |
|---|---|---|
| Identity | Seeded users, shared demo password, HS256 dev JWT (`DevTokenValidator`); **no logout/revocation** — a UI logout will only clear the token client-side (docs/PRODUCTION_DEBT.md). | Keycloak OIDC/JWKS behind `TokenValidator`. |
| Policy engine | `LocalPolicy`, Python ABAC behind the `Policy` protocol. | `OpaPolicy` implementing the same `decide`/`row_filter`. |
| Tool routing | Deterministic keyword router (SPEC: the model selects the tool); logged in `docs/PRODUCTION_DEBT.md`. | Model-driven tool selection over the same registry. |
| Live streams (SPEC §10.5) | None yet (`stream()` raises); timed replay of synthetic events planned behind the adapter `stream()` contract. | Real adapter stream. |
| Job queue | `scripts/ingest_documents.py` run by hand. | Procrastinate worker. |
| On-prem model | `LocalVLLMProvider` present but fails closed (`ProviderNotConfiguredError`). | vLLM behind `LLMProvider`. |
| Reranker | Reciprocal rank fusion inside the retrieval SQL, no reranker (DEMO CUT). | `LocalRerankerProvider` after fusion. |
| Provenance store | Citations inline + in the answer audit event; no answer/evidence tables. | Answer/Evidence tables with claim-level links. |
| Map | Built: `/map` page (MapLibre, self-hosted npm package, GeoJSON from `GET /api/v1/connected/map`, no external tiles). Nav item is live for roles with read access. | — |

## Not built yet (part of the demo build)

| Item | Demo script step |
|---|---|
| Next.js UI (login, dashboard, chat, citation viewer, audit viewer, evidence panel) | §18.1 and every later step's presentation |
| Administrative/report drafting over records and documents | §18.4 |
| Timed replay of the synthetic feed (data, tools, map endpoint and map view are built) | §18.5 |
| Evaluation additions beyond the current authorization/retrieval/adversarial suite | §16 |

## Not built (spec modules outside the Monday demo)

> All module data is demo data standing in for the client's existing systems.

| Spec module | Status in the demo |
|---|---|
| Module workspaces (Personnel, Logistics, Training) | Nav entries shown greyed out, marked "Not in demo". |
| Map and connected-systems view | Map view built (MapLibre + GeoJSON, no tiles); timed replay not built. |
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
earlier. `scripts/prefill_cache.py` logs in as each demo user (the asker plus `a.bello`
and `t.adeyemi`), asks every `built` assistant question in `data/demo_questions.json`
through `POST /api/v1/assistant/query` with `LLM_CACHE_RECORD=1` (refused unless
`APP_PROFILE=dev`), and writes `data/demo_llm_cache.json`. `--verify` then re-asks every
pair with the hosted provider disabled (`LLM_CACHE_ONLY=1`, key ignored) and prints a
pass/fail table. A failure is reported, never filled with a placeholder answer.

```bash
set -a && . ./.env && set +a
uv run python scripts/prefill_cache.py            # record (live Gemini, a few minutes)
uv run python scripts/prefill_cache.py --verify   # cache-only check
```

> **Re-run the prefill after the code freeze.** Cache keys hash the exact model request
> (system prompt + retrieved evidence + question), so **any change to prompts, the
> corpus, chunking, retrieval, typed tools or the seeded data (including re-seeding on
> a different day without the pin below) invalidates the cache**. A stale cache
> does not fail quietly into wrong answers: a miss in cache-only mode is a 503. Ask each
> demo question as the first message of a new chat; follow-ups carry history and have
> their own keys. The prefill and verify runs add queries and audit events to the dev
> database; every one of those events is tagged `source: "prefill"` (or
> `"prefill-verify"`) in its audit payload and shows as a badge in the audit viewer.
> The tag never reaches a prompt or a cache key.
>
> **A cache miss never shows an error.** If the assistant answers 503 (nothing recorded for
> that question in cache-only mode) or says nothing for 30 seconds, the chat shows a calm
> panel: "This demonstration runs on recorded answers for its scripted questions. Live
> model access is disabled in this environment." The wait ends at 30 s (the request is
> abandoned in the browser; the server still logged it). `web/smoke/cache_miss.mjs`
> checks both paths with Playwright against `STUB_MODE=unavailable web/smoke/stub_api.py`.
>
> **`DEMO_DATE=2026-10-07` for the demo.** One setting pins the business date for exactly
> two things: the seed's date offsets and the data tools' cutoffs ("due within 30
> days", "expired"). Those decide which records reach a model prompt, so with the pin
> the cache keys do not move as the calendar does. Set it in `.env` for the prefill,
> the verify run and the demo, and re-seed with it
> (`DEMO_DATE=2026-10-07 python -m app.seed`, then the ingest script). Unset (the
> default) means the live clock. It is dev-profile only (the API refuses to start
> otherwise) and never touches audit timestamps, token times, `created_at` or
> `retrieved_at`. The dev database was seeded on 2026-10-07, so it already matches.
>
> **Ingest.** A plain re-ingest is safe: chunk ids are uuid5 of document ref + chunk
> index, and a test proves two from-scratch ingests give identical ids and text.
> Regenerating the documents or changing the chunker invalidates the cache.
>
> **Verify in the way you demo.** If the demo runs in compose, start the API with
> `LLM_CACHE_ONLY=1` and click through each question once as the real user before
> Monday. Evidence is sorted by chunk id in the prompt so ranking noise cannot change
> a key, but only a run in the demo configuration proves it.

## Cut entirely (AGENTS.md DEMO CUT)

Workflows, OCR, reranker, observability, Kubernetes, air-gapped deployment
profile. Map tiles are cut too (MapLibre renders GeoJSON without them).

## Trimmed demo script (spec §18)

1. Login lands on the dashboard (permission-aware tiles) — **works**.
2. Knowledge pathway with citations + open a cited page — **works against the API today**.
3. Data pathway — **works against the API today** (equipment due for maintenance, expired certifications; more tools to come). Needs a live or cached model for the explanation; the table is deterministic.
4. Reporting — the data half works (`training_activity`: "summary of training activity over the last quarter" returns the table and an explanation); the drafted report document is **not built**.
5. Connected systems — pending.
6. Correlation finding — **works**: commander clicks "Run correlation" on the dashboard (or `POST /api/v1/correlation/run`), opens the finding, follows evidence links; ask "Why are maintenance faults rising in one battalion?".
7. Security moment (same question, lower clearance) — **works against the API today**.
8. Manipulation attempt — **works against the API today**.
9. Audit trail + chain verification — **works against the API today**.
10. Sovereignty — **do not claim**: dev profile uses the hosted model.
