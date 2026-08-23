# Watchlist API Integration Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:test-driven-development for every behavior change and superpowers:systematic-debugging for unexpected failures.

**Goal:** Persist the Watchlist page through the existing FastAPI REST contract while showing honest Failure/Degraded states and never falling back to Fixture data in API mode.

**Architecture:** An async Next.js route selects an explicit `fixture` or `api` data mode. In API mode, a server-only client calls the existing FastAPI watchlist endpoints, validates every response into a typed view model, and exposes mutations through Server Actions; the browser never receives the FastAPI base URL. Missing enrichment remains explicitly unavailable, so valid configuration renders in a degraded state instead of being padded with fixture or zero data.

**Tech Stack:** Next.js 15 App Router, React 19 Server Components and Server Actions, TypeScript 5.9, Vitest/Testing Library, FastAPI, PostgreSQL, Playwright.

---

### Task 1: Lock the Watchlist response parser and API-mode view model

**Files:**
- Create: `web/lib/watchlist-contract.ts`
- Create: `web/tests/watchlist-contract.test.ts`
- Modify: `web/lib/product-types.ts`

**Step 1: Write failing parser tests**

Cover a valid backend list and rejection of a malformed symbol, naive `created_at`/`updated_at`, non-boolean flags, non-object thresholds, and non-decimal `return_5m`. Also require missing `return_5m` to map to `null`, not a fabricated default.

```ts
const validRow = {
  symbol: 'NVDA',
  daily_research: true,
  intraday_monitoring: false,
  thresholds: { return_5m: '0.025' },
  created_at: '2026-08-23T00:00:00+00:00',
  updated_at: '2026-08-23T00:05:00+00:00',
}

expect(parseWatchlistRows([validRow])[0]).toMatchObject({
  symbol: 'NVDA',
  dailyResearch: true,
  intradayMonitoring: false,
  alertThreshold: '0.025',
  enrichment: { kind: 'unavailable' },
})
```

**Step 2: Run the focused test and confirm RED**

Run: `pnpm --dir web test -- --run tests/watchlist-contract.test.ts`

Expected: FAIL because `watchlist-contract.ts` and its parser do not exist.

**Step 3: Implement the minimal contract**

Add `ApiWatchlistItem` and a view-model union that keeps persisted configuration separate from unavailable enrichment. Reuse `parseAwareInstant`; validate decimal strings without converting them to JavaScript numbers.

```ts
export type WatchlistEnrichment =
  | { kind: 'available'; /* existing market/research fields */ }
  | { kind: 'unavailable'; missing: readonly string[] }

export type ApiWatchlistItem = {
  symbol: string
  dailyResearch: boolean
  intradayMonitoring: boolean
  alertThreshold: string | null
  createdAt: string
  updatedAt: string
  enrichment: WatchlistEnrichment
}
```

Do not reuse fixture prices or decisions when building this object.

**Step 4: Run focused tests and typecheck**

Run: `pnpm --dir web test -- --run tests/watchlist-contract.test.ts`

Expected: PASS.

Run: `pnpm --dir web typecheck`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/lib/watchlist-contract.ts web/lib/product-types.ts web/tests/watchlist-contract.test.ts
git commit -m "feat: validate persisted watchlist contract"
```

### Task 2: Implement explicit data-mode configuration and a server-only read client

**Files:**
- Create: `web/lib/server/data-mode.ts`
- Create: `web/lib/server/watchlist-api.ts`
- Create: `web/tests/watchlist-api.test.ts`
- Modify: `web/vitest.config.ts`

**Step 1: Write failing mode and transport tests**

Require `readWebDataMode` to accept only `api` and `fixture`. In API mode, require a valid HTTP(S) `API_BASE_URL`. Use an injected `fetch` to test:

- `GET /api/v1/watchlist` with `cache: 'no-store'`;
- success parsing;
- timeout/network failure classification;
- non-2xx classification without leaking response bodies;
- invalid JSON and invalid contract classification;
- no fixture module or fixture callback is consulted on any API error.

```ts
await expect(listWatchlist({
  baseUrl: 'http://api.test',
  fetchImpl: rejectingFetch,
})).rejects.toMatchObject({ kind: 'unavailable' })
expect(fixtureFallback).not.toHaveBeenCalled()
```

**Step 2: Run the focused test and confirm RED**

Run: `pnpm --dir web test -- --run tests/watchlist-api.test.ts`

Expected: FAIL because the server configuration and client modules do not exist.

**Step 3: Implement the minimal server-only client**

The client owns a bounded timeout, joins paths through `URL`, sends `Accept: application/json`, and throws a typed `WatchlistApiError` with safe `kind` and status metadata. Add `import 'server-only'`; configure Vitest to alias the marker to an empty test module if required by the runner.

Do not accept a fixture fallback parameter in production APIs. The negative fallback assertion must be proved at the route boundary later through explicit mode selection.

**Step 4: Run focused tests, lint, and typecheck**

Run: `pnpm --dir web test -- --run tests/watchlist-api.test.ts`

Expected: PASS.

Run: `pnpm --dir web lint && pnpm --dir web typecheck`

Expected: both commands exit 0.

**Step 5: Commit**

```bash
git add web/lib/server/data-mode.ts web/lib/server/watchlist-api.ts web/tests/watchlist-api.test.ts web/vitest.config.ts
git commit -m "feat: add fail-closed watchlist API client"
```

### Task 3: Add tested POST, PATCH, and DELETE operations

**Files:**
- Modify: `web/lib/server/watchlist-api.ts`
- Modify: `web/tests/watchlist-api.test.ts`

**Step 1: Write failing mutation tests**

Require exact methods, paths, JSON content type, and snake-case payloads:

```ts
await addWatchlistItem(client, {
  symbol: 'NVDA',
  dailyResearch: true,
  intradayMonitoring: true,
  thresholds: {},
})

await patchWatchlistItem(client, 'NVDA', {
  dailyResearch: false,
  thresholds: { return_5m: '0.03' },
})

await deleteWatchlistItem(client, 'NVDA')
```

Require POST/PATCH responses to pass the same strict parser and DELETE to accept only 204. Verify symbols are encoded and invalid symbols never reach `fetch`.

**Step 2: Run the focused test and confirm RED**

Run: `pnpm --dir web test -- --run tests/watchlist-api.test.ts`

Expected: FAIL because mutation functions are absent.

**Step 3: Implement minimal mutations**

Reuse one request helper and the parser. Keep threshold values as strings throughout. Do not add optimistic state or new FastAPI endpoints.

**Step 4: Run focused tests**

Run: `pnpm --dir web test -- --run tests/watchlist-api.test.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/lib/server/watchlist-api.ts web/tests/watchlist-api.test.ts
git commit -m "feat: persist watchlist mutations through REST"
```

### Task 4: Expose mutations through Server Actions

**Files:**
- Create: `web/app/watchlist/actions.ts`
- Create: `web/tests/watchlist-actions.test.ts`

**Step 1: Write failing action tests**

Mock the server-only client and `next/cache`. Require:

- invalid form values return a safe field/action error without calling FastAPI;
- add, update, and delete call the corresponding client exactly once;
- `revalidatePath('/watchlist')` occurs only after success;
- backend errors return a visible safe message and retain the submitted symbol;
- unchecked checkboxes become explicit `false` values;
- thresholds remain decimal strings.

**Step 2: Run the focused test and confirm RED**

Run: `pnpm --dir web test -- --run tests/watchlist-actions.test.ts`

Expected: FAIL because the Server Actions do not exist.

**Step 3: Implement minimal actions**

Use `'use server'`, a small serializable `WatchlistActionState`, shared input validation, and `revalidatePath`. Do not catch and reinterpret Next.js redirect/revalidation control flow.

**Step 4: Run focused tests and typecheck**

Run: `pnpm --dir web test -- --run tests/watchlist-actions.test.ts`

Expected: PASS.

Run: `pnpm --dir web typecheck`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/app/watchlist/actions.ts web/tests/watchlist-actions.test.ts
git commit -m "feat: add watchlist server actions"
```

### Task 5: Render honest Fixture, Failure, and Degraded page states

**Files:**
- Modify: `web/app/watchlist/page.tsx`
- Modify: `web/components/watchlist/watchlist-page.tsx`
- Create: `web/components/watchlist/watchlist-api-controls.tsx`
- Modify: `web/tests/research-workflow-pages.test.tsx`
- Create: `web/tests/watchlist-route.test.tsx`
- Modify: `web/app/globals.css`

**Step 1: Write failing route and component tests**

Require:

- fixture mode dynamically loads the frozen fixture and retains its notice;
- API mode renders persisted configuration without a fixture notice;
- API mode with valid configuration renders `Degraded` and lists unavailable market/research domains;
- API read failure renders a `Failure` alert and no symbol, fixture notice, fixture provider, price, research opinion, or TradingView chart;
- API rows render `Unavailable` instead of `$0.00`, `0%`, `ABSTAIN`, or `NO_ACTION`;
- add/update/delete forms expose pending controls and safe action errors;
- a delete control is keyboard accessible and names its symbol.

Use `vi.resetModules()` and mode-specific mocks to prove the API failure branch never imports or invokes the fixture export.

**Step 2: Run focused tests and confirm RED**

Run: `pnpm --dir web test -- --run tests/watchlist-route.test.tsx tests/research-workflow-pages.test.tsx`

Expected: FAIL because the route is fixture-only and the component has no API-mode states.

**Step 3: Implement the route and UI minimally**

Make the route async and force dynamic rendering in API mode. Select mode before loading data. Use a dynamic import for `fixtureWatchlistSnapshot` only inside the fixture branch. In API mode:

- call the server-only read client;
- map valid configuration into a degraded snapshot;
- render `StateBoundary` with degraded children;
- catch typed transport/contract failures and render `StateBoundary` failure without children.

Split persisted form behavior into a small client component using `useActionState`/`useFormStatus`. Keep the existing fixture-session behavior isolated and clearly labelled. Do not render TradingView charts for API rows whose authoritative enrichment is unavailable.

**Step 4: Run focused tests, accessibility unit tests, lint, and typecheck**

Run: `pnpm --dir web test -- --run tests/watchlist-route.test.tsx tests/research-workflow-pages.test.tsx tests/page-states.test.tsx`

Expected: PASS.

Run: `pnpm --dir web lint && pnpm --dir web typecheck`

Expected: both commands exit 0.

**Step 5: Commit**

```bash
git add web/app/watchlist/page.tsx web/components/watchlist/watchlist-page.tsx web/components/watchlist/watchlist-api-controls.tsx web/tests/watchlist-route.test.tsx web/tests/research-workflow-pages.test.tsx web/app/globals.css
git commit -m "feat: connect watchlist UI to persisted API state"
```

### Task 6: Make explicit data modes reproducible in development and CI

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `scripts/verify.sh`
- Modify: `web/playwright.config.ts`
- Modify: `web/tests/watchlist-api.test.ts`

**Step 1: Write the failing configuration assertions**

Extend tests to prove missing/unknown `WEB_DATA_MODE` fails closed and API mode without `API_BASE_URL` fails clearly. Confirm `API_BASE_URL` is not exposed through a `NEXT_PUBLIC_` variable.

**Step 2: Run the focused test and confirm RED**

Run: `pnpm --dir web test -- --run tests/watchlist-api.test.ts`

Expected: FAIL until strict environment handling is complete.

**Step 3: Document and wire explicit modes**

Add to `.env.example`:

```dotenv
WEB_DATA_MODE=fixture
API_BASE_URL=http://127.0.0.1:8000
```

Document that API mode never falls back and requires the backend/database. Set `WEB_DATA_MODE=fixture` explicitly in fixture-only CI build and Playwright commands. Do not introduce a production default in application code.

**Step 4: Run the focused configuration and build checks**

Run: `pnpm --dir web test -- --run tests/watchlist-api.test.ts`

Expected: PASS.

Run: `WEB_DATA_MODE=fixture pnpm --dir web build`

Expected: PASS.

**Step 5: Commit**

```bash
git add .env.example README.md scripts/verify.sh web/playwright.config.ts web/tests/watchlist-api.test.ts
git commit -m "docs: make frontend data modes explicit"
```

### Task 7: Prove the real API vertical slice and complete verification evidence

**Files:**
- Create: `web/e2e/watchlist-api.spec.ts`
- Modify: `docs/progress.md`

**Step 1: Write the API-mode E2E test**

Against the local FastAPI/PostgreSQL stack, require the Watchlist page to add a unique symbol, persist toggles and a decimal threshold, survive a page reload, then delete the symbol. Add a separate controlled-backend test proving an unavailable API produces `Failure` and no fixture symbols.

**Step 2: Run the test and confirm RED**

Run the API and web app in explicit API mode, then run:

`WEB_DATA_MODE=api API_BASE_URL=http://127.0.0.1:8000 pnpm --dir web exec playwright test e2e/watchlist-api.spec.ts --project=desktop-chrome`

Expected: FAIL before the E2E harness and completed UI behavior exist.

**Step 3: Add the minimum deterministic E2E harness**

Use the existing Docker Compose/PostgreSQL setup and FastAPI app. Seed only watchlist configuration needed by the test. Cleanup must delete only the test symbol; do not reset shared databases or volumes.

**Step 4: Run focused, integration, and full verification**

Record every command and exit code in `docs/progress.md`:

```bash
uv run pytest -q backend/tests/contract/api/test_rest_contract.py -k watchlist
pnpm --dir web test -- --run tests/watchlist-contract.test.ts tests/watchlist-api.test.ts tests/watchlist-actions.test.ts tests/watchlist-route.test.tsx tests/research-workflow-pages.test.tsx
WEB_DATA_MODE=api API_BASE_URL=http://127.0.0.1:8000 pnpm --dir web exec playwright test e2e/watchlist-api.spec.ts --project=desktop-chrome
make verify
git diff --check
git status --short
```

Expected: all commands exit 0; test totals and any skips/warnings are copied from actual output, never estimated.

**Step 5: Commit verification evidence**

```bash
git add web/e2e/watchlist-api.spec.ts docs/progress.md
git commit -m "test: verify persisted watchlist vertical slice"
```

### Task 8: Delivery review and collaboration updates

**Files:**
- No product-code changes expected.

**Step 1: Review the complete branch diff**

Run: `git diff main...HEAD --check`

Run: `git diff --stat main...HEAD`

Run: `git log --oneline main..HEAD`

Expected: only approved Watchlist API integration, tests, and documentation are present.

**Step 2: Run pre-completion verification**

Invoke `superpowers:verification-before-completion`; rerun any stale evidence before making completion claims.

**Step 3: Push and open a PR**

Push `codex/watchlist-api-integration`, create a PR against `main`, and inspect the remote diff and CI results. Do not merge until review finds no P1 blockers and CI is green.

**Step 4: Update Notion and Linear**

Record scope, key files, exact test commands/exit codes, report paths, risks, branch, commit, and PR. Do not mark an issue Done before the PR is merged and its merge commit is recorded.

**Step 5: Stop at the approved boundary**

Do not begin Alpaca/SEC/Alpha Vantage ingestion until the remaining Notion data-backend design items are completed and approved.
