# Frontend Product Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the audit findings tracked in Linear milestone M8.1 using authoritative point-in-time API data, explicit unavailable states, and no Fixture fallback in API mode.

**Architecture:** Keep FastAPI as the source of persisted read models and parse every response into strict camel-case TypeScript contracts at the server boundary. Page components render only validated records and expose provenance, cutoff, and recovery actions without inventing facts. Changes proceed in Linear issue order with one red-green-refactor loop and verification record per issue.

**Tech Stack:** Next.js App Router, React, TypeScript, Vitest, Testing Library, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL.

---

### Task 1: Parse the locked Alerts response

**Files:**
- Modify: `web/lib/server/live-data-api.ts`
- Test: `web/tests/live-data-api.test.ts`

**Step 1: Write the failing test**

Add a response containing severity, materiality as a Decimal string, UTC timestamps, conditions, metrics, data quality, acknowledgement, correlation ID, rule ID, and rule version. Assert `getAlerts` returns a typed camel-case record and rejects numeric materiality or naive timestamps.

**Step 2: Run test to verify it fails**

Run: `cd web && npm test -- --run tests/live-data-api.test.ts`

Expected: FAIL because the generic paged-record parser does not expose the locked typed contract.

**Step 3: Write minimal implementation**

Add `AlertRecord` and `AlertPage`, parse every locked field with existing `text`, `decimal`, `instant`, `enumeration`, and object/array guards, then return the typed page from `getAlerts`.

**Step 4: Run test to verify it passes**

Run: `cd web && npm test -- --run tests/live-data-api.test.ts`

Expected: PASS.

### Task 2: Render usable API-mode Alerts

**Files:**
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/app/alerts/page.tsx`
- Test: `web/tests/api-pages.test.tsx`
- Test: `web/tests/api-boundary-routing.test.tsx`

**Step 1: Write the failing component and route tests**

Assert persisted alerts render severity, symbol, materiality, rule/version, event time, acknowledgement state, metrics/data-quality evidence, correlation ID, and useful Research/Run Trace destinations. Assert an empty response remains an honest empty state and no Fixture copy appears.

**Step 2: Run tests to verify they fail**

Run: `cd web && npm test -- --run tests/api-pages.test.tsx tests/api-boundary-routing.test.tsx`

Expected: FAIL because API mode currently renders only a count placeholder.

**Step 3: Write minimal implementation**

Add `ApiAlertsPage` and route the parsed records into it. Keep JSON evidence deterministic and readable, preserve PIT cutoff labels, and use existing design-system primitives.

**Step 4: Run tests to verify they pass**

Run: `cd web && npm test -- --run tests/api-pages.test.tsx tests/api-boundary-routing.test.tsx`

Expected: PASS.

### Task 3: Verify and record FRE-29 Alerts closure

**Files:**
- Modify: `docs/progress.md`

**Step 1: Run related frontend verification**

Run: `cd web && npm test -- --run tests/live-data-api.test.ts tests/api-pages.test.tsx tests/api-boundary-routing.test.tsx`

Expected: PASS with no skipped tests in the selected files.

**Step 2: Run static verification**

Run: `cd web && npm run lint && npm run build`

Expected: both commands exit 0.

**Step 3: Record evidence**

Append commands, exit codes, counts, remaining Eval persistence risk, and Linear issue ID FRE-29 to `docs/progress.md`.

**Step 4: Commit**

Run: `git add docs/plans/2026-09-09-frontend-product-closure.md web/lib/server/live-data-api.ts web/components/live/api-pages.tsx web/app/alerts/page.tsx web/tests/live-data-api.test.ts web/tests/api-pages.test.tsx web/tests/api-boundary-routing.test.tsx docs/progress.md && git commit -m "feat: render authoritative API alerts"`

### Task 4: Establish an authoritative Eval read model

**Files:**
- Modify after schema review: `backend/src/stock_platform/infrastructure/db/models/tables.py`
- Modify after schema review: `backend/src/stock_platform/api/schemas/rest.py`
- Modify after schema review: `backend/src/stock_platform/api/routes/rest.py`
- Create after schema review: `backend/alembic/versions/<revision>_add_eval_run_read_model.py`
- Modify: `web/lib/server/live-data-api.ts`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/app/eval/page.tsx`
- Test: relevant backend API/migration tests and `web/tests/live-data-api.test.ts`, `web/tests/api-pages.test.tsx`

**Steps:** Review the frozen Notion contract before adding persistence; write failing migration/API/parser/page tests; implement the smallest append-safe PIT read model; run focused tests and `make verify`; record evidence. Do not load Fixture or local evaluation-report files in API mode.

### Task 5: Complete remaining M8.1 issues in Linear order

Implement FRE-30, FRE-33, FRE-31, FRE-37, FRE-32, FRE-34, FRE-36, FRE-39, FRE-35, and FRE-38 one issue at a time. For each issue: confirm the authoritative contract, write a failing test, verify the expected failure, implement the minimum change, run focused and integration tests, update `docs/progress.md`, update Linear, and commit. Run `make verify` before milestone review.
