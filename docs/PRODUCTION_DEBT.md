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
- **Why acceptable:** single demo machine, free-tier key, air-gapped demo narrative.
- **Production needs:** vault/KMS-backed secrets with short-lived scoped credentials,
  rotation, and egress controls.

### 2026-10-07 — Synchronous non-streaming completion (25 s cap)
- **Issue:** `AIGateway.complete()` is a blocking request/response; there is no
  streaming of tokens (`HostedProvider` does not implement the spec's streaming path).
- **Why acceptable:** demo answers are short; SPEC's 25 s sync-response ceiling is
  respected via `hosted_timeout_seconds`.
- **Production needs:** server-sent streaming end to end, with cancellation and
  per-token accounting.

### 2026-10-07 — Embedding weights downloaded from HuggingFace, not an air-gapped build
- **Issue:** the BGE-M3 int8 ONNX weights are fetched from the HuggingFace Hub on the
  dev machine and copied into the image at build (`COPY data/models`); the build is not
  air-gapped and the upstream source is not mirrored or verified by signature.
- **Why acceptable:** DEMO CUT removes the air-gapped profile for now; weights are
  gitignored, baked once, and never fetched at runtime.
- **Production needs:** internally mirrored model registry, checksum/signature
  verification at build, and a build pipeline that makes no external calls.

### 2026-10-07 — Live hosted API dependency and free-tier quota
- **Issue:** every uncached LLM call leaves the machine for the Gemini API; availability
  and rate limits are Google's, and the free tier has RPM/RPD quotas.
- **Why acceptable:** development/demo profile only; retries and the response cache
  absorb transient failures during the scripted demo.
- **Production needs:** on-prem inference (the stubbed `LocalVLLMProvider`), or a
  contracted zero-retention endpoint with SLAs, quota monitoring and backpressure.
