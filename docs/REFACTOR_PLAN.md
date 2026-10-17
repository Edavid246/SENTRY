# Refactor plan

Status: **approved 2026-10-16, in progress.** Progress is ticked in section 10.
Written 2026-10-16 against commit `860b101` (main, clean tree).

**Decisions (2026-10-16):** the plan is approved as a whole. D1-D9 are all yes and slot in where
section 6 says. D10: delete dead code, with the git restore note. D11: leave the division page's
home call as it is. D12: this file lives at `docs/REFACTOR_PLAN.md` (it started as `refactor.md`).

This plan comes from reading every tracked source file: the backend (`backend/app`, 92 files),
the migrations, the 43 test modules and their helpers, the web app (`web/src`, 33 files), the
scripts, the smoke tests, the infra files and the docs. Each finding below names the file and
line, and each was checked against the code, not inferred from a file name.

## What this refactor is, and what it is not

It **is** a clean-up of structure: code moved to where it belongs, duplicates folded into one
place, dead code removed, types made explicit, tests and docs brought back in line with the code.

It is **not** a feature change. After each step the API returns the same JSON, writes the same
audit events, sends the model the same prompts and shows the same screens. The few places where
I found real bugs or gaps are listed separately in section 4. They are **not** part of the
refactor unless you say yes to them one by one.

---

## 1. Rules every step follows

1. **Invariants (AGENTS.md) are not touched.** Authorization before retrieval, filter inside
   the query plus RLS, 404 not 403, derived labels, hash-chained audit on every read, read-only
   adapters, typed tools, no external resources, demo data labelled, no `.env` access. Where a
   finding touches an invariant it is in section 4.1, and I stop and ask.
2. **No behaviour change.** Same routes, status codes, response fields, audit payloads and
   `data-testid` attributes (the web smoke tests select on 57 distinct test ids).
3. **LLM cache keys do not move.** A cache key is the hash of the exact model request. So no
   step may change: system prompt text, evidence formatting, the explain or report prompt, chunk
   ids, seed rows or their order, seed dates, or the order of tool rows. Step 0.1 adds a test that
   fails if any of these change by a single byte.
4. **Existing migrations are history.** They are never edited. Schema changes, if any, get new
   migrations (none are planned).
5. **One step, one commit.** `./scripts/check.sh` green after every step (stop the web dev
   server first: `next build` clobbers `web/.next`). Web steps also run the UI smoke test.
   Then push and stop for your go-ahead, as usual.
6. **Layout changes get a dated line in `docs/DECISIONS.md`** (AGENTS.md: file layout is a
   default, deviations are logged).
7. **Removed code stays restorable.** Everything deleted is in git at `860b101`; each removal
   commit names the files, and `git show 860b101:<path>` brings any of them back. (You asked for
   "archive, don't delete" for product features. For dead code I suggest plain deletion with this
   restore note; see decision D10.)
8. Files on disk are CRLF; edits go through the Edit tool, not shell rewrites.

---

## 2. Baseline (measured 2026-10-16)

| Check | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 162 files already formatted |
| `pytest -q` | 620 passed, 5 skipped, in 6 min 41 s. One warning: Starlette deprecates `httpx` inside its `TestClient` (third-party; out of scope) |
| web `lint`, `typecheck`, `build` | Not re-run here (it would break a running dev server). Last recorded green at `860b101`. |
| UI smoke (`web/smoke/smoke.mjs`) | Not re-run here (needs the stub API and a fresh `--include-archived` seed). Last recorded 71 ok. |

Size of what is in scope (tracked lines, approximate):

| Area | Files | Lines |
|---|---|---|
| Backend app | 92 | ~9,600 |
| Migrations | 5 | ~530 |
| Tests (43 test modules plus fixtures and helpers) | 48 | ~7,000 |
| Web source (excluding the generated `api-types.ts`) | 33 | ~3,800 |
| Scripts and smoke | 10 | ~1,300 |

Step 0 re-measures pytest and runs the full `check.sh` and smoke test before anything moves.

---

## 3. How the code is organised today

The request path is sound and the seams mostly hold. In short:

- `app/api/*` are the FastAPI routers. Each route opens `guarded(...)` (`app/api/guard.py`),
  which runs `authorize` then `open_scope` (`app/authz/scope.py`): policy decision first, RLS
  context set once, every read recorded, the audit batch written when the block closes, writes
  committed only after their audit record exists.
- Data comes only through `get_adapter()` (`app/connectors`), with the policy row filter inside
  the SQL and RLS underneath. Typed tools (`app/data_queries/tools/*`) sit on the adapter and are
  run by `execute_tool` (`app/data_queries/registry.py`), which writes one `data_query` event each.
- The assistant (`app/assistant/service.py`) picks a pathway (knowledge, data, report), runs it
  on the scope, labels the turn with `Labels.derive` (`app/authz/labels.py`), stores it, audits.
- Models are reached only through `ModelPort` (`app/ai_gateway/port.py`) and the gateway.
- Division pages, the home summary, case pages and reports are built from the same typed tools.
- The web app (`web/src`) is Next.js client pages over a small `api` object in `web/src/lib/api.ts`.

The problems are mostly about *where* things live and *how many copies* exist, plus a short list
of stale code and docs. Two seams are weaker than the docs say (section 4.1).

---

## 4. Findings that need your decision (not refactoring)

These came up during the read. Each one changes behaviour, an interface, or an invariant, so I
have kept them out of the refactor. Tick the ones you want and I will slot them in where marked.

### 4.1 Invariant and seam findings (AGENTS.md says: stop and ask)

| ID | Finding | Where | Proposed fix | Effect |
|---|---|---|---|---|
| D1 | One read has RLS but **no policy row filter in the SQL**. `open_conversation` checks the conversation id and owner with RLS alone. Every other read puts `scope.filter(...)` in the query. The comment at line 168 says it was found "under the same filter + RLS", which is not true. | `backend/app/assistant/conversations.py:102-112`, comment `:168` | Add `scope.filter("conversation")` to that query. | Tightening only. Same answers, because the filter and RLS encode the same rule. |
| D2 | The **`TokenValidator` seam does not exist** as an interface. AGENTS.md and docs/STUBS.md name it as a seam, but the code builds `DevTokenValidator()` directly in two places. There is no protocol and no single wiring point like `get_policy()`. | `backend/app/api/deps.py:69`, `backend/app/api/endpoints.py:72`, `backend/app/authz/tokens.py:45` | Add a `TokenValidator` protocol and `get_token_validator()` in `authz/tokens.py`; `deps.py` uses it. The dev login keeps issuing dev tokens explicitly (Keycloak replaces login entirely). | No runtime change. Makes the documented seam real. |
| D3 | **Per-tool policy decisions only happen on the assistant path.** `tool_requirements()` says a tool needs `("query","record")` (or `("read","finding")` for findings). The assistant decides these before running a tool. The home, division, trace, case, report and correlation routes decide only `("read","dashboard")` or `("run_correlation","finding")`, then run the same tools. No current role is exposed: every role with `read` also has `query`. But a future role with `read` and no `query` would get tool rows on the dashboards. | `backend/app/data_queries/registry.py:24-36`; routes `api/home.py:113`, `api/divisions.py:180,206`, `api/cases.py:67`, `api/reports.py:91`, `api/correlation.py:69` | Either (a) dashboard routes also authorize the requirements of the tools they run, or (b) `execute_tool` refuses to run a tool whose requirements the scope did not decide. I recommend (b): one rule, in one place. | Adds decide events to those routes' audit batches. Not in docs/PRODUCTION_DEBT.md today. |
| D4 | **A second copy of the visibility rule is still there with nothing using it.** `Policy.item_visible` restates the SPEC 7.1 rule in Python for the fixture tiles. The fixtures were deleted on 2026-10-09. Only its own test calls it now, and docs/PRODUCTION_DEBT.md still describes it as live. | `backend/app/authz/policy.py:54-61, 110-128`; `tests/authz/test_item_visible.py` | Remove it from the protocol, the class and the tests; update the debt entry. | Smaller policy seam (OPA would no longer need to implement it). |

### 4.2 Bugs and gaps found along the way

| ID | Finding | Where | Proposed fix |
|---|---|---|---|
| D5 | **A chat starter misses the recorded answer.** The starter reads "…training activity for *this group* over the last quarter." The scripted question is "…for *this command*…". A different question is a different cache key, so in an offline demo this button shows the "recorded answers" panel instead of the report. | `web/src/app/chat/page.tsx:49` vs `data/demo_questions.json` (`reporting-training-summary`) and `web/smoke/smoke.mjs:18` | Use the scripted wording. UI text only; no cache key changes. |
| D6 | **Two different markings for the same level.** The training draft prints the internal code (`Classification: SECRET`). Division reports and the whole UI print the display name (`GOVERNMENT-SENSITIVE`). | `backend/app/reporting/training.py:73-75` vs `backend/app/reporting/division.py:95` | Use `Labels.display` in the training draft too. The text is added after the model call, so no cache keys move; the visible marking changes. |
| D7 | **The answer audit event leaves out model fields that SPEC 8.1 and 14.1 ask for.** It records provider, model and `cached`, but not `model_version`, token counts or latency. `LLMResult` already carries all three. | `backend/app/assistant/service.py:158-162` | Add the three fields to `_model_use`. Additive audit change. |
| D8 | **Multi-turn history can reach the model in the wrong order.** This is already in the debt log. The fix is already in the codebase: `list_messages` breaks ties by role, but `load_history` does not. | `backend/app/assistant/conversations.py:138` vs `:95` | Use the same tie-break in `load_history`. This can change follow-up prompts, and so their cache keys. Low priority. |
| D9 | Smaller ones, all cheap: **(a)** the division page swallows a failed division fetch and shows a header with no sections and no error (`web/src/app/d/[division]/page.tsx:22`); **(b)** `DemoReferenceAdapter.describe()` lists 15 entity types but the seed also holds `WorkOrder` and `Flight` (REC-003, 004, 008) (`backend/app/connectors/demo.py:26-42`); **(c)** the default `DEV_JWT_SECRET` in `.env.example:22` and `infra/compose.yaml:49` is 25 bytes, while `config.py:49-51` says it must be at least 32 and uses a 42-byte default; **(d)** `load_manifest` reads JSON without `encoding="utf-8"` (Windows default codepage) (`backend/app/knowledge/ingest.py:39`). | as listed | Fix each in place. |

### 4.3 Preferences I need from you

- **D10.** Dead code (section 5.E): delete it, with the git restore note? (Recommended.) Or move
  it to an `archive/` folder?
- **D11.** The division page calls `/home/summary` on every visit, just for the tab strip and its
  own name, tagline and alert. That re-runs all six attention tools and the findings read, each
  audited. Leave it as it is (behaviour-preserving)? Or add the alert and a division list to
  `DivisionView` (an API change)? I recommend leaving it for now.
- **D12.** Plan file location (answered: moved to `docs/REFACTOR_PLAN.md`). It started as `refactor.md` at the repo root. The other
  plans live in `docs/` (`PIVOT_PLAN.md`, `GROUP_HOME_PLAN.md`). Shall I move it to
  `docs/REFACTOR_PLAN.md` once approved?

---

## 5. What the refactor fixes

Grouped by kind. The step that handles each one is in brackets; the steps are in section 6.

### 5.A Code that lives in the wrong place

| ID | Finding | Where | Fix [step] |
|---|---|---|---|
| A1 | The **division catalogue and the dashboard builder are domain logic inside route modules**. `DIVISIONS`, `FIELD_OPS` and `_division_key` live in `api/home.py`. `build_division`, `_division` and `_field_ops_facts` live in `api/divisions.py`. As a result `api/divisions.py` imports `api/home.py`, and `api/reports.py` imports `api/divisions.py`: route modules importing each other. | `backend/app/api/home.py:60-108`, `api/divisions.py:72-175`, `api/reports.py:21`, `api/division_specs.py` | New package `app/divisions/`: `catalog.py` (the five divisions, which records count toward which), `specs.py` (today's `division_specs.py`), `view.py` (`build_division` and its models), `attention.py` (the home card counting). The routes keep only HTTP. [3.1] |
| A2 | **Unit-path parsing is re-implemented** outside `app/units.py`, whose docstring says "every module reads that shape here". `_division_key` splits paths by hand. `_field_ops_facts` uses `p.split("/")[2]`. `_reach` is local to divisions. Meanwhile `units.is_subsidiary` and `units.subsidiary_path` are unused. | `api/home.py:98-108`, `api/divisions.py:116-117, 145`, `app/units.py:30-43` | One unit vocabulary in `app/units.py` (subsidiary key, site test, "covers" test), used everywhere; delete what stays unused. [2.2] |
| A3 | **Conversation and message ORM models live in `knowledge/models.py`**, but they belong to the assistant. A third type, `conversations.Message` (a dataclass), shares its name with the ORM `Message`. | `backend/app/knowledge/models.py:56-92`, `assistant/conversations.py:42-46` | Move them to `app/assistant/models.py` (alembic `env.py` and the seed loader import from there). Rename the dataclass to `StoredMessage`. No schema change. [3.3] |
| A4 | **`utc_now_iso` is a clock helper living in the audit chain.** Five route modules import it from `app.audit.chain` just to stamp `generated_at`. | `backend/app/audit/chain.py:59`; importers `api/cases.py:19`, `connected.py:19`, `divisions.py:24`, `home.py:27`, `reports.py:23` | Move it to `app/clock.py`; the audit chain imports it from there. [2.4] |
| A5 | **The report marking is defined twice, and the shared banner sits in a sibling feature.** `reporting/division.py` imports `DRAFT_BANNER` from `reporting/training.py`. The marking text is built in `division.marking()` and again by hand in `training._assemble()`. | `backend/app/reporting/division.py:18, 58-60`, `reporting/training.py:33, 73-75` | `app/reporting/marking.py` holds the banner and `marking()`; both reports use it. (If you approve D6, the training draft also switches to display names here.) [2.6] |
| A6 | **`api/endpoints.py` mixes five concerns**: login, `/me`, documents and passages, records, and the audit viewer. | `backend/app/api/endpoints.py` (219 lines) | Split into `api/auth.py`, `api/documents.py`, `api/records.py`, `api/audit.py`. Same paths, same function names, so the OpenAPI operation ids stay the same. [3.2] |
| A7 | **`correlation/analysis.py` is really the rising-faults analysis.** Its siblings are named after what they do (`custody.py`, `qc_delivery.py`). | `backend/app/correlation/analysis.py` | Rename it to `rising_faults.py`. [2.5] |
| A8 | **The only relative imports in the backend**: `from .division_specs` and `from .home`. | `backend/app/api/divisions.py:31-32` | Absolute imports (this goes away with A1). [3.1] |
| A9 | **Test helpers live inside test modules, and other tests import them by private name.** There are about 50 imports like `from test_assistant_endpoints import _ask, _audit, _latest`. `test_auth_endpoints.auth_header` is used by 14 modules, and `test_rls_only.CONTEXTS` is shared data. Only `tests/authz` is on the configured `pythonpath`; the other imports work because of pytest's rootdir insertion. | e.g. `tests/api/test_data_pathway.py:28-31`, `tests/api/test_contracts.py:15-17`, `tests/authz/test_decide.py:13-14`; `pyproject.toml:47` | A `tests/support/` package: `http.py` (login, auth header, ask, get), `audit.py` (audit events, latest match, watermark), `contexts.py` (the hand-written user contexts and `ctx_for`), `fakes.py`. Explicit `pythonpath`. [0.2] |

### 5.B Duplication

| ID | Finding | Where | Fix [step] |
|---|---|---|---|
| B1 | **Three throwaway classes exist only to satisfy `Labelled`**: `home._Member`, `reports._Part` and `conversations._Stored`, plus the derive tests' `Item`. They exist because `Label` has a `code` field while `Labelled` asks for `classification_code`. | `api/home.py:89-95`, `api/reports.py:70-75`, `assistant/conversations.py:153-156` | Give `Label` a `classification_code` property so a `Label` can be an input to `derive`; delete the three classes. [2.1] |
| B2 | **The label scheme is reloaded several times per request.** `Labels.load(conn)` runs on every `_Turn.label` call, again in `_raise_conversation_label`, and twice on the trace route. | `assistant/service.py:114`, `assistant/conversations.py:169`, `api/divisions.py:170, 213`, `api/home.py:114`, `api/cases.py:106`, `api/correlation.py:71` | `Scope.labels`, loaded once per scope. [2.1] |
| B3 | **Identifier formats are written in several places.** Case ref: three regexes. Evidence ref: two. Serial: two. Depot: two, and they differ (the router accepts more). Site: two. `REC-` ids: two. Contract statuses: two. | `api/cases.py:25`; `tools/forensics.py:14-15`; `tools/production.py:14`; `tools/compliance.py:27`; `tools/uas.py:31`; `tools/commercial.py:23`; `reporting/training.py:39`; `data_queries/routing.py:38, 60, 67, 69, 80, 81` | `app/data_queries/formats.py` holds each pattern once. Tools compile it anchored, the router unanchored and case-insensitive, exactly as today; the routing tests pin the behaviour. [2.3] |
| B4 | **`RetrievedChunk` and `Passage` carry the same nine fields.** `api/assistant.py` defines a `_Cited` protocol only so one function can accept both. | `knowledge/retrieve.py:31-52`, `knowledge/passages.py:34-46`, `api/assistant.py:145-162` | `RetrievedChunk` extends `Passage` with the three score fields; `_Cited` goes. Evidence text stays byte-identical (guarded by 0.1). [2.4] |
| B5 | **Two copies each of the vector literal format and the "embed or degrade to keyword search" wrapper.** | `knowledge/retrieve.py:55-56` and `knowledge/ingest.py:158`; `ai_gateway/port.py:33-39` and `knowledge/ingest.py:45-60` | One `vector_literal()` and one `embed_or_none()` beside the embedder. [2.4] |
| B6 | **The three correlation analyses repeat the finding boilerplate** (derive label, sort evidence ids, `as_of`, severity, tools list), and `FindingRow` repeats all ten fields of `FindingDraft`. | `correlation/analysis.py:73-107`, `custody.py:52-83`, `qc_delivery.py:55-107`; `correlation/types.py:9-20` vs `correlation/store.py:16-28` | A `draft_finding(...)` helper in `correlation/types.py`; `FindingRow` composed from `FindingDraft` plus `created_at`. Keys, text and details stay identical (the correlation tests pin them). [2.5] |
| B7 | **Test helper copies**: `_get` (5 modules), `_audit`/`_latest` (2), `_ctx` (2) plus three more hand-built context helpers, `_ids` (3), `_refs` (4), `_tip` (2), `_sections` (2), `Capture` (2). | `tests/api/*`, `tests/authz/*`, `tests/knowledge/test_retrieve.py` | Into `tests/support/` with A9. [0.2] |
| B8 | **Three fake models parse the same prompt markers** ("QUERY RESULT", "TRAINING TABLE", "BEGIN EVIDENCE CHUNK"), each with its own string-splitting. If a marker changes, all three break separately. | `tests/api/fakes.py`, `web/smoke/stub_api.py`, `tests/api/test_reporting.py:22` | The markers become named constants in the app modules that write them; one shared fake in `tests/support/fakes.py`, also used by the smoke stub. [5.1] |
| B9 | **The prefill script re-declares the demo password and the account list.** Its `DEFAULT_USERS` includes `coo`, which the `ACTIVE_USERS` filter then always drops, so `--users` cannot add anyone. `smoke_ai_gateway.OfflineProvider` duplicates the gateway's `_DisabledProvider`. | `scripts/prefill_cache.py:35-38, 249`; `scripts/smoke_ai_gateway.py:45-49` vs `ai_gateway/gateway.py:139-150` | Read users and the password from `app.seed.identity`; reuse the gateway's disabled provider. [5.1] |
| B10 | **Web: four value formatters doing the same job** (`show` twice, `cell`, `str`). | `web/src/app/records/[ref]/page.tsx:11`, `findings/[id]/page.tsx:12`, `components/ResultTableView.tsx:4`, `app/audit/page.tsx:12` | One `displayValue()` in `lib/format.ts`. [4.1] |
| B11 | **Web: the marking chips (badge plus compartment tags) are written out 10 times.** | home, d, cases, reports, findings ×2, records, map, chat draft banner, `PassagePanel`, `DivisionSections` | A `<Marking code compartments />` component. [4.2] |
| B12 | **Web: every detail page repeats the same scaffolding**: wait for `me`, fetch, track loading/missing/failed, render "Not found". Plus the same page wrapper markup. The brand lockup is also written three times. | `cases/[ref]`, `reports/[division]`, `records/[ref]`, `findings/[id]`, `d/[division]`; `Shell.tsx:62-66`, `app/page.tsx:88-92, 112-116` | A `useLoad()` hook, a `<NotFound>` and a `<Page>` wrapper; a `<Brand>` component. [4.3] |
| B13 | **Web: colours are hard-coded beside the Tailwind palette.** 7 hex values on 6 lines of `globals.css`, 4 in the map page, 1 on the login page, 1 in `clearance.ts`. | `web/src/app/globals.css:12-49`, `app/map/page.tsx:15-17, 160`, `app/page.tsx:25`, `lib/clearance.ts:11` | `lib/palette.ts` imported by `tailwind.config.ts` and the map; CSS uses `theme()`. Same colours exactly. [4.4] |
| B14 | **Lists kept in step by hand across languages**: the 37 states (`web/src/lib/states.ts` vs `backend/app/geo/states.py`), and the level display names (`web/src/lib/clearance.ts` vs the seeded `classification_levels.name`). | as listed | Keep both copies, add a test that fails when they differ. No runtime change. [5.2] |

### 5.C Typing and contracts

| ID | Finding | Where | Fix [step] |
|---|---|---|---|
| C1 | **Ten routes return untyped dicts**, so the web hand-writes their types and has to be "kept in step with endpoints.py": login, `/me`, documents list and detail, passage, records list, audit list and verify, map and replay. | `backend/app/api/endpoints.py`, `api/connected.py`; `web/src/lib/api.ts:20-110` | Pydantic response models with exactly today's fields; regenerate `api-types.ts`; the web uses the generated types. One trap: FastAPI writes `null` for unset optional fields, so the GeoJSON `properties` stay a free-form object (or use `exclude_none`). Otherwise extra keys would appear. Guarded by the OpenAPI snapshot from 0.1. [3.5] |
| C2 | **A helper uses FastAPI dependency aliases as plain type hints** (`CurrentContext`, `ConnDep`). | `backend/app/api/reports.py:90` | Use `AccessContext` and `Connection`. [3.1] |
| C3 | **Query parameter style is mixed**: two routes use `= Query(...)` defaults, the rest use `Annotated`. | `api/divisions.py:203`, `api/reports.py:137` | `Annotated` throughout. [3.1] |
| C4 | **Web: the division page hard-codes per-division extras**: the serial lookup for Poctova, the map link for Briech, the Field Operations link for Stratoc, the findings lead card. The backend promises "add its entry to SECTIONS, nothing else changes". | `web/src/app/d/[division]/page.tsx:129-173` | One web-side `DIVISION_EXTRAS` map keyed by division (no API change). [4.5] |
| C5 | **Web: record links are built inconsistently**: some `encodeURIComponent` the ref, four do not. `ResultTableView` decides findings vs records by sniffing the `FND-` prefix. | `cases/[ref]/page.tsx:22, 43, 142`, `reports/[division]/page.tsx:154`, `components/ResultTableView.tsx:31` | One `recordHref(ref)` helper. [4.1] |

### 5.D Files that do too much (web)

| ID | Finding | Where | Fix [step] |
|---|---|---|---|
| W1 | The map page (353 lines) holds the data load, the replay engine, the MapLibre lifecycle and the sidebar. | `web/src/app/map/page.tsx` | A `useReplay` hook, a `MapCanvas` component, a sidebar component. Same `data-testid`s. [4.6] |
| W2 | The chat page (441 lines) holds the thread, the conversation list, the composer and the request logic. | `web/src/app/chat/page.tsx` | `ChatThread`, `ConversationList` and `Composer` components; the page keeps the state. [4.6] |

### 5.E Dead code and stale config

| ID | What | Where | [step] |
|---|---|---|---|
| E1 | `Sparkline` component, unused since the Overview page was deleted | `web/src/components/Sparkline.tsx` | [1.1] |
| E2 | `IconDashboard` and `IconShield`, unused | `web/src/components/Icons.tsx:56, 82` | [1.1] |
| E3 | `RetrievedChunk.source`, unused | `backend/app/knowledge/retrieve.py:46-52` | [1.1] |
| E4 | `AIGateway.llm` and `AIGateway.cache` properties, unused | `backend/app/ai_gateway/gateway.py:66-72` | [1.1] |
| E5 | `Labels.rank`, only its own unit test calls it | `backend/app/authz/labels.py:61-63` | [1.1] |
| E6 | `Settings.assistant_evidence_only`, never read | `backend/app/config.py:88` | [1.1] |
| E7 | Re-exports of `expired_certifications` and `ToolFn` that nothing imports | `backend/app/data_queries/tools/__init__.py:25, 29, 33` | [1.1] |
| E8 | `units.is_subsidiary` and `units.subsidiary_path`, unused (reused or removed in 2.2) | `backend/app/units.py:30-43` | [2.2] |
| E9 | Seed modules export underscore names that are public in practice (`_STRATOC`, `_days_from_today`…); `app.seed` re-exports private `_rows`; `connected.py` has its own `_UAS_WING` copy of `_BRIECH`; `base.py` writes unit paths out instead of using the constants; the loader docstring repeats the package docstring | `backend/app/seed/__init__.py:15-20`, `seed/records/common.py`, `seed/records/connected.py:24`, `seed/records/base.py`, `seed/loader.py:1-10` | [1.2] |
| E10 | Stale comments: "audit attachment happens when the knowledge pathway lands" (`ai_gateway/gateway.py:13-15`); a seed comment still says forensics lives in `connected.py` (`seed/records/connected.py:9`); `alembic.ini:3` points at a nonexistent `tests/integration/conftest.py`; `.dockerignore` lists a nonexistent `frontend/`; `data/SOURCES.md` is an empty tracked file | as listed | [1.2] |
| E11 | `EMBEDDING_DIM = 1024` is written in `knowledge/models.py:13` and again as `settings.embedding_dim`, with nothing checking they agree | as listed | [1.2]: a test asserts they match (the value stays 1024, which the schema needs) |

### 5.F Tests and tooling

| ID | Finding | Fix [step] |
|---|---|---|
| T1 | Nothing fails today if a refactor changes a prompt by one byte. The existing key tests check that a key stays *stable*: across dates (`test_demo_date_prompts.py`), across chunk order (`test_answer.py:113`), and with the audit tag (`test_prefill_audit_tag.py`). None compares a prompt to a recorded value. | A prompt fingerprint test: build the knowledge, explain and report prompts from fixed inputs and compare their SHA-256 to recorded values. [0.1] |
| T2 | Nothing fails today if a refactor changes the API shape by accident. The endpoint tests check fields they know about, not the whole surface. | An OpenAPI snapshot test: the schema (paths, methods, response schemas) compared to a committed snapshot. Updated deliberately only by step 3.5. [0.1] |
| T3 | `auth_header` logs in on every call. Each login is an argon2 verify plus an audit event, and every 10th audit event is a git ledger commit. That is probably hundreds of logins per run (step 0.2 counts them). | Measure first. If a session token cache in `tests/support/http.py` cuts the run time meaningfully, keep it, with a fresh-login option for tests that check login events. Otherwise drop the idea. [0.2] |

### 5.G Docs that no longer match the code

| Doc | Stale text | Fix [step 5.3] |
|---|---|---|
| `README.md` | "MapLibre lands later"; "A group Compliance page covers…" (deleted 2026-10-10); the API table lists 11 of the 23 routes; the repo layout says the web app is "login, assistant chat, audit viewer" | Bring it in line with the code |
| `docs/DEMO_SCOPE.md` | Points to `app/correlation/derive.py` (does not exist; the rule is in `app/authz/labels.py`); script step 1 still mentions the `/compliance` page; a debt-style entry ("2026-10-07 — Draft report label…") sits at the end of the file | Fix the references; move the entry to PRODUCTION_DEBT |
| `docs/STUBS.md` | "Web app (Next.js) — Deferred" (it is built); "`correlation` … scaffolds" (built) | Update |
| `docs/PRODUCTION_DEBT.md` | `DevValidator` (it is `DevTokenValidator`), `_load_history`, `_query_embedding`; "only one demo user (`a.bello`) holds run_correlation" (it is `owner`); "Correlation: one rule-based analysis" (there are three); "Dashboard placeholders…" (fixtures gone; see D4); "dashboard certification tile" | Update the names and facts; keep the entries |
| `AGENTS.md` | Names the `TokenValidator` seam | True once D2 lands; otherwise leave it |

---

## 6. The steps, in order

Each step is one commit, with `check.sh` green and stop-for-go between steps. "Cache" says
whether the step could touch an LLM cache key (the fingerprint test from 0.1 checks it either way).

### Phase 0: safety net (test code only)

| Step | What | Covers | Cache | Risk |
|---|---|---|---|---|
| 0.1 | Prompt fingerprint test and OpenAPI snapshot test. Re-run the full `check.sh` and the smoke test to confirm the baseline. | T1, T2 | none | low |
| 0.2 | `tests/support/` package: move the shared helpers and fakes, replace the 30+ cross-test imports, set an explicit `pythonpath`. Measure the token-cache idea (T3). | A9, B7, T3 | none | low; pytest collection is checked by the run itself |

### Phase 1: dead code and stale config

| Step | What | Covers | Cache | Risk |
|---|---|---|---|---|
| 1.1 | Remove the unused backend and web code | E1-E7 | none | low |
| 1.2 | Seed module hygiene (no row changes: the seed counts test, the authz oracle and the fingerprint test all pin it); stale comments and config; the embedding-dim agreement test | E9-E11 | none if rows are byte-identical, which is asserted | low |

### Phase 2: one vocabulary per concept (backend)

| Step | What | Covers | Cache | Risk |
|---|---|---|---|---|
| 2.1 | `Label` works as an input to `derive`; `Scope.labels` is loaded once; the three throwaway classes go | B1, B2 | none | low |
| 2.2 | Unit vocabulary in `app/units.py`, used by home and divisions | A2, E8 | none | medium: division membership; the home, division and authz-matrix tests pin it |
| 2.3 | Identifier formats in one module | B3 | router params must not change; the routing tests and the fingerprint test pin them | medium |
| 2.4 | `utc_now_iso` to `app/clock.py`; `RetrievedChunk` extends `Passage`; one vector-literal helper and one embed-or-degrade helper | A4, B4, B5 | evidence text must stay identical; fingerprint | low |
| 2.5 | Correlation: `analysis.py` renamed `rising_faults.py`; `draft_finding` helper; `FindingRow` built from `FindingDraft` | A7, B6 | none | low; the correlation tests pin keys, text and labels |
| 2.6 | `reporting/marking.py` (plus D6 if you approve it) | A5 | none (text added after the model call) | low |

### Phase 3: structure (backend)

| Step | What | Covers | Cache | Risk |
|---|---|---|---|---|
| 3.1 | `app/divisions/` package: catalogue, specs, view builder, home attention counting. Routes become thin; absolute imports; helper type hints; `Annotated` query params | A1, A8, C2, C3 | none | medium: biggest move; the OpenAPI snapshot plus the division, home, report, forensics and matrix tests cover it |
| 3.2 | Split `api/endpoints.py` into auth, documents, records and audit routers | A6 | none | low; the route convention test and the OpenAPI snapshot cover it |
| 3.3 | Assistant ORM models to `app/assistant/models.py`; `StoredMessage` rename | A3 | none | low; `alembic check` against the test database must report no changes (there is no automated schema-drift test today, so this is run by hand in the step) |
| 3.4 | `TokenValidator` protocol and `get_token_validator()` (only if you approve D2) | D2 | none | low |
| 3.5 | Response models for the ten dict routes; regenerate `api-types.ts`; the web drops its hand-written copies. The OpenAPI snapshot is updated deliberately in this step, and only with schema additions (paths and response JSON unchanged) | C1 | none | medium: the `null` trap noted in C1; endpoint tests and smoke cover it |

### Phase 4: web (no visual change; smoke test after each step)

| Step | What | Covers | Risk |
|---|---|---|---|
| 4.1 | `displayValue()` and `recordHref()` in `lib/` | B10, C5 | low |
| 4.2 | `<Marking>` component | B11 | low |
| 4.3 | `useLoad()`, `<NotFound>`, `<Page>`, `<Brand>`; fix D9(a) here if approved | B12 | medium: five pages |
| 4.4 | `lib/palette.ts` as the one source of colour | B13 | low; a screenshot comparison in the smoke run confirms nothing shifted |
| 4.5 | `DIVISION_EXTRAS` map | C4 | low |
| 4.6 | Split the map and chat pages; fix D5 here if approved | W1, W2 | medium: replay timing and chat state; the smoke checks cover both pages |

### Phase 5: tooling and docs

| Step | What | Covers | Risk |
|---|---|---|---|
| 5.1 | Prompt markers as constants; one shared fake model (tests and smoke stub); prefill and smoke scripts read identity from the seed | B8, B9 | low |
| 5.2 | Cross-language sync tests for states and level names | B14 | low |
| 5.3 | Docs drift: README, DEMO_SCOPE, STUBS, PRODUCTION_DEBT; DECISIONS lines for the layout changes | 5.G | none |

Where the approved section 4 items slot in: D1 with 2.1 (same file), D3 after 3.1 (once the
dashboard routes live together), D4 with 1.1, D7 with 2.4, D8 with 2.1, D9(b-d) with 1.2.

---

## 7. Deliberately not changing

- **The existing migrations**, including the RLS rule repeated in four of them. It is history.
  The rule appearing in both `policy.row_filter` and the RLS policies is the design: two
  independent layers.
- **Prompt text**, including the persona sentence that opens all three system prompts
  (`knowledge/answer.py:40`, `data_queries/explain.py:21`, `reporting/training.py:42`). Folding it
  into a constant would remove three copies of one sentence and put every cached answer at risk.
  Not worth it.
- **Audit payload field names.** `item_ids` and `record_ids` are used for the same thing in
  different routes. Renaming them would split the vocabulary of the audit history that is
  already in the chain.
- **Seed content, the keyword router's design, and the adapter's Python-side time windows.**
  All recorded stubs or debt; changing any of them is feature work, and the first two also move
  cache keys.
- **The `dashboard` policy resource name** (DECISIONS 2026-10-10).
- **Reserved columns** (`units.depth`, `messages.metadata`, `users.keycloak_id`).
- **The visual design and the motion tokens.** No new dependencies either: no data-fetching
  library, no state library.
- **`audit.chain.verify_chain`.** Only tests use it, but it is the readable form of the chain
  walk, and the tamper tests are clearer with it.

---

## 8. Risks and how each is controlled

| Risk | Control |
|---|---|
| A prompt changes and every cached answer silently becomes a miss | Fingerprint test (0.1) on every step |
| An API shape changes and the web or smoke test breaks | OpenAPI snapshot (0.1), endpoint tests, smoke after web steps |
| An authorization regression during a move | The RLS-only and filter-only oracle suites and the endpoint matrix run on every step, unchanged |
| A seed byte changes and the oracle or the cache drifts | Seed counts test, oracle, chunk-id determinism test, fingerprint |
| Smoke fails for reasons unrelated to the refactor | It needs the stub API (not the real one) and a seed less than a day old with the archived accounts. Reseeding wipes dev conversations, so I will ask before each reseed |
| `check.sh` breaks a running dev server | Stop the dev server before `check.sh`; restart with a clean `web/.next` |

---

## 9. Approval

Approved 2026-10-16 with D1-D9 yes and the recommended answers to D10-D12 (see the top of this
file). One step per commit, `check.sh` green, push, then stop for the go-ahead.

## 10. Progress

Tick a step when its commit is pushed; note the commit hash.

- [x] 0.1 (2982ab1) Prompt fingerprint and OpenAPI snapshot tests; baseline re-confirmed (check.sh green:
  622 passed, 5 skipped; UI smoke 66 ok, which is the 71 above less the five checks 7038e4e removed)
- [x] 0.2 (91e2208) `tests/support/` package; token-cache measurement (751 logins took 84 s of a 320 s
  run; with the cache: 21 logins, 171 s; 622 passed, 5 skipped both times)
- [x] 1.1 (de32dfa) Remove unused backend and web code (+ D4)
- [x] 1.2 (0ae2c97) Seed hygiene, stale comments and config, embedding-dim test (+ D9 b-d); seed rows
  byte-identical before and after (SHA-256 of every row but the argon2 hashes, DEMO_DATE pinned)
- [x] 2.1 (c33eea1) `Label` as a `derive` input, `Scope.labels` (+ D1, D8); the D1 and D8 tests in
  `tests/authz/test_conversation_store.py` fail on the code before this step
- [x] 2.2 (5f2ece0) Unit vocabulary: `is_site`, `subsidiary_key`, `covers`, `overlaps` in `app/units.py`,
  used by home, divisions and the tools' `unit_path` check; `is_subsidiary` and `subsidiary_path`
  deleted (unused; restore with `git show 860b101:backend/app/units.py`); `tests/unit/test_units.py`
  pins the home grouping rule and passes on the code before this step too
- [x] 2.3 (ad23f8e) Identifier formats: `app/data_queries/formats.py` (case, evidence, serial, depot, site,
  record id, contract statuses; `exact()` for tools, `mention()` for the router). The router's
  looser depot and site forms stay as they were. Old and new patterns compared on 300,000 random
  strings: same matches, spans and groups. The `REC-` copies in the test fakes and the smoke stub
  are left for 5.1
- [x] 2.4 (0ac30be) Clock helper, `RetrievedChunk` extends `Passage`, vector and embed helpers (+ D7):
  `utc_now_iso` in `app/clock.py`; `_Cited` gone; `embed_or_none` and `vector_literal` in
  `ai_gateway/embeddings.py` (`ingest._embed` stays as the name tests patch); the answer event
  gains `model_version`, token counts and `latency_ms` (`tests/unit/test_model_use.py`)
- [x] 2.5 (659ee2a) Correlation rename and finding helper: `analysis.py` is `rising_faults.py`;
  `draft_finding()` in `correlation/types.py`; `FindingRow` extends `FindingDraft`. A run's full
  findings JSON (all four, minus `created_at`) is byte-identical before and after
- [x] 2.6 (b444b7e) `reporting/marking.py` (+ D6): `DRAFT_BANNER` and `marking()` in one module, used by
  both reports; the training draft's marking line prints display names (`tests/unit/test_report_marking.py`
  fails on the code before this step). Prompt fingerprints unchanged
- [x] 3.1 (9addb2a; D3 db4e7e2) `app/divisions/` package: `catalog`, `specs`, `view`, `attention`;
  routes keep only HTTP, the domain raises `DivisionNotFound` / `TraceRefused`; OpenAPI and prompt
  snapshots unchanged. D3 (option b): `execute_tool` checks each tool requirement through
  `Scope.allows`; dashboard routes gain one decide event. Its five tests fail on the previous
  registry. Left open: the home "findings open" count reads the findings store under the
  dashboard read alone (not a tool, so outside D3)
- [x] 3.2 (c74ed20) Split `api/endpoints.py` into `api/auth.py`, `api/documents.py`, `api/records.py`,
  `api/audit.py`; OpenAPI snapshot unchanged
- [x] 3.3 (d08ab7b) Assistant ORM models in `app/assistant/models.py`; `StoredMessage`. `alembic check`
  on the test database: same three differences before and after, all pre-existing
  (`audit_events.prev_hash` and `chunks.search_vector` nullability, `ix_chunks_search_vector`)
- [x] 3.4 (9e46856) `TokenValidator` seam (D2): protocol and `get_token_validator()` in `authz/tokens.py`;
  `api/deps.py` and `tests/support/contexts.py` go through it; docs/STUBS.md names it
- [x] 3.5 (989059e) Response models for the ten dict routes; response JSON byte-identical before and
  after (six users, clock fields masked); map properties are one flat model serialised with
  `response_model_exclude_unset`; OpenAPI snapshot re-recorded with only the ten 200 responses and
  15 added schemas changed; `api-types.ts` regenerated and `lib/api.ts` aliases it (650 passed; smoke 66 ok)
- [x] 4.1 (913803a) `displayValue()` in `lib/format.ts` (options keep the findings comma lists and the
  table's yes/no), `recordHref()` in `lib/links.ts` for all nine record and finding links; old and new
  formatters compared value by value (650 passed; smoke 66 ok)
- [x] 4.2 (77e8db2) `<Marking>` in `components/Marking.tsx`, a fragment (same DOM) replacing the ten
  badge-plus-tags copies; no badge without a classification, as DivisionSections did (650 passed; smoke 66 ok)
- [ ] 4.3 `useLoad()`, `<NotFound>`, `<Page>`, `<Brand>` (+ D9 a)
- [x] 4.4 Palette (done before 4.3, at the user's request, ahead of the red-and-white re-theme):
  `lib/palette.ts` feeds `tailwind.config.ts`, `globals.css` (via `theme()`), the map and the login
  page. Checked by building the Tailwind CSS before and after: every colour value identical. Smoke
  not run (user asked for no test runs this session).
- [ ] 4.5 `DIVISION_EXTRAS`
- [ ] 4.6 Split the map and chat pages (+ D5)
- [ ] 5.1 Prompt markers, one shared fake, scripts read the seed identity
- [ ] 5.2 Cross-language sync tests
- [ ] 5.3 Docs drift
