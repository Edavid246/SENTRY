# Stubs, cuts and deferrals

Everything here is deliberate, per AGENTS.md (DEMO CUT) and docs/SPEC.md.
Each entry: what the spec says → what the demo build does → how the real
component slots in. **Demo build only; never claim the dev profile is sovereign.**

## Stubbed (interface kept, real component later)

| Spec component | Spec | Demo implementation | Later |
|---|---|---|---|
| Identity | Keycloak, password+OTP (SPEC §4, §6, §7.1) | Seeded users, shared demo password, HS256 dev JWT behind `TokenValidator`; `users.keycloak_id` column reserved | Replace validator with Keycloak JWKS/OIDC |
| Policy engine | OPA with partial evaluation (SPEC §7.3) | `LocalPolicy`, Python ABAC behind the `Policy` protocol (`decide` + `row_filter`) | `OpaPolicy` implements same protocol |
| Job queue | Procrastinate worker (SPEC §6, §5.2) | `scripts/` run manually (seed today; ingestion/sync later) | Worker service |
| Live streams | SSE live feeds (SPEC §6, §10.5) | Timed replay of synthetic events (later slice) | Real adapter `stream()` |
| Audit hash chain | Hash-chained append-only audit (SPEC §14) | `audit_events` table created, append-only grants applied; chain/verify **not implemented yet** (audit becomes real next slice) | `audit` package implementation |

## Deferred (not yet built; part of the demo build)

| Item | Note |
|---|---|
| Web app (Next.js) | Deferred per build decision — steps 1–6 are API + database only; `web` service will be added to Compose later. Air-gap rules apply when it lands (system fonts, no CDNs). |
| `assistant`, `knowledge`, `data_queries`, `connectors`, `ai_gateway`, `modules`, `correlation`, `provenance` | Package scaffolds/interfaces as their slices arrive. |
| FTS / hybrid search | Chunk search uses `ILIKE` for now; Postgres full-text + vector search arrive with the knowledge slice. |
| Vector index | **No HNSW (or IVFFlat) index on `chunks.embedding`** — chunks use exact (sequential) search; corpus is tiny and memory is constrained. Add an index with the knowledge slice when data grows. |
| CI service | GitHub Actions skipped (no git remote). `scripts/check.sh` runs ruff, pytest and the air-gap grep locally. |

## Cut entirely (AGENTS.md DEMO CUT)

Workflows, OCR (Tesseract), reranker (`RerankerProvider`), observability
(OpenTelemetry/Prometheus/Grafana/Loki), Kubernetes profile, air-gapped
deployment profile, map tiles (map = MapLibre + GeoJSON only, no tiles).
