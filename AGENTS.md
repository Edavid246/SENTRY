# Defence Gateway AI: MVP build

## Authority
docs/SPEC.md (MVP Technical Specification v0.1) is the source of truth.
If code and spec disagree, stop and ask. Never silently deviate, except where the
DEMO CUT section below says so.

## Principle Zero
The AI layer is never the authorization boundary. Authorization decides access BEFORE
retrieval. The model only ever receives data the user is cleared for.
Never: user -> LLM -> database with "don't reveal" instructions.

## Hard rules
- Everything is demo data: fictitious people, units, documents, records, labelled as such.
  Surveillance, UAS, and forensic data is synthetic, modelled on ONVIF, MAVLink/MISB, CASE/UCO.
- Adapters are read-only. All source systems, including our reference systems, are reached
  only through the adapter interface (describe/search/get/stream/sync).
- Structured questions use typed, parameterized query tools. The model never writes raw SQL.
- Derived items (summaries, findings) inherit the highest classification and the union of
  compartments of their inputs.
- Every query, retrieval, answer, approval and policy decision writes a hash-chained,
  append-only audit event. Every answer stores its provenance chain.
- The assistant informs; humans decide. No operational actions.
- Air-gap rules from day one: no external CDNs, fonts, map tiles, telemetry. The hosted
  LLM is reachable only through the AI gateway and can be disabled by config.
- Never read, print, or commit .env or secrets.

## Stack
Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 + pgvector, Next.js +
TypeScript, MapLibre, Docker Compose. Full target stack in spec Section 6.

## Models
All model calls go through AI gateway interfaces: LLMProvider, EmbeddingProvider.
Dev uses HostedProvider (Gemini). On-prem later uses LocalVLLMProvider.
Embeddings are always local. Provider and model come from config, never hardcoded.

## DEMO CUT (deadline: Monday 12 October 2026)
Deliberately deviates from the spec's phase order. Build the vertical slice below.
Stub everything else behind the spec's interfaces so the real component slots in.
REAL: classification and compartments, access context, Postgres row-level security,
hash-chained audit with verify, AI gateway (Gemini dev + local embeddings), knowledge
pathway with filter inside the query and citations, 4-5 typed query tools, one planted
correlation finding, provenance/evidence panel, authorization + adversarial tests.
STUBBED: Keycloak (seeded login behind AccessContext), OPA (Python policy function behind
a Policy interface), live streams (timed replay of synthetic events), job queue (scripts).
CUT: workflows, OCR, reranker, observability, Kubernetes, air-gapped profile.
Map uses MapLibre with GeoJSON and no external tiles.
List every stub in docs/STUBS.md. Demo script: spec Section 18, trimmed.
Never claim the dev profile is sovereign.

## Working style
Plan first, then build. Run tests after each step and show the output.
Commit after each working step with a clear message.
Authorization tests start immediately and grow every phase.
Keep memory low: 16 GB dev machine, no GPU.
