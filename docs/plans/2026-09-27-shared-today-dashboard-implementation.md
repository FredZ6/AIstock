# Shared Today Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Fixture and API Today routes render the same approved compact dashboard composition while API Mode continues to use only persisted real data.

**Architecture:** Introduce a shared presentation component and a small discriminated Today dashboard view model. Fixture and API components remain responsible for provenance-safe adaptation; the shared component owns layout, semantic regions, compact empty/degraded slots, and responsive ordering. The home route also reads the latest persisted research run so the API dashboard's execution slot is real rather than synthetic.

**Tech Stack:** Next.js 15 App Router, React 19, TypeScript, Vitest/Testing Library, Playwright, CSS custom properties and grid.

---

### Task 1: Lock the shared dashboard contract in RED tests

**Files:**
- Modify: `web/tests/today-page.test.tsx`
- Modify: `web/tests/api-pages.test.tsx`
- Modify: `web/tests/home.test.tsx`

**Step 1: Write failing component tests**

Add assertions that both `TodayPage` and `ApiTodayPage` expose the same semantic regions and order:

```tsx
const workspace = screen.getByRole('region', { name: 'Today decision workspace' })
expect(within(workspace).getByRole('region', { name: 'Market and portfolio summary' })).toBeInTheDocument()
expect(within(workspace).getByRole('region', { name: 'Watchlist signals' })).toBeInTheDocument()
expect(within(workspace).getByRole('region', { name: 'Decision activity' })).toBeInTheDocument()
expect(within(workspace).getByRole('region', { name: 'Research execution' })).toBeInTheDocument()
```

For API Mode, assert persisted quote/provider labels, persisted portfolio state, persisted alert/research content, live refresh, and no `Fixture Mode` text. Add an empty-slot case proving missing Portfolio, alerts, and run facts remain explicit.

**Step 2: Write the failing route-data test**

Mock `getLatestResearchRun` in `web/tests/home.test.tsx`, render API Home, and assert the run is passed into the shared dashboard. Add the rejected-request case and assert the execution slot degrades without failing the rest of Today.

**Step 3: Run tests to verify RED**

Run:

```bash
pnpm --dir web vitest -- --run tests/today-page.test.tsx tests/api-pages.test.tsx tests/home.test.tsx
```

Expected: FAIL because API Today lacks the shared Market/Portfolio and Research execution regions and Home does not request the latest run.

**Step 4: Commit the RED tests**

```bash
git add web/tests/today-page.test.tsx web/tests/api-pages.test.tsx web/tests/home.test.tsx
git commit -m "test: lock shared Today dashboard contract"
```

### Task 2: Extract the shared presentation model and component

**Files:**
- Create: `web/components/today/today-dashboard.tsx`
- Create: `web/components/today/today-dashboard-model.ts`
- Modify: `web/components/today-page.tsx`
- Modify: `web/components/live/api-pages.tsx`

**Step 1: Define a discriminated, presentation-safe model**

Create explicit slot types instead of importing either data source into the shared component:

```ts
export type TodaySlot<T> =
  | { kind: 'available'; value: T }
  | { kind: 'empty' | 'degraded' | 'unavailable'; message: string }

export type TodayDashboardModel = {
  mode: 'fixture' | 'api'
  asOf: string
  portfolio: TodaySlot<TodayPortfolioView>
  marketRegime: TodaySlot<TodayMarketRegimeView>
  watchlist: TodayWatchlistView[]
  alerts: TodayAlertView[]
  activeRun: TodaySlot<TodayRunView>
}
```

Keep monetary values as formatted strings supplied by adapters. Do not calculate money with frontend floating point.

**Step 2: Extract the approved layout**

Move the common header/workspace composition from `TodayPage` into `TodayDashboard`. Preserve these classes and semantic boundaries because browser tests depend on them:

- `.today-page`
- `.today-decision-workspace`
- `.market-portfolio-grid`
- `.today-watchlist`
- `.decision-activity`
- `Market and portfolio summary`, `Watchlist signals`, `Decision activity`, and `Research execution` regions.

The shared component renders compact labelled fallback content inside the same slots for non-available API facts.

**Step 3: Adapt Fixture Mode**

Map `TodaySnapshot` into the shared model in `TodayPage`. Keep the Fixture provenance pill and frozen-history language. Do not change Fixture values or semantics.

**Step 4: Adapt API Mode**

Map persisted Portfolio, quotes, research, alerts and latest run into the same model in `ApiTodayPage`. API-specific rules:

- Preserve `LiveDataRefresh`.
- Show API Mode and persisted provenance, never Fixture copy.
- Use quotes for the compact Watchlist rows and retain provider, coverage and availability time.
- Render persisted Alert facts, not Fixture summaries.
- Use the real latest run; show a compact empty/degraded execution slot when absent or unavailable.
- Render Market Regime unavailable unless an authoritative API fact exists; never copy `market-regime-v1` Fixture values.
- Keep Provider diagnostics and market lineage disclosures below the workspace.

**Step 5: Run component tests to verify GREEN**

Run the Task 1 command.

Expected: all selected tests pass.

**Step 6: Commit**

```bash
git add web/components/today web/components/today-page.tsx web/components/live/api-pages.tsx
git commit -m "refactor: share Today dashboard composition"
```

### Task 3: Connect persisted latest-run data to Home

**Files:**
- Modify: `web/app/page.tsx`
- Modify: `web/lib/server/live-data-api.ts` only if an existing type/export needs reuse; do not duplicate the existing `getLatestResearchRun` client.
- Test: `web/tests/home.test.tsx`

**Step 1: Extend the parallel request group**

Call existing `getLatestResearchRun(options)` with the other independent Today requests. Report a typed `latest-research-run` diagnostic on rejection and add one availability fact for the run slot.

**Step 2: Pass the fulfilled run to `ApiTodayPage`**

Use `null` only for an honest no-run/rejected state. Do not import Fixture run data.

**Step 3: Run route tests**

```bash
pnpm --dir web vitest -- --run tests/home.test.tsx tests/api-pages.test.tsx
```

Expected: all tests pass, including partial failure without Fixture fallback.

**Step 4: Commit**

```bash
git add web/app/page.tsx web/tests/home.test.tsx web/tests/api-pages.test.tsx
git commit -m "feat: show persisted run progress on Today"
```

### Task 4: Restore the approved responsive visual composition

**Files:**
- Modify: `web/app/globals.css`
- Modify: `web/e2e/happy-path.spec.ts`
- Modify: `web/e2e/today-responsive-closure.spec.ts`

**Step 1: Add a failing API-mode browser contract**

Extend browser coverage so the shared layout is checked in API Mode as well as Fixture Mode. At 1440x800 and 1280x720 assert:

- Portfolio/Market are left of Watchlist.
- Watchlist sits above Alert/Run activity.
- Alert and Run surfaces share a bottom edge with the left Portfolio surface within 2px.
- Horizontal and vertical surface gaps are equal within 2px.
- Critical workspace fits the first viewport when the available dataset is compact.
- No page-level horizontal overflow and visible body/data text remains at least 13px.

At mobile width, assert deliberate single-column ordering and no hidden critical slot.

**Step 2: Run browser test to verify RED**

```bash
pnpm --dir web exec playwright test e2e/happy-path.spec.ts e2e/today-responsive-closure.spec.ts --project=chromium
```

Expected: API layout assertions fail before final CSS alignment.

**Step 3: Apply the minimal shared CSS**

Reuse the existing `.today-decision-workspace` grid and dark/light design tokens. Add only shared-slot variants needed for compact API rows and fallback messages. Do not create a second API-only dashboard grid.

**Step 4: Run browser test to verify GREEN**

Run the Task 4 browser command.

Expected: all selected browser checks pass at desktop and mobile widths.

**Step 5: Commit**

```bash
git add web/app/globals.css web/e2e/happy-path.spec.ts web/e2e/today-responsive-closure.spec.ts
git commit -m "style: restore approved Today dashboard layout"
```

### Task 5: Full verification and delivery evidence

**Files:**
- Modify: `docs/progress.md`

**Step 1: Run focused and complete frontend gates**

```bash
pnpm --dir web test
pnpm --dir web typecheck
pnpm --dir web lint
pnpm --dir web build
```

Expected: all commands exit 0.

**Step 2: Run real API browser acceptance**

Start the managed Paper runtime, verify API Mode at `http://127.0.0.1:3000`, and run the existing live-provider closure. Confirm no Fixture text, real quote/provider lineage, latest-run state, explicit unavailable Market Regime where applicable, no overflow and both themes.

**Step 3: Run repository gate**

Stop long-running writers before the immutable database assertion, then run:

```bash
make verify
```

Expected: Ruff, Mypy, Alembic drift, backend, frontend and production build all pass.

**Step 4: Record evidence**

Append the exact RED/GREEN, browser and `make verify` results to `docs/progress.md`, including any external-provider gaps without fabricating success.

**Step 5: Commit delivery evidence**

```bash
git add docs/progress.md
git commit -m "docs: record shared Today dashboard verification"
```

**Step 6: Review the branch**

Run `git diff --check`, inspect `git status --short`, and confirm `.gitignore` plus `Fred_Zhang_English_Resume.pdf` remain outside every commit.
