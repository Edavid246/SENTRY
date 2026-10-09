# Defence Gateway AI — MVP

> **Demo build.** Every person, unit, document and record in this repository is
> **fictitious demo data**. The MVP is not security-accredited, and the **dev
> profile is not sovereign** — development calls a hosted model (Google Gemini)
> through the AI gateway. See [docs/DEMO_SCOPE.md](docs/DEMO_SCOPE.md) for what
> works today and [docs/STUBS.md](docs/STUBS.md) for what is stubbed.

A classified-document assistant for defence staff: ask a question in natural
language, get an answer grounded in the documents you are cleared to see — cited
down to the page — while every retrieval, answer, and access decision is written
to a hash-chained, append-only audit trail.

**Principle Zero:** the AI layer is never the authorization boundary. Access is
decided **before** retrieval, so the model only ever receives data the caller is
cleared for — never `user → LLM → database` with "don't reveal" instructions.

## What the MVP does

| Area | Behaviour |
|---|---|
| Classification & compartments | Secret/Confidential/Restricted/Unclassified plus compartment sets (UAS-OPS, FORENSICS) on every document, record and chunk. Derived answers inherit the union of their inputs. |
| Authorization | Policy decision first, then a parameterized row filter **inside** the SQL together with Postgres row-level security. Restricted detail reads answer `404`, never `403`. |
| Knowledge pathway | Question → local embedding → hybrid retrieval (vector + full-text, reciprocal rank fusion) **filtered inside the query** → cited answer. Answers report `found` (did the evidence exist?) and `degraded` (did the vector channel run?). |
| Citations | Inline citations resolve to the exact passage via `GET /api/v1/documents/{ref}/chunks/{chunk_id}`, through the same authorization path. |
| Audit trail (SPEC §14) | Every query, retrieval, answer and decision is hash-chained with a checkpoint file and a git ledger; `GET /api/v1/audit/verify` reports `valid`, `checked_count`, `first_bad_event_id` and both external tips. |
| AI gateway | `LLMProvider`/`EmbeddingProvider` interfaces. Dev uses a hosted model with a response-cache fallback; embeddings are always local. Production swaps in on-prem inference behind the same interface. |
| Defences | Requests to ignore permissions are refused with access unchanged and flagged as notable events; answers citing outside the evidence set are blocked. |

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 + pgvector ·
Docker Compose · Next.js + TypeScript + Tailwind (MapLibre lands later) ·
`uv` for dependency management.

## Quick start

```bash
# 1. Postgres (pgvector/pg16) on localhost:5434
docker compose -f infra/compose.yaml up -d db

# 2. Install dependencies
uv sync

# 3. Schema + demo corpus (idempotent)
cd backend && uv run alembic upgrade head && cd ..
uv run python -m app.seed
# optional: also seed the archived restricted accounts (restricted-view demos, web smoke test)
# uv run python -m app.seed --include-archived
uv run python scripts/ingest_documents.py   # parses DOC-201..204, embeds locally (first run downloads the model)

# 4. Run the API (http://localhost:8001, docs at /docs)
uv run uvicorn app.main:app --reload --port 8001
```

Or run the database and the API container together:

```bash
docker compose -f infra/compose.yaml up -d --build   # db on :5434, api on :8001
```

> **AI key (optional):** set `GEMINI_API_KEY` (or `HOSTED_API_KEY`) in `.env` for
> live answers — copy `.env.example` to `.env` first. Without it the assistant
> answers 503 (a missing key is never masked). To run the demo from the
> prefilled response cache instead, set `LLM_CACHE_ONLY=1`; record that cache
> with `scripts/prefill_cache.py` (see `docs/DEMO_SCOPE.md`). Never commit `.env`.

## Start the UI

The browser only calls same-origin `/api/*`; Next.js rewrites it to the API
(`API_URL`, default `http://localhost:8001`). No CORS, no CDN, no telemetry.

```bash
cd web && npm ci && npm run dev      # http://localhost:3000 (API on :8001)
# or, with everything in containers:
docker compose -f infra/compose.yaml up -d --build   # adds web on :3000
npm run gen:api                       # regenerate src/lib/api-types.ts from /openapi.json
```

Sign in as any demo user below. The JWT is held in memory and `sessionStorage`
only; logout clears it in the browser (the token stays valid until expiry, see
docs/PRODUCTION_DEBT.md).

## Run the checks

```bash
./scripts/check.sh   # ruff lint + format, pytest, web eslint + tsc, air-gap scan
```

The suite includes the authorization layers (RLS-only and filter-only against a
hand-authored oracle), API tests, adversarial/audit tests and tamper-evidence
tests for the hash chain.

## Demo users

All names, units and documents are fictitious.

| User | Role | Unit | Clearance | Compartments |
|---|---|---|---|---|
| Group Owner (`owner`) | Commander role | EIB Group | Government-sensitive | UAS-OPS, FORENSICS, CLIENT-A..D |

Only `owner` is seeded and can log in. Five restricted accounts (`logistics.head`, `coo`,
`briech.lead`, `group.it`, `group.audit`) are archived in `ARCHIVED_USERS` in `backend/app/seed.py`;
only the authorization tests load them (`include_archived=True`). To restore one, move its entry
back into `USERS` and reseed.

Shared demo password: `Demo!Gateway2026` (dev seed only).

## API surface

All routes are mounted under `/api/v1` (system health check at `/healthz`):

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/login` | Token for a seeded demo user |
| `GET` | `/api/v1/me` | Identity: display name, unit breadcrumb, permissions |
| `GET` | `/api/v1/documents` | Documents visible to the caller |
| `GET` | `/api/v1/documents/{ref}` | Document detail (404 when not visible) |
| `GET` | `/api/v1/documents/{ref}/chunks/{chunk_id}` | Cited-passage viewer |
| `GET` | `/api/v1/records` | Canonical records visible to the caller |
| `POST` | `/api/v1/assistant/query` | Cited question answering (`found`, `degraded`, `refused`); record-style requests return a `result_table` from a typed data tool |
| `GET` | `/api/v1/assistant/conversations` | The caller's own threads |
| `GET` | `/api/v1/assistant/conversations/{id}` | Turns with resolved citations |
| `GET` | `/api/v1/audit` | Audit events (filter by `event_id`) |
| `GET` | `/api/v1/audit/verify` | Chain, checkpoint and ledger verification |

## Repository layout

```
backend/          FastAPI app: api/ authz/ audit/ knowledge/ ai_gateway/ connectors/
  alembic/        Schema migrations (RLS policies included)
data/             Fictitious demo corpus, seed inputs, demo questions
docs/             SPEC.md (source of truth), DEMO_SCOPE, STUBS, PRODUCTION_DEBT
web/              Next.js UI: login, assistant chat, audit viewer
infra/            Docker Compose, Postgres init, RLS guards
scripts/          check.sh, seeding, document generation, gateway smoke test
tests/            authz (RLS-only/filter-only oracles), api, audit, knowledge
```

## Documentation

- [docs/SPEC.md](docs/SPEC.md) — MVP Technical Specification (source of truth)
- [docs/DEMO_SCOPE.md](docs/DEMO_SCOPE.md) — what is built, stubbed, and cut today
- [docs/STUBS.md](docs/STUBS.md) — every stub and its swap point
- [docs/PRODUCTION_DEBT.md](docs/PRODUCTION_DEBT.md) — accepted demo shortcuts and what production requires
- [AGENTS.md](AGENTS.md) — build rules, including Principle Zero and the DEMO CUT

## Air-gap rules

No external CDNs, fonts, map tiles or telemetry. The API serves same-origin only
(no CORS middleware). Embeddings run locally; the hosted model is reachable only
through the AI gateway and can be disabled by configuration. `scripts/check.sh`
scans for external resource references on every run.

## License

All rights reserved. No license file is provided — this is client demo work.
