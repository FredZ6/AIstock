# FRE-44 Truthful Availability and Eval State Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every operator-facing API page report unavailable facts with one explicit reason/state model, and keep incomplete test/sentinel evaluation runs out of the normal Eval view without deleting audit history.

**Architecture:** Add a small frontend availability domain model that converts provider health, request failures, missing data, stale data, unsupported domains, and degraded quality into structured facts. `StateBoundary` renders those facts consistently, including a safe action or an explicit “no producer” explanation. Add an opt-in backend `audience=operator` Eval listing that selects only runs with complete persisted metric and gate evidence; the default audit listing remains unchanged.

**Tech Stack:** Next.js, React, TypeScript, Vitest, Playwright, FastAPI, SQLAlchemy 2, PostgreSQL, Pytest.

---

### Task 1: Canonical availability state model

**Files:**
- Create: `web/lib/availability.ts`
- Modify: `web/components/states/state-boundary.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/components/watchlist/watchlist-page.tsx`
- Test: `web/tests/availability.test.ts`
- Test: `web/tests/page-states.test.tsx`

1. Write failing tests for all six non-success states: `EMPTY`, `UNSUPPORTED`, `UNCONFIGURED`, `STALE`, `DEGRADED`, and `FAILURE`.
2. Verify failures are caused by the missing structured model/rendering.
3. Implement the minimum typed availability fact, deduplication, grouping, status precedence, operator-action/no-producer rule, and accessible rendering.
4. Replace ad-hoc provider and missing-fact summaries on Today, Research, and Watchlist with the shared model.
5. Run the focused unit/component suite.

### Task 2: Truthful Today aggregation

**Files:**
- Modify: `web/app/page.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Test: `web/tests/home.test.tsx`
- Test: `web/tests/api-pages.test.tsx`

1. Write failing route tests proving fulfilled research `unavailableDomains` and reasons contribute to the visible count, including SEC.
2. Write a failing test proving provider display and summary derive from the same canonical status rule.
3. Implement structured aggregation for rejected APIs, quote gaps/quality, research gaps, provider health, and missing NAV.
4. Verify exact counts, reasons, links/actions, deduplication, and no Fixture fallback.

### Task 3: Operator Eval isolation with audit preservation

**Files:**
- Modify: `backend/src/stock_platform/api/routes/rest.py`
- Modify: `web/lib/server/live-data-api.ts`
- Modify: `web/app/eval/page.tsx`
- Test: `backend/tests/contract/api/test_rest_contract.py`
- Test: `web/tests/live-data-api.test.ts`
- Test: `web/tests/api-boundary-routing.test.tsx`

1. Write failing API contract tests showing `audience=operator` excludes incomplete sentinel runs but retains PASSED or FAILED runs that have both persisted metrics and regression gates; default `audience=all` preserves the audit history.
2. Implement the minimal SQL `EXISTS` filters without modifying or deleting append-only records.
3. Make the frontend request the operator audience and preserve point-in-time bounds.
4. Run backend and frontend focused contract tests.

### Task 4: Browser, accessibility, and completion verification

**Files:**
- Create: `web/e2e/truthful-availability.spec.ts`
- Modify: `docs/progress.md`

1. Add a browser matrix for desktop/mobile, keyboard disclosure, accessible state names, exact unavailable count, and Eval empty/operator behavior.
2. Run focused frontend tests, backend contract tests, Playwright accessibility/regression tests, and `make verify`.
3. Record every command, exit code, counts, skips, and remaining risks in `docs/progress.md`.
4. Review the final diff and only then prepare commit/push/PR handoff; do not mark FRE-44 Done before merged evidence exists.
