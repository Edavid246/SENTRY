# Defence Gateway AI: MVP build

## Authority
Scope for the demo: docs/DEMO_SCOPE.md and the DEMO CUT section below.
Target design: docs/SPEC.md (v0.1 draft). It binds on the INVARIANTS below; everywhere
else it is a default.
- Invariant affected, or spec and code disagree on one: stop and ask.
- Anything else (stack, phase order, tool choice, UI, file layout): deviate if it is
  better, and add a dated one-line entry to docs/DECISIONS.md.

## Invariants (never loosen, never stub away)
- **Principle Zero.** The AI layer is never the authorization boundary. Authorization
  decides access BEFORE retrieval; the filter runs inside the query, backed by Postgres
  row-level security. The model only receives data the user is cleared for.
  Never: user -> LLM -> database with "don't reveal" instructions.
- Hidden records answer 404, never 403.
- Derived items (summaries, findings, reports) inherit the highest classification and the
  union of compartments of their inputs.
- Every query, retrieval, answer, approval and policy decision writes a hash-chained,
  append-only audit event. Every answer stores its provenance chain.
- Adapters are read-only. All source systems, including our reference systems, are reached
  only through the adapter interface (describe/search/get/stream/sync).
- Structured questions use typed, parameterized query tools. The model never writes raw SQL.
  Whether the tool is chosen by the model or by a deterministic router is a default, not
  an invariant; parameters are always validated.
- The assistant informs; humans decide. No operational actions.
- No external CDNs, fonts, map tiles or telemetry. The hosted LLM is reachable only through
  the AI gateway and can be disabled by config.
- Everything is demo data: fictitious, labelled as such. Never claim the dev profile is
  sovereign, and never present recorded answers as live.
- Never read, print, or commit .env or secrets.

## Defaults (replaceable; keep the interface, not the product)
Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 + pgvector, Next.js +
TypeScript, MapLibre, Docker Compose. Spec Section 6 lists the full target stack
(Keycloak, OPA, Procrastinate, observability, Kubernetes): treat it as the destination.
What must hold are the seams: Policy, TokenValidator, LLMProvider, EmbeddingProvider,
adapter interface.

## Models
All model calls go through AI gateway interfaces: LLMProvider, EmbeddingProvider.
Dev uses HostedProvider (Gemini). On-prem later uses LocalVLLMProvider.
Embeddings are always local. Provider and model come from config, never hardcoded.

## DEMO CUT
No deadline: build as far as the work needs.
Deliberately deviates from the spec's phase order. Build the vertical slice in docs/DEMO_SCOPE.md. Stub everything else behind the spec's interfaces so the real
component slots in.
REAL: classification and compartments, access context, Postgres row-level security,
hash-chained audit with verify, AI gateway (Gemini dev + local embeddings), knowledge
pathway with filter inside the query and citations, typed query tools, one planted
correlation finding, provenance/evidence panel, authorization + adversarial tests.
STUBBED: Keycloak (seeded login behind AccessContext), OPA (Python policy function behind
a Policy interface), live streams (timed replay of synthetic events), job queue (scripts).
CUT: workflows, OCR, reranker, observability, Kubernetes, air-gapped profile.
Map uses MapLibre with GeoJSON and no external tiles.
List every stub in docs/STUBS.md. Demo script: spec Section 18, trimmed.

## Working style
Plan first, then build. Run tests per task and show the output; commit each working task
with a clear message. Authorization tests run on every change and grow every phase; the
wider evaluation suite runs before releases.
Keep memory low: 16 GB dev machine, no GPU.
Shortcuts and stubs: record plain stubs in docs/STUBS.md. Record in
docs/PRODUCTION_DEBT.md (dated) only shortcuts that matter for security, accreditation or
data handling, and mention those in one line in the end-of-task report.

## DEMO-ONLY TOOLING NOTE
Demo build uses a free-tier coding model (Big Pickle) that may retain prompts. Accepted for
the demo only. The production build must use zero-retention or on-prem tooling and keep the
spec, client material, and keys out of any third-party model's reach.
