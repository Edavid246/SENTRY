# Production debt

Shortcuts accepted **for the demo build only** (DEMO CUT deadline: Monday 12 October
2026). Each entry says what is wrong, why it is acceptable now, and what production
requires. Grouped by area.

**Standing rule (AGENTS.md):** whenever a demo-acceptable production flaw is identified —
by the client or by the build — add a dated entry here *and* say so explicitly in the
end-of-step report. Never silently log it.

---

## Authentication / session

### 2026-10-07 — Single static dev JWT secret, no rotation
- **Issue:** `DEV_JWT_SECRET` is one static per-installation value (`dev_jwt_secret` in
  compose/env); tokens never expire per-env, keys are never rotated, and the secret sits
  in the compose file.
- **Why acceptable:** demo runs air-gapped on one machine with seeded demo users.
- **Production needs:** per-environment secret management (vault/KMS), key rotation with
  overlap, short token lifetimes + refresh, and the real Keycloak issuer instead of the
  dev `DevValidator` (already stubbed behind the validator interface).

### 2026-10-07 — No rate limiting or lockout on `/auth/login`
- **Issue:** login attempts are unlimited; failed attempts are only recorded as audit
  events.
- **Why acceptable:** demo traffic is a handful of scripted logins.
- **Production needs:** per-account/per-source rate limits, backoff or lockout, and
  federation through Keycloak's own brute-force protection.

### 2026-10-07 — No logout or token revocation
- **Issue:** tokens are stateless bearer tokens valid until expiry; there is no logout
  endpoint and no revocation list.
- **Update 2026-10-07:** the demo UI's logout button (Part B) will only drop the token
  in browser storage — the token itself stays valid until expiry. Call this out in the
  step report whenever the UI logout lands; do not present it as server-side logout.
- **Why acceptable:** demo sessions are short-lived page reloads.
- **Production needs:** revocation (denylist or introspection), logout, and session
  management via the real IdP.

## Audit chain / checkpoints

### 2026-10-07 — DB transaction held across git subprocess (up to 10 s)
- **Issue:** the layer-2 git ledger commit runs while the advisory-locked DB transaction
  is open; `subprocess.run(..., timeout=10)` can hold the chain lock for up to 10 s.
- **Why acceptable:** demo write volume is tiny; a slow commit only delays other audit
  writes briefly.
- **Production needs:** emit the git ledger commit outside the DB transaction (append the
  checkpoint line first, commit asynchronously via a queue), or push to an external
  notarisation service instead of local git.

### 2026-10-07 — Tail truncation caught only at next checkpoint
- **Issue:** events between the last checkpoint and the current DB tail (up to
  `audit_checkpoint_interval - 1` = 9 events) have no external attestation; truncating
  them is only detectable when the next checkpoint fires.
- **Why acceptable:** the demo script verifies immediately after generating traffic.
- **Production needs:** checkpoint per event (interval = 1) or streaming hash
  publication to an external witness, plus monitoring of checkpoint age.

### 2026-10-07 — Ledger identity and location are self-asserted and co-hosted
- **Issue:** the git ledger uses local identity `gateway-audit <gateway-audit@localhost>`
  and lives on the same host as the database, so an attacker with root on the host could
  tamper with both the DB and the ledger.
- **Why acceptable:** air-gapped single-host demo.
- **Production needs:** append-only notarisation on separate infrastructure (remote
  HSM-backed signing, WORM storage, or cross-host hash publication), with a real
  identity and monotonic external clock.

### 2026-10-07 — Checkpoint failure logging must be distinguishable
- **Issue:** a blocking checkpoint-file write failure and a non-blocking git-ledger
  commit failure must produce clearly different log lines so operators can tell which
  layer failed.
- **Why acceptable:** n/a — this is implemented in step 7 (`AUDIT CHECKPOINT FILE WRITE
  FAILED — blocking` vs `AUDIT LEDGER GIT COMMIT FAILED — non-blocking`); recorded here
  so the requirement is visible and testable.
- **Production needs:** structured audit-health metrics/alerts on both failure modes.

## Data / schema

### 2026-10-07 — `source_ref` not UNIQUE on documents and canonical_records
- **Issue:** lookup endpoints resolve `GET /documents/{source_ref}` with `.first()`; the
  schema does not enforce uniqueness, so duplicates would silently return one row.
- **Why acceptable:** demo corpus is seeded once with distinct refs.
- **Production needs:** `UNIQUE` constraints on `source_ref` (plus a migration backfill),
  and 409/500 handling if duplicates ever appear.

## API surface

### 2026-10-07 — Checkpoint path is CWD-relative
- **Issue:** default `audit_checkpoint_path = "data/audit_checkpoints.log"` resolves
  against the process working directory; a service started elsewhere writes a different
  file.
- **Why acceptable:** uvicorn runs from the repo/app directory in compose and dev.
- **Production needs:** an absolute path from config/env, owned by the service user.

## Knowledge pathway / retrieval

### 2026-10-07 — Reciprocal rank fusion instead of a reranker
- **Issue:** SPEC §8.1/§8.2 hybrid search ends with reranking
  (`LocalRerankerProvider`); the demo fuses vector similarity and full-text with
  reciprocal rank fusion (RRF, k=60) inside the retrieval SQL and stops there.
- **Why acceptable:** the reranker is a DEMO CUT item; RRF keeps fusion inside the
  same authorization-filtered query and needs no extra model or memory.
- **Production needs:** a local cross-encoder reranker after fusion, scored by the
  retrieval-quality evaluation suite, with the authorization filter still applied
  inside the query (never after it).

### 2026-10-07 — Retrieval silently degrades to full-text only
- **Issue:** if the local embedder is unavailable, `ModelPort.embed_query()` (was `_query_embedding()`) returns
  `None` and ingestion stores NULL embeddings; hybrid retrieval then runs as
  keyword search only, with nothing on the answer or in the logs distinguishing
  it from a full hybrid run. The API tests always take this path (no weights).
- **Why acceptable:** the demo must run without network/model weights, and tests
  must not depend on them.
- **Update 2026-10-07 (Part A):** the answer now carries a code-path `degraded` flag
  (`true` when the query vector or every chunk embedding is missing) and the answer
  audit event stores it, so the UI can label a keyword-only run. The API tests still
  take this path by design.
- **Production needs:** fail closed or label the answer as degraded (the flag is the
  label), require embeddings at ingestion time, and monitor embedder health so a
  missing vector channel raises an alert instead of quietly lowering recall.

### 2026-10-07 — Conversation/message RLS policies do not bind rows to the session user
- **Issue:** the SELECT and INSERT (WITH CHECK) policies on `conversations` and
  `messages` verify markings (data scope, clearance, compartments, unit) but not
  `user_id`; ownership is enforced only by the `user_id = :user_id` predicate the
  assistant endpoint writes into its SQL.
- **Why acceptable:** one endpoint reads turns, always resolves ownership first
  (404 otherwise), and the cross-user 404 is covered by a test.
- **Production needs:** add `user_id = NULLIF(current_setting('app.user_id', true), '')::uuid`
  to both policies so any future query path inherits row ownership in the database,
  not only in application SQL.

### 2026-10-07 — Conversation history ties on `created_at` within a turn
- **Issue:** the user and assistant messages of one turn are inserted in a single
  statement, so they share `now()`; `_load_history` orders by
  `created_at DESC, id DESC` and the UUID tie-break is random — a turn's pair can
  reach the model in reverse order.
- **Why acceptable:** histories are ≤ 6 turns and the demo script does not probe
  multi-turn ordering.
- **Production needs:** a monotonic per-message sequence column (or a two-column
  sort that cannot tie) so history order is deterministic.

### 2026-10-07 — Hosted dev model name deviates from the approved name
- **Issue:** `llm_model` is configured as `gemini-3.5-flash`, which is not the
  model name originally approved for the demo; the spec leaves model choice to
  configuration (§8.1) but the change was not re-approved through that route.
- **Why acceptable:** recorded here rather than silently accepted; every answer
  event already stores provider and model, so answers are traceable to the model
  that produced them.
- **Production needs:** pin an approved model and version per environment, re-approve
  before any non-demo use, and keep model+version on the answer record (already done)
  for provenance.

## AI gateway / data

### 2026-10-07 — Hosted LLM (Gemini) in dev profile
- **Issue:** `HostedProvider` sends prompts to an external model API.
- **Why acceptable:** explicitly scoped to the demo dev profile; spec-compliant on-prem
  `LocalVLLMProvider` is stubbed behind `LLMProvider` (see docs/STUBS.md).
- **Production needs:** on-prem/in-profile inference, zero-retention terms, and no client
  material reaching a third-party model.

### 2026-10-07 — OPA stubbed as a Python policy function
- **Issue:** `Policy` is implemented as a Python function, not an OPA/Rego decision
  service.
- **Why acceptable:** demo CUT item; the interface keeps the swap-in point honest.
- **Production needs:** OPA sidecar/SDK evaluation with the same `decide()` contract and
  policy-as-code tests.

### 2026-10-07 — Pre-canned response cache can mask provider failure
- **Issue:** when the hosted LLM fails after retries, `AIGateway` falls back to a
  pre-recorded answer from `data/demo_llm_cache.json` (keyed by the full request shape:
  model, messages, temperature, max_output_tokens). A stale canned answer can therefore
  be shown instead of a hard failure.
- **Why acceptable:** keeps the demo script runnable offline and on free-tier quota;
  the result is flagged (`cached=True`, notice string) for provenance display.
- **Production needs:** fail closed — surface the provider error; if a degraded mode is
  required, label it explicitly in the UI and exclude cached answers from any
  operational or evidentiary output.

### 2026-10-07 — Committed canned-answer file
- **Issue:** `data/demo_llm_cache.json` (prompt→answer pairs for the demo script) is
  committed to the repository as plaintext.
- **Why acceptable:** answers are synthetic demo data about synthetic records.
- **Production needs:** no committed response corpus at all; if caching is kept, store
  entries server-side with retention limits and access control.

### 2026-10-07 — Hosted API key via environment/compose, no vault or rotation
- **Issue:** the Gemini key is a plaintext env var (`HOSTED_API_KEY`/`GEMINI_API_KEY`)
  passed through compose; no secret manager, no rotation, no redaction beyond not
  logging it.
- **Update 2026-10-07:** a `GEMINI_API_KEY` value was exposed in a debug transcript
  during the demo build. **The owner must rotate it** — logged here so the rotation
  is tracked and not assumed done.
- **Update 2026-10-07 (later):** rotation done — the exposed key was revoked and
  replaced with a new key in `.env` (gitignored, never committed); a live
  `scripts/smoke_ai_gateway.py` call with the new key returned OK. The rotation
  incident note stays visible here rather than being deleted.
- **Why acceptable:** single demo machine, free-tier key, air-gapped demo narrative.
- **Production needs:** vault/KMS-backed secrets with short-lived scoped credentials,
  rotation, and egress controls.

### 2026-10-07 — Synchronous non-streaming completion (25 s cap)
- **Issue:** `AIGateway.complete()` is a blocking request/response; there is no
  streaming of tokens (`HostedProvider` does not implement the spec's streaming path).
- **Why acceptable:** demo answers are short; SPEC's 25 s sync-response ceiling is
  respected via `hosted_timeout_seconds`.
- **Update 2026-10-07:** a live call after the key rotation returned OK in
  **~204 s** end-to-end (provider-reported), so `hosted_timeout_seconds: 25` did not
  bound wall-clock time — httpx's connect/read timeouts bound individual wait
  periods, not the whole call, and a slow provider can sit well inside them. Treat
  the 25 s ceiling as *not* guaranteed: the demo script should stay on the response
  cache, and the API must not present a slow answer as timely.
- **Production needs:** server-sent streaming end to end, with cancellation and
  per-token accounting; an overall deadline on the sync path if streaming is
  deferred.

### 2026-10-07 — Embedding weights downloaded from HuggingFace, not an air-gapped build
- **Issue:** the BGE-M3 int8 ONNX weights are fetched from the HuggingFace Hub on the
  dev machine and copied into the image at build (`COPY data/models`); the build is not
  air-gapped and the upstream source is not mirrored or verified by signature.
- **Why acceptable:** DEMO CUT removes the air-gapped profile for now; weights are
  gitignored and baked once. **Correction 2026-10-07:** they are *not* guaranteed to be
  absent at runtime on a fresh dev machine: the first `scripts/ingest_documents.py` run
  downloads them into `data/models` (observed ~2 min). Pre-stage the weights before any
  run on a network-restricted host.
- **Production needs:** internally mirrored model registry, checksum/signature
  verification at build, and a build pipeline that makes no external calls.

### 2026-10-07 — Live hosted API dependency and free-tier quota
- **Issue:** every uncached LLM call leaves the machine for the Gemini API; availability
  and rate limits are Google's, and the free tier has RPM/RPD quotas.
- **Why acceptable:** development/demo profile only; retries and the response cache
  absorb transient failures during the scripted demo.
- **Production needs:** on-prem inference (the stubbed `LocalVLLMProvider`), or a
  contracted zero-retention endpoint with SLAs, quota monitoring and backpressure.

### 2026-10-07 — Keyword router selects the data tool (SPEC: the model selects it)
- **Issue:** SPEC 8.2 has the model choose a typed tool. The demo uses a deterministic
  keyword router (`data_queries/routing.py`): record-style requests ("show me / list /
  which" + equipment maintenance or expired certifications) go to a tool; anything that
  mentions a document, policy, directive, SOP or manual always goes to the knowledge
  pathway. Free-form phrasings that are not in the keyword set fall through to the
  knowledge pathway and answer "not found"; unit scope is passed only as a literal path
  token (no unit-name resolution such as "Brigade 2").
- **Why acceptable:** predictable demo behaviour, no model in the routing decision, and
  authorization does not depend on routing (tools authorize via the adapter either way).
- **Production needs:** model-driven tool selection over the same registry with schema
  validation of the model's arguments, unit-name resolution, and an evaluation set
  (SPEC 16) for routing accuracy.

### 2026-10-07 — Relative seed dates and one demo adapter
- **Issue:** the maintenance/certification demo rows store dates as offsets from the day
  the corpus is seeded (so "overdue" and "due in 15 days" stay true), and one
  `DemoReferenceAdapter` serves both logistics and personnel entities from the gateway's
  own `canonical_records`. Rows seeded on another day shift with it; a stale dev database
  must be re-seeded.
- **Why acceptable:** demo data only; the adapter contract is the real one.
- **Production needs:** per-system adapters reading the client's systems; no seeded dates.

### 2026-10-07 — Pre-existing: manipulation detection is a keyword regex
- **Issue:** the SPEC 8.3 manipulation detector is a regex. Task 2 widened it to match
  "ignore my permissions" (the SPEC 15 example and a demo question, previously
  undetected, so no `notable` event was written). It remains evadable by paraphrase.
  Access never depends on it: authorization decides before the model.
- **Production needs:** a classifier-based detector plus an adversarial evaluation set
  (SPEC 16).

## Web UI

### 2026-10-07 — JWT held in sessionStorage; logout is client-only
- **Issue:** the UI keeps the bearer token in React state and `sessionStorage`, readable by
  any script that runs in the page. Logout only clears it in the browser; the token stays
  valid until expiry (see "No logout or token revocation").
- **Why acceptable:** demo data only, no third-party scripts (air-gap scan), short sessions.
- **Production needs:** Keycloak OIDC with HttpOnly, SameSite cookies or a BFF session,
  server-side revocation, and a strict Content-Security-Policy.

### 2026-10-07 — Web container runs the Next.js dev server
- **Issue:** the compose `web` service runs `npm ci && npm run dev` against the mounted
  source (hot reload, unminified, installs on every start); `npm audit` reports advisories
  in dev dependencies.
- **Why acceptable:** local demo only, on a developer machine.
- **Production needs:** a multi-stage image with `next build`, pinned lockfile install,
  non-root user, dependency audit in CI, and a reverse proxy in front.

### 2026-10-07 — Demo cache record and cache-only modes
- **Issue:** `LLM_CACHE_RECORD=1` makes the gateway persist every live model result
  (the exact prompt, including the user's authorized evidence, and the answer) to the
  plaintext `data/demo_llm_cache.json`; `LLM_CACHE_ONLY=1` serves answers from that file
  without calling any model. Keys are exact-prompt hashes, so any change to prompts,
  corpus, chunking, retrieval, tools or seed dates silently turns replays into 503
  misses until the prefill is re-run. Record mode is refused unless `APP_PROFILE=dev`.
  The prefill also leaves its queries, conversations and audit events in the dev
  database, so they show up in the demo audit trail.
- **Why acceptable:** demo only; the data and the answers are synthetic, and the
  cached evidence is only what each demo user was already cleared to see.
- **Production needs:** neither mode exists in a production profile; no stored prompt
  corpus, no replay of model output, and a real on-prem model behind `LLMProvider`.

### 2026-10-08 — Correlation: one rule-based analysis, run by hand
- **Issue:** the correlation job is a single hard-coded rule (`rising_faults`: fault count
  doubling over two 21-day windows, plus lapsed maintainer certifications and stock below
  threshold in the same unit), run on demand by a commander; it is not scheduled, has no
  tuning, no false-positive review and no history of earlier runs (a rerun updates the
  finding in place). The dashboard certification tile reports expired, not expiring, certs.
- **Why acceptable:** the demo needs one reproducible planted pattern with provenance; the
  summary is deterministic text from the numbers, so no model can embellish or leak it.
- **Production needs:** scheduled worker (Procrastinate), a library of analyses with
  thresholds under change control, finding lifecycle (acknowledge, dismiss, history), and
  the findings table's UPDATE grant narrowed to the worker role.

### 2026-10-07 — Dashboard placeholders and a second copy of the visibility rule
- **Issue:** the readiness dashboard tile is a hard-coded fixture, not
  module data, and they are authorized by `LocalPolicy.item_visible`, a Python re-statement of the SQL row filter
  (two implementations of SPEC 7.1 that can drift).
- **Why acceptable:** the fixtures are fictitious and tagged PLACEHOLDER DATA in the UI;
  `tests/authz/test_item_visible.py` checks the Python rule against the SQL oracle for
  every seeded record and demo user. Part D replaces the tiles with real tool results,
  which use the SQL filter only.
- **Production needs:** one policy decision point (OPA partial evaluation) for every
  surface, and no fixture data in the dashboard.

### 2026-10-07 — DEMO_DATE pins the business date
- **Issue:** `DEMO_DATE` (dev profile only, refused otherwise) replaces the live date in
  the seed offsets and in the data-tool cutoffs, so "overdue" and "due within 30 days"
  are evaluated against a fixed day. With it set, the demo reports a stale date as
  today; audit, token and `created_at` times stay real.
- **Why acceptable:** it keeps recorded model answers valid for the scripted demo; it is
  off by default and cannot be enabled outside the dev profile.
- **Production needs:** no date override at all; tools evaluate against the live clock.

### 2026-10-07 — Connected-technology demo data is hand-seeded, windowed in Python
- **Issue:** surveillance, UAS and forensics records (REC-046..062) are a small hand-written
  set in `app/seed.py`, not output of a generator, and are served by the same
  `DemoReferenceAdapter` as logistics data. A mission's track is a short coordinate list
  inside the mission record (no `TrackPoint` rows). `uas_missions`, `detections_near_site`
  and `/connected/map` fetch every authorized row of the entity type and apply the time
  window in Python. Detection times are offsets from `demo_now()` (noon on the demo date,
  pinned by `DEMO_DATE`), so "last 48 hours" is relative to that fixed instant.
- **Why acceptable:** tens of rows, all authorized by the row filter + RLS before the
  window is applied; the pinned instant keeps recorded model answers valid.
- **Production needs:** real per-system adapters pushing windows (time, area, sensor) into
  the source query or an indexed store, `TrackPoint`/telemetry storage, and live `stream()`.
