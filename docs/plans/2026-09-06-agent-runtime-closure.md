# Agent Runtime Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver one honest, deterministic, end-to-end research-agent workflow from the Research page through durable Celery execution and resumable SSE to a persisted, lineage-backed terminal report.

**Architecture:** Keep FastAPI admission transactional and let the existing Beat recovery loop dispatch queued runs. Execute the existing deterministic `DailyResearchGraph` in Celery, persist checkpoints and append-only events, proxy SSE through a same-origin Next.js route, and render a live Run Trace that refreshes into a closed persisted report. Extend report lineage only where the current schema cannot identify run-owned evidence gaps; do not add an LLM client, Fixture fallback in API mode, or any brokerage execution path.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL, Celery, Redis, LangGraph, Next.js, React, TypeScript, Pytest, Vitest, Playwright.

---

## Task 1: Close the persisted research-report lineage contract

**Files:**

- Create: `backend/migrations/versions/0037_evidence_gap_run_lineage.py`
- Modify: `backend/src/stock_platform/infrastructure/db/models/tables.py`
- Modify: `backend/src/stock_platform/application/research/persistence.py`
- Modify: `backend/src/stock_platform/api/schemas/rest.py`
- Modify: `backend/src/stock_platform/api/routes/rest.py`
- Modify: `backend/tests/contract/api/test_rest_contract.py`
- Create: `backend/tests/integration/api/test_research_run_report.py`
- Modify: `backend/tests/integration/db/test_migrations.py`

### Step 1: Write failing contract and integration tests

Add tests proving that:

- `evidence_gap` has a nullable `run_id` foreign key for legacy rows and new persistence assigns the active run.
- `GET /api/v1/research-runs/{run_id}/report` has a closed response model.
- The report contains the persisted thesis, independent research opinion, decision pins, evidence links, claims, run-owned gaps, citations, and deterministic decision diff.
- Another run's evidence or gaps cannot leak into the response.
- An unfinished or unknown run returns the existing explicit error contract.

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest \
  backend/tests/contract/api/test_rest_contract.py \
  backend/tests/integration/api/test_research_run_report.py \
  backend/tests/integration/db/test_migrations.py -q
```

Expected: FAIL because `evidence_gap.run_id` and the closed lineage response do not exist.

### Step 2: Add the minimal schema lineage

Create migration `0037` adding `evidence_gap.run_id` as a nullable UUID foreign key to `agent_run.id` plus a query index. Keep it nullable so append-only legacy facts are not fabricated. Update the SQLAlchemy table mapping and make `PostgresResearchStore.persist` set `run_id` on every newly persisted gap.

### Step 3: Add closed Pydantic report models and query

Define extra-forbid response models for:

- thesis and independent opinion;
- decision-time, cutoff, prompt/model, and four policy pins;
- linked evidence with relation, weight, rationale, claim, provider, timestamps, content hash, and raw object key;
- run-owned evidence gaps;
- deterministic decision diff.

Build the response exclusively from persisted rows joined through `ThesisEvidenceLink`. Preserve UTC-aware datetimes and serialize numeric weights/confidence without introducing money floats.

### Step 4: Run focused and integration tests

```bash
UV_CACHE_DIR=.uv-cache uv run pytest \
  backend/tests/contract/api/test_rest_contract.py \
  backend/tests/integration/api/test_research_run_report.py \
  backend/tests/integration/research -q
```

Expected: PASS.

### Step 5: Verify migration repeatability

```bash
docker compose up -d --wait postgres
UV_CACHE_DIR=.uv-cache uv run alembic -c backend/alembic.ini upgrade head
UV_CACHE_DIR=.uv-cache uv run alembic -c backend/alembic.ini upgrade head
UV_CACHE_DIR=.uv-cache uv run alembic -c backend/alembic.ini check
```

Expected: all commands exit 0.

### Step 6: Commit

```bash
git add backend/migrations/versions/0037_evidence_gap_run_lineage.py \
  backend/src/stock_platform/infrastructure/db/models/tables.py \
  backend/src/stock_platform/application/research/persistence.py \
  backend/src/stock_platform/api/schemas/rest.py \
  backend/src/stock_platform/api/routes/rest.py \
  backend/tests/contract/api/test_rest_contract.py \
  backend/tests/integration/api/test_research_run_report.py \
  backend/tests/integration/db/test_migrations.py
git commit -m "feat(agent): close persisted research report lineage"
```

## Task 2: Add idempotent Research Run admission to the web server boundary

**Files:**

- Modify: `web/lib/server/live-data-api.ts`
- Create: `web/lib/research-run-action-state.ts`
- Create: `web/app/research/actions.ts`
- Modify: `web/tests/live-data-api.test.ts`
- Create: `web/tests/research-run-action.test.ts`

### Step 1: Write failing client and action tests

Test that the server-only client:

- sends `POST /api/v1/research-runs` with a stable `Idempotency-Key`;
- sends one normalized symbol and the exact same aware UTC timestamp for `decision_time` and `data_cutoff`;
- rejects invalid symbols locally;
- maps 429 admission saturation and backend failures to explicit action states;
- never returns Fixture data in API mode.

Run:

```bash
pnpm --dir web test -- --run tests/live-data-api.test.ts tests/research-run-action.test.ts
```

Expected: FAIL because the create client and server action do not exist.

### Step 2: Implement the minimal server-only API client

Add `createResearchRun` using the existing request/error conventions. Require the caller to provide the idempotency key and timestamps; do not generate either inside the low-level client.

### Step 3: Implement the server action

Normalize the symbol with the locked `[A-Z.]{1,10}` rule. Accept a hidden idempotency key generated for the rendered form, generate one aware UTC instant on the server, use it for both temporal fields, and return a discriminated action state containing either the admitted run id or a safe error message.

### Step 4: Run focused tests and typecheck

```bash
pnpm --dir web test -- --run tests/live-data-api.test.ts tests/research-run-action.test.ts
pnpm --dir web typecheck
```

Expected: PASS.

### Step 5: Commit

```bash
git add web/lib/server/live-data-api.ts web/lib/research-run-action-state.ts \
  web/app/research/actions.ts web/tests/live-data-api.test.ts \
  web/tests/research-run-action.test.ts
git commit -m "feat(web): admit idempotent research runs"
```

## Task 3: Add the Research page run control

**Files:**

- Create: `web/components/research/research-run-control.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/app/research/[symbol]/page.tsx`
- Modify: `web/tests/api-pages.test.tsx`
- Modify: `web/tests/research-workflow-pages.test.tsx`

### Step 1: Write failing component tests

Prove that API-mode Research renders:

- a prefilled editable symbol field;
- an honest `Run deterministic research` action label;
- a stable hidden idempotency key;
- pending and 429/error feedback;
- navigation to `/runs/{run_id}` only after successful admission.

Also prove that the page does not claim an LLM was used and does not expose broker controls.

Run:

```bash
pnpm --dir web test -- --run tests/api-pages.test.tsx tests/research-workflow-pages.test.tsx
```

Expected: FAIL because API Research has no run control.

### Step 2: Implement the minimal accessible control

Use `useActionState`, an associated label, keyboard-operable submit button, `aria-live` status copy, and the existing Apple-inspired surface tokens. Keep the current persisted research facts visible and make the run control the single primary action.

### Step 3: Run component tests, lint, and typecheck

```bash
pnpm --dir web test -- --run tests/api-pages.test.tsx tests/research-workflow-pages.test.tsx
pnpm --dir web lint
pnpm --dir web typecheck
```

Expected: PASS.

### Step 4: Commit

```bash
git add web/components/research/research-run-control.tsx \
  web/components/live/api-pages.tsx web/app/research/[symbol]/page.tsx \
  web/tests/api-pages.test.tsx web/tests/research-workflow-pages.test.tsx
git commit -m "feat(web): start deterministic research workflows"
```

## Task 4: Build the same-origin durable SSE transport

**Files:**

- Create: `web/app/api/research-runs/[runId]/events/route.ts`
- Modify: `web/lib/sse.ts`
- Create: `web/tests/sse-route.test.ts`
- Modify: `web/tests/sse.test.ts`

### Step 1: Write failing route and parser tests

Test that:

- the route validates the run id and proxies only to the configured server-only backend base URL;
- `Last-Event-ID` is forwarded on reconnect;
- response headers disable buffering and caching;
- upstream failures become explicit non-Fixture failures;
- the incremental parser handles split frames, custom `event:` types, comments, and final unterminated frames;
- `DurableEventStore` deduplicates replayed events and rejects sequence collisions.

Run:

```bash
pnpm --dir web test -- --run tests/sse.test.ts tests/sse-route.test.ts
```

Expected: FAIL because the same-origin route and incremental parser are absent.

### Step 2: Implement the proxy route

Forward the upstream `ReadableStream` without buffering. Preserve `text/event-stream`, forward `Last-Event-ID`, and set `Cache-Control: no-cache, no-transform` plus `X-Accel-Buffering: no`. Do not expose `API_BASE_URL` to client code.

### Step 3: Implement the incremental parser

Add a small stateful parser that converts SSE frames to the existing `AgentEvent` validator/store. Keep reconnect policy outside the parser so UI lifecycle remains testable.

### Step 4: Run focused tests and typecheck

```bash
pnpm --dir web test -- --run tests/sse.test.ts tests/sse-route.test.ts
pnpm --dir web typecheck
```

Expected: PASS.

### Step 5: Commit

```bash
git add web/app/api/research-runs/[runId]/events/route.ts \
  web/lib/sse.ts web/tests/sse-route.test.ts web/tests/sse.test.ts
git commit -m "feat(web): proxy durable agent event streams"
```

## Task 5: Render live Run Trace and the terminal persisted report

**Files:**

- Create: `web/components/trace/live-run-trace.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/app/runs/[runId]/page.tsx`
- Modify: `web/lib/server/live-data-api.ts`
- Create: `web/tests/live-run-trace.test.tsx`
- Modify: `web/tests/api-pages.test.tsx`

### Step 1: Write failing trace and report tests

Test the UI states:

- QUEUED and RUNNING show status, current node, elapsed time, retry/degradation information, checkpoint progress, data cutoff, and resume cursor;
- events are chronological and duplicate replay frames do not duplicate rows;
- a disconnect shows reconnecting without replacing the trace with Fixture content;
- terminal completion refreshes server data and renders opinion, confidence, thesis, linked evidence, gaps, citations, policy/model/prompt pins, and deterministic diff;
- FAILED and CANCELLED remain explicit terminal states.

Run:

```bash
pnpm --dir web test -- --run tests/live-run-trace.test.tsx tests/api-pages.test.tsx
```

Expected: FAIL because the API run page only renders metadata.

### Step 2: Add the report client and server page composition

Add a typed `getResearchRunReport`. The server page fetches run metadata and fetches the report only for terminal completed runs. Pass persisted initial state into the client trace component.

### Step 3: Implement durable client streaming

Use fetch streaming, `AbortController`, the incremental parser, and `DurableEventStore`. Reconnect with the last accepted event id using bounded backoff. On terminal events call `router.refresh()`; a browser refresh starts from persisted run metadata and the authoritative event stream.

### Step 4: Render the terminal report honestly

Label the workflow `Deterministic Research Workflow`. Make lineage identifiers and timestamps inspectable, keep evidence gaps prominent, and never infer missing report fields client-side.

### Step 5: Run focused tests, lint, and build

```bash
pnpm --dir web test -- --run tests/live-run-trace.test.tsx tests/api-pages.test.tsx
pnpm --dir web typecheck
pnpm --dir web lint
CI=true pnpm --dir web build
```

Expected: PASS.

### Step 6: Commit

```bash
git add web/components/trace/live-run-trace.tsx web/components/live/api-pages.tsx \
  web/app/runs/[runId]/page.tsx web/lib/server/live-data-api.ts \
  web/tests/live-run-trace.test.tsx web/tests/api-pages.test.tsx
git commit -m "feat(web): render durable research run traces"
```

## Task 6: Prove the full agent runtime and browser recovery loop

**Files:**

- Create: `scripts/verify-agent-runtime.sh`
- Modify: `Makefile`
- Modify: `backend/tests/integration/api/test_worker_execution.py`
- Modify: `backend/tests/integration/api/test_sse_resume.py`
- Modify: `web/e2e/api-runtime.spec.ts`
- Modify: `docs/progress.md`

### Step 1: Write failing runtime acceptance tests

Extend acceptance coverage to prove:

- duplicate admissions with the same idempotency key return the same run;
- Beat recovery dispatches a queued run to an actual Celery worker;
- the graph persists checkpoints and strictly increasing append-only events;
- SSE replay after disconnect resumes after the last event without duplication;
- FastAPI restart does not lose the run, cursor, or terminal report;
- worker retry/checkpoint recovery does not duplicate persisted facts;
- API/provider failure stays Failure/Degraded and never substitutes Fixture data;
- desktop and mobile browser flows complete with no serious automated accessibility violations.

Run the smallest new test first:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest \
  backend/tests/integration/api/test_worker_execution.py \
  backend/tests/integration/api/test_sse_resume.py -q
pnpm --dir web exec playwright test e2e/api-runtime.spec.ts
```

Expected: FAIL until the harness starts all required processes and the browser exercises the real UI stream.

### Step 2: Implement the isolated runtime harness

Create `scripts/verify-agent-runtime.sh` with cleanup traps and unique process/log/database names. It must:

1. start PostgreSQL, Redis, and MinIO;
2. migrate an isolated database to head;
3. seed only clearly identified persisted test facts;
4. start FastAPI, Celery worker, Beat, and API-mode Next.js;
5. run backend recovery checks and Playwright browser acceptance;
6. stop child processes and print log locations on failure.

Do not read or print provider secrets. Do not require a live provider for deterministic agent acceptance.

### Step 3: Add the Makefile acceptance target

Add `verify-agent-runtime` to `.PHONY` and map it only to the new script. Keep `make verify` deterministic and credential-free; document that milestone acceptance runs both commands.

### Step 4: Run runtime acceptance and recovery tests

```bash
./scripts/verify-agent-runtime.sh
./scripts/verify-recovery.sh
```

Expected: both exit 0 with an actual Celery execution, SSE replay, API restart, checkpoint recovery, and browser evidence.

### Step 5: Run the complete verification gate

```bash
make verify
```

Expected: exit 0; record exact test counts, skips, warnings, and command exit codes.

### Step 6: Update progress evidence

Append to `docs/progress.md`:

- scope and non-goals;
- implementation summary and key files;
- RED/GREEN commands with exit codes;
- runtime, recovery, browser, accessibility, and full-gate evidence;
- remaining risks, including deterministic-agent labeling and any unavailable live provider entitlement.

### Step 7: Commit

```bash
git add scripts/verify-agent-runtime.sh Makefile \
  backend/tests/integration/api/test_worker_execution.py \
  backend/tests/integration/api/test_sse_resume.py \
  web/e2e/api-runtime.spec.ts docs/progress.md
git commit -m "test(agent): verify durable research runtime"
```

## Final review gate

Before any completion claim:

```bash
git status --short
git diff main...HEAD --check
./scripts/verify-agent-runtime.sh
./scripts/verify-recovery.sh
make verify
```

Then perform a code review of `main...HEAD` focused on transaction boundaries, idempotency, point-in-time lineage, append-only behavior, SSE resumption, secret isolation, accessibility, and the absence of live-broker paths. Do not push, create a PR, or merge until separately authorized.
