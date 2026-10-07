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
| Data pathway (SPEC §8.2, §11) | `POST /api/v1/assistant/query` routes record-style requests to typed, parameterized tools (`equipment_due_for_maintenance`, `expired_certifications`) in `backend/app/data_queries/`. Tools reach records only through the adapter interface (`connectors/base.py`; `DemoReferenceAdapter` is the only reader of `canonical_records`), which applies `row_filter` + RLS. The response carries `result_table` (deterministic tool output) and a gateway-written explanation; a bad or out-of-scope `unit_path` is a safe refusal (`refused=true`, no SQL, no model call). One `data_query` audit event per call. |
| Route convention | All routers under `/api/v1` (no root aliases), `/healthz` only at the root; no CORS middleware — same-origin proxy only. |
| Authorization tests | RLS-only and filter-only layers checked against a hand-authored oracle (`tests/authz/`), plus API, adversarial and tamper-evidence tests. |

## Stubbed (interface kept; swap point named)

| Item | Demo behaviour now | Swap point |
|---|---|---|
| Identity | Seeded users, shared demo password, HS256 dev JWT (`DevTokenValidator`); **no logout/revocation** — a UI logout will only clear the token client-side (docs/PRODUCTION_DEBT.md). | Keycloak OIDC/JWKS behind `TokenValidator`. |
| Policy engine | `LocalPolicy`, Python ABAC behind the `Policy` protocol. | `OpaPolicy` implementing the same `decide`/`row_filter`. |
| Tool routing | Deterministic keyword router (SPEC: the model selects the tool); logged in `docs/PRODUCTION_DEBT.md`. | Model-driven tool selection over the same registry. |
| Live streams (SPEC §10.5) | None yet; timed replay of synthetic events planned behind the adapter `stream()` contract. | Real adapter stream. |
| Job queue | `scripts/ingest_documents.py` run by hand. | Procrastinate worker. |
| On-prem model | `LocalVLLMProvider` present but fails closed (`ProviderNotConfiguredError`). | vLLM behind `LLMProvider`. |
| Reranker | Reciprocal rank fusion inside the retrieval SQL, no reranker (DEMO CUT). | `LocalRerankerProvider` after fusion. |
| Provenance store | Citations inline + in the answer audit event; no answer/evidence tables. | Answer/Evidence tables with claim-level links. |
| Map | Not built. MapLibre + GeoJSON only, no external tiles (air-gap). | — |

## Not built yet (part of the demo build)

| Item | Demo script step |
|---|---|
| Next.js UI (login, dashboard, chat, citation viewer, audit viewer, evidence panel) | §18.1 and every later step's presentation |
| Remaining typed tools for the data pathway (2 of 4–5 built: maintenance, expired certifications) | §18.3 |
| Administrative/report drafting over records and documents | §18.4 |
| Connected-systems map and timed synthetic feeds (surveillance, UAS, forensics) | §18.5 |
| One planted correlation finding with its evidence panel | §18.6 |
| Evaluation additions beyond the current authorization/retrieval/adversarial suite | §16 |

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
> a different day, which shifts the seeded dates) invalidates the cache**. A stale cache
> does not fail quietly into wrong answers: a miss in cache-only mode is a 503. Ask each
> demo question as the first message of a new chat; follow-ups carry history and have
> their own keys. The prefill and verify runs add queries and audit events to the dev
> database; they appear in the demo audit trail.

## Cut entirely (AGENTS.md DEMO CUT)

Workflows, OCR, reranker, observability, Kubernetes, air-gapped deployment
profile. Map tiles are cut too (MapLibre renders GeoJSON without them).

## Trimmed demo script (spec §18)

1. Login — API ready, dashboard waits for the UI (Part B).
2. Knowledge pathway with citations + open a cited page — **works against the API today**.
3. Data pathway — **works against the API today** (equipment due for maintenance, expired certifications; more tools to come). Needs a live or cached model for the explanation; the table is deterministic.
4. Reporting — pending.
5. Connected systems — pending.
6. Correlation finding — pending.
7. Security moment (same question, lower clearance) — **works against the API today**.
8. Manipulation attempt — **works against the API today**.
9. Audit trail + chain verification — **works against the API today**.
10. Sovereignty — **do not claim**: dev profile uses the hosted model.
