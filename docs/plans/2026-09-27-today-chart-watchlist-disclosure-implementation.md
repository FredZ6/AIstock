# Today Chart and Watchlist Disclosure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an accessible three-metric Portfolio chart to both Today modes and collapse Today Watchlist to two rows until the user expands it.

**Architecture:** Reuse the existing client-side `PerformanceChart` for Fixture and API Today. A small pure adapter derives API daily-return and drawdown strings from persisted NAV history with bigint-backed Decimal helpers; a separate client Watchlist section owns only the local disclosure state while server components continue to supply authoritative rows.

**Tech Stack:** Next.js 15, React 19, TypeScript, Vitest/Testing Library, Playwright, existing Decimal-string utilities and CSS tokens.

---

### Task 1: Derive presentation-safe API performance series

**Files:**
- Create: `web/components/portfolio/performance-series.ts`
- Test: `web/tests/performance-series.test.ts`

**Step 1: Write the failing Decimal-series tests**

Cover an ordered NAV series and assert:

```ts
expect(toPerformanceSeries([
  { nav: '100.00', availableAt: '2026-09-25T20:00:00Z' },
  { nav: '110.00', availableAt: '2026-09-26T20:00:00Z' },
  { nav: '99.00', availableAt: '2026-09-27T20:00:00Z' },
])).toEqual([
  { nav: '100.00', dailyReturn: null, drawdown: '0.00000000', time: '2026-09-25T20:00:00Z' },
  { nav: '110.00', dailyReturn: '0.10000000', drawdown: '0.00000000', time: '2026-09-26T20:00:00Z' },
  { nav: '99.00', dailyReturn: '-0.10000000', drawdown: '-0.10000000', time: '2026-09-27T20:00:00Z' },
])
```

Also assert input order is preserved, a single point has `dailyReturn: null`, and the helper never uses `Number` for financial derivation.

**Step 2: Run the test to verify RED**

Run:

```bash
pnpm --dir web vitest -- --run tests/performance-series.test.ts
```

Expected: FAIL because `toPerformanceSeries` does not exist.

**Step 3: Implement the minimal pure adapter**

Use `decimalChange` and `compareDecimals` from `web/lib/decimal.ts`. Track the running peak as a Decimal string, derive each drawdown against that peak, and leave the first daily return `null`.

**Step 4: Run the test to verify GREEN**

Run the Task 1 command. Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/portfolio/performance-series.ts web/tests/performance-series.test.ts
git commit -m "test: derive persisted portfolio chart series"
```

### Task 2: Make the compact Portfolio metrics control one chart

**Files:**
- Modify: `web/components/portfolio/performance-chart.tsx`
- Modify: `web/tests/today-page.test.tsx`
- Modify: `web/app/globals.css`

**Step 1: Write failing interaction tests**

Render Fixture Today and assert the compact Portfolio figure contains a tablist with `Net asset value`, `Day return`, and `Current drawdown`. Assert NAV is initially selected and the chart is named `Net asset value history`; click and keyboard-select the other tabs and assert the accessible chart name and `data-metric` change. Assert no three-series overlay exists.

**Step 2: Run tests to verify RED**

```bash
pnpm --dir web vitest -- --run tests/today-page.test.tsx
```

Expected: FAIL because compact mode currently hides metric tabs and labels cumulative return rather than day return.

**Step 3: Implement the minimal chart behavior**

Change the metric key to `dailyReturn`, keep NAV as the initial metric, render the accessible tabs in compact mode, and use the existing single SVG plot for the selected series. If the selected series has fewer than two usable persisted values, render `Not enough persisted history for this metric.` instead of a fabricated line.

**Step 4: Apply compact styles**

Use the existing theme tokens, a three-column segmented control on desktop, and wrapping controls on narrow screens. Preserve a minimum 44px hit area and the existing chart height budget.

**Step 5: Run tests to verify GREEN**

Run the Task 2 command. Expected: PASS.

**Step 6: Commit**

```bash
git add web/components/portfolio/performance-chart.tsx web/tests/today-page.test.tsx web/app/globals.css
git commit -m "feat: switch Today portfolio chart metrics"
```

### Task 3: Add a shared two-row Watchlist disclosure

**Files:**
- Create: `web/components/today/today-watchlist-section.tsx`
- Modify: `web/components/today/today-dashboard-model.ts`
- Modify: `web/components/today/today-dashboard.tsx`
- Modify: `web/tests/today-page.test.tsx`
- Modify: `web/tests/api-pages.test.tsx`

**Step 1: Write failing disclosure tests**

Supply four Fixture rows and four API rows. For each mode assert only the first two symbol links are initially present, `Show all (4)` has `aria-expanded=false`, keyboard activation reveals all four inside the same `Watchlist signals` list, and the control changes to `Show less` with `aria-expanded=true`. Assert one- and two-row inputs have no disclosure button.

**Step 2: Run tests to verify RED**

```bash
pnpm --dir web vitest -- --run tests/today-page.test.tsx tests/api-pages.test.tsx
```

Expected: FAIL because all rows are always rendered and no disclosure control exists.

**Step 3: Introduce the explicit Watchlist model**

Replace Watchlist's opaque `content` node with a panel containing `action`, `items`, `kicker`, and `title`. Keep the generic alert/run panel unchanged.

**Step 4: Implement the client disclosure section**

Create a client component that renders the section heading, independent Manage link, stable list id, first two items while collapsed, and all items while expanded. The local state is not persisted. Do not make the entire surface clickable and do not nest interactive elements.

**Step 5: Run tests to verify GREEN**

Run the Task 3 command. Expected: PASS.

**Step 6: Commit**

```bash
git add web/components/today/today-watchlist-section.tsx web/components/today/today-dashboard-model.ts web/components/today/today-dashboard.tsx web/tests/today-page.test.tsx web/tests/api-pages.test.tsx
git commit -m "feat: collapse Today watchlist after two rows"
```

### Task 4: Connect the API Portfolio chart without Fixture fallback

**Files:**
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/components/today-page.tsx`
- Modify: `web/tests/api-pages.test.tsx`

**Step 1: Write failing API chart tests**

Render API Today with three persisted NAV records and assert `Paper portfolio performance`, the three metric tabs, persisted timestamp copy, and the derived day-return/drawdown chart states. Render a single NAV record, select Day return, and assert the explicit insufficient-history message and absence of a synthetic line.

**Step 2: Run tests to verify RED**

```bash
pnpm --dir web vitest -- --run tests/api-pages.test.tsx tests/today-page.test.tsx
```

Expected: FAIL because API Today currently renders headline facts without a chart.

**Step 3: Adapt both data sources**

Pass Fixture `dailyReturn` history directly to `PerformanceChart`. Map API `performanceHistory` through `toPerformanceSeries`, use the latest derived values for headline Day return and Current drawdown, and label the source `Persisted paper NAV history`. Do not borrow Fixture values when the API series is absent.

**Step 4: Run focused and complete frontend tests**

```bash
pnpm --dir web vitest -- --run tests/performance-series.test.ts tests/today-page.test.tsx tests/api-pages.test.tsx tests/home.test.tsx
pnpm --dir web test -- --run
pnpm --dir web typecheck
pnpm --dir web lint
pnpm --dir web build
```

Expected: all commands exit 0.

**Step 5: Commit**

```bash
git add web/components/live/api-pages.tsx web/components/today-page.tsx web/tests/api-pages.test.tsx
git commit -m "feat: chart persisted portfolio history on Today"
```

### Task 5: Browser acceptance and repository closure

**Files:**
- Modify: `web/e2e/api-runtime.spec.ts`
- Modify: `web/e2e/happy-path.spec.ts`
- Modify: `docs/progress.md`

**Step 1: Write the failing browser acceptance**

At 1440x800, 1280x720, and 393x852 assert the default Watchlist has two rows, expands and collapses by keyboard, the Portfolio tabs switch one chart, focus remains visible, both themes preserve contrast, and no horizontal overflow appears. In API mode assert no Fixture copy or synthetic series appears.

**Step 2: Run browser tests to verify RED, then GREEN after integration**

```bash
pnpm --dir web exec playwright test e2e/happy-path.spec.ts e2e/api-runtime.spec.ts --project=desktop-chrome --project=mobile-chrome
```

Expected RED: new disclosure and chart assertions fail before integration. Expected GREEN: all selected checks pass.

**Step 3: Stop managed writers and run the repository gate**

```bash
make verify
```

Expected: Ruff, Mypy, Alembic drift, backend, frontend and production build all pass.

**Step 4: Record exact evidence**

Append RED/GREEN counts, viewport checks, provider gaps, and fresh `make verify` totals to `docs/progress.md`. Do not claim unavailable external data succeeded.

**Step 5: Commit delivery evidence**

```bash
git add web/e2e/api-runtime.spec.ts web/e2e/happy-path.spec.ts docs/progress.md
git commit -m "test: close Today chart and watchlist interaction"
```

**Step 6: Review the branch**

Run `git diff --check`, inspect `git status --short`, and verify `.gitignore` plus `Fred_Zhang_English_Resume.pdf` remain outside every commit.
