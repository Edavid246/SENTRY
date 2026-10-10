# Stubs, cuts and deferrals

Everything here is deliberate, per AGENTS.md (DEMO CUT) and docs/SPEC.md.
Each entry: what the spec says → what the demo build does → how the real
component slots in. **Demo build only; never claim the dev profile is sovereign.**

## Stubbed (interface kept, real component later)

| Spec component | Spec | Demo implementation | Later |
|---|---|---|---|
| Identity | Keycloak, password+OTP (SPEC §4, §6, §7.1) | Seeded users, shared demo password, HS256 dev JWT behind `TokenValidator`; `users.keycloak_id` column reserved | Replace validator with Keycloak JWKS/OIDC |
| Policy engine | OPA with partial evaluation (SPEC §7.3) | `LocalPolicy`, Python ABAC behind the `Policy` protocol (`decide` + `row_filter`) | `OpaPolicy` implements same protocol; swap it in at `get_policy()` (`app/authz/policy.py`), the one wiring point |
| Job queue | Procrastinate worker (SPEC §6, §5.2) | `scripts/` run manually (seed today; ingestion/sync later) | Worker service |
| Tool selection | Model selects a typed tool (SPEC §8.2) | Keyword router in `data_queries/routing.py`; the registry and tool contracts are the real ones | Model picks from `REGISTRY`; authorization is unchanged because tools authorize themselves |
| Source-system adapters | One adapter per source system (SPEC §11) | A single `DemoReferenceAdapter` over `canonical_records`; `stream()` replays seeded detections, `sync()` is a no-op | Per-system adapters behind `SourceAdapter`; only the translation layer changes |
| Live streams | SSE live feeds (SPEC §6, §10.5) | Timed replay of seeded detections: adapter `stream()` + polled `GET /api/v1/connected/replay`, driven by the map page's replay clock (not SSE) | Real adapter `stream()` |
| Surveillance / UAS / forensics systems | Client systems behind read-only adapters (SPEC §11.3) | Synthetic records REC-046..062 in `canonical_records`: ONVIF-style detections, MAVLink/MISB-style missions (a short track inside the mission record instead of `TrackPoint` rows), CASE/UCO-style evidence and custody records, read through the one `DemoReferenceAdapter`. No generator job: the seed holds them. Detection times are offsets from noon on the demo date | Per-system adapters; only the translation layer is rewritten |
| LLM provider | `LocalVLLMProvider` for on-prem inference (SPEC §8.1) | Dev profile uses `HostedProvider` (Gemini over HTTPS, `LLM_PROVIDER=hosted`, model `gemini-3.5-flash` — name deviation logged in docs/PRODUCTION_DEBT.md); `LocalVLLMProvider` occupies the interface and fails closed with `ProviderNotConfiguredError` | vLLM/OpenAI-compatible service behind the same `LLMProvider` protocol |
| Retrieval fusion | Hybrid search with reranking (SPEC §8.1, §8.2) | Reciprocal rank fusion of vector similarity + full-text inside the retrieval SQL; **no reranker** (DEMO CUT); if the embedder is unavailable, retrieval degrades to full-text only (logged in docs/PRODUCTION_DEBT.md) | `LocalRerankerProvider` after fusion |
| Knowledge provenance | `Answer` + `Evidence` entities per answer (SPEC §12, §13) | Citations are returned inline with the answer and stored in the answer audit event (full provenance chain); no separate answer/evidence tables yet | Dedicated Answer/Evidence tables with claim-level links |

## Deferred (not yet built; part of the demo build)

| Item | Note |
|---|---|
| Web app (Next.js) | Deferred per build decision — steps 1–6 are API + database only; `web` service will be added to Compose later. Air-gap rules apply when it lands (system fonts, no CDNs). |
| `modules`, `correlation`, `provenance` | Package scaffolds/interfaces as their slices arrive. (`assistant` and `knowledge` landed with step 9; `connectors` and `data_queries` with Task 2.) |
| Vector index | **No HNSW (or IVFFlat) index on `chunks.embedding`** — chunks use exact (sequential) search; corpus is tiny and memory is constrained. Add an index when data grows. |
| CI service | GitHub Actions skipped (no git remote). `scripts/check.sh` runs ruff, pytest and the air-gap grep locally. |
| LLM response-cache prefill | Offline only: `scripts/prefill_cache.py` drives the real pipeline as each demo user with `LLM_CACHE_RECORD=1` (dev profile only) to write `data/demo_llm_cache.json`; `LLM_CACHE_ONLY=1` replays it with the hosted provider disabled. No in-app or API prefill. |

## Cut entirely (AGENTS.md DEMO CUT)

Workflows, OCR (Tesseract), reranker (`RerankerProvider` — retrieval uses
reciprocal rank fusion instead), observability
(OpenTelemetry/Prometheus/Grafana/Loki), Kubernetes profile, air-gapped
deployment profile. Map tiles are not cut but reduced: one small offline OpenStreetMap
extract of the demo area, served by the web app (`web/public/basemap/README.md`).

## Demo-only tooling

`reportlab` is also a **runtime** dependency since Phase E: division reports export to PDF with it, and to
DOCX with `python-docx` (`backend/app/reporting/export.py`). Both run in-process on the standard fonts and
fetch nothing. `scripts/generate_demo_documents.py` still uses them to write the fictitious DOC-201..204
corpus (the generated files and manifest are committed).

## Division reports

Reports are deterministic: the rows of the division dashboard, set out as a document, with the DRAFT banner,
the derived marking and the source list. No model writes any of it, so nothing in it can be invented.
Swap point: a model-drafted narrative over the same rows, through `LLMProvider`, with the citation checks of
`app/reporting/training.py`. There is no approval flow; people review and decide.

## Archived accounts

Only `owner` is seeded. `logistics.head`, `coo`, `briech.lead`, `group.it`, `group.audit` are kept in
`ARCHIVED_USERS` (`backend/app/seed/identity.py`); tests seed them with `include_archived=True`. Restore one by
moving its entry to `USERS` and reseeding.

## Pivot data (Tasks 4-6)

- **Contracts, deliveries, production runs, serials, group assets:** invented rows in the
  `contracts-demo` and `production-demo` source systems, read through the demo reference
  adapter. Swap point: real contract/ERP and MES/serial-tracking adapters implementing the
  adapter interface (describe/search/get/stream/sync), read-only.
- **Client agencies:** generic labels (Client Agency A-D) mapped to CLIENT-A..D compartments.
  Swap point: the client's real agency list and compartment mapping.
- **State filter:** lists every state and the FCT, but only the fictional rural Niger State
  sites carry data.
