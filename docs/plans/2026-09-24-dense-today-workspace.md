# Dense Today Workspace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fit Portfolio, Market Regime, Watchlist, Alerts, and Research activity in the 1440×900 Today viewport while preserving truthful availability and readable interaction bounds.

**Architecture:** Recompose the existing Fixture and API Today markup into a shared semantic hierarchy using existing data contracts. Apply density through shared classes and desktop-only layout rules; provider diagnostics and complete evidence remain in collapsed native disclosures below the decision workspace. Do not change calculations, providers, API requests, or Paper Trading boundaries.

**Tech Stack:** Next.js 15, React 19, TypeScript, CSS, Vitest/Testing Library, Playwright, Axe.

---

### Task 1: Lock the dense Fixture Today hierarchy

**Files:**
- Modify: `web/tests/today-page.test.tsx`
- Modify: `web/components/today-page.tsx`

**Step 1: Write the failing semantic hierarchy test**

Add a test that renders the existing `snapshot` and asserts:

```tsx
const workspace = screen.getByRole('region', { name: 'Today decision workspace' })
expect(workspace).toHaveClass('today-decision-workspace')
expect(within(workspace).getByRole('region', { name: 'Portfolio overview' })).toHaveClass('portfolio-overview')
expect(within(workspace).getByRole('region', { name: 'Market regime' })).toHaveClass('market-regime-compact')
expect(within(workspace).getByRole('list', { name: 'Watchlist signals' })).toHaveClass('market-list')
expect(within(workspace).getByRole('region', { name: 'Decision activity' })).toHaveClass('decision-activity')
expect(screen.getByRole('group', { name: 'Provider diagnostics' })).not.toHaveAttribute('open')
```

Keep every existing assertion for Fixture labeling, quality dimensions, benchmarks, alerts, and run progress.

**Step 2: Run the focused test and verify RED**

Run:

```bash
pnpm --dir web exec vitest --run tests/today-page.test.tsx
```

Expected: FAIL because the dense workspace regions, market-list class, and collapsed provider disclosure do not exist.

**Step 3: Implement the minimal Fixture markup**

In `TodayPage`:

- wrap the first-viewport content in `<section aria-label="Today decision workspace" className="today-decision-workspace">`;
- make Portfolio the first semantic region and retain `PerformanceChart` plus all four benchmarks;
- make Market Regime a sibling region with `market-regime-compact`;
- rename the Watchlist accessible list to `Watchlist signals` and use `market-list`;
- place Alerts and Research execution inside `<section aria-label="Decision activity" className="decision-activity">`;
- move Provider health into `<details className="provider-diagnostics"><summary>Provider diagnostics</summary>…</details>` after the workspace;
- limit visible alerts with `snapshot.alerts.slice(0, 3)` while keeping the full Alerts route link;
- do not remove provider states, quality dimensions, Fixture labels, or links.

**Step 4: Run Fixture Today regressions**

Run:

```bash
pnpm --dir web exec vitest --run tests/today-page.test.tsx tests/home.test.tsx
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/today-page.tsx web/tests/today-page.test.tsx
git commit -m "style: compose dense Today decision workspace"
```

---

### Task 2: Give API Today the same truthful hierarchy

**Files:**
- Modify: `web/tests/api-pages.test.tsx`
- Modify: `web/tests/home.test.tsx`
- Modify: `web/components/live/api-pages.tsx`

**Step 1: Write the failing API hierarchy test**

Extend the successful API Today fixture and assert:

```tsx
const workspace = screen.getByRole('region', { name: 'Today decision workspace' })
expect(within(workspace).getByRole('region', { name: 'Portfolio overview' })).toBeInTheDocument()
expect(within(workspace).getByRole('list', { name: 'Market watchlist' })).toHaveClass('market-list')
expect(within(workspace).getByRole('region', { name: 'Decision activity' })).toBeInTheDocument()
expect(screen.getByRole('group', { name: 'Provider diagnostics' })).not.toHaveAttribute('open')
expect(screen.getByText('Current market context · not decision-time evidence')).toBeInTheDocument()
```

Keep the existing assertions that persisted data remains visible, unavailable domains stay explicit, and Fixture data is never substituted.

**Step 2: Run and verify RED**

Run:

```bash
pnpm --dir web exec vitest --run tests/api-pages.test.tsx tests/home.test.tsx
```

Expected: FAIL on the new hierarchy and disclosure contract.

**Step 3: Implement the minimal API markup**

In `ApiTodayPage`:

- place the persisted Paper Portfolio value first in `portfolio-overview`;
- render the persisted quote evidence as `ul.market-list` inside the workspace and keep TradingView clearly labeled as external current context;
- place the latest Research decisions and at most three Alerts in `decision-activity`;
- retain exact cutoff, provider, coverage, and `availableAt` facts;
- move Provider health and verbose persisted evidence into closed `<details aria-label="Provider diagnostics">` and `<details aria-label="Complete market lineage">` elements below the workspace;
- when a region has no authoritative record, keep the existing canonical unavailable fact rather than adding a placeholder value.

**Step 4: Run API and degradation regressions**

Run:

```bash
pnpm --dir web exec vitest --run tests/api-pages.test.tsx tests/home.test.tsx tests/api-route-degradation.test.tsx tests/page-states.test.tsx
pnpm --dir web run typecheck
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/live/api-pages.tsx web/tests/api-pages.test.tsx web/tests/home.test.tsx
git commit -m "style: align API Today with dense workspace"
```

---

### Task 3: Apply desktop density without sacrificing mobile readability

**Files:**
- Modify: `web/tests/visual-system-contract.test.ts`
- Modify: `web/app/globals.css`

**Step 1: Write the failing density token test**

Add stylesheet assertions:

```ts
expect(css).toContain('--space-dashboard: clamp(0.75rem, 1.4vw, 1.25rem);')
expect(css).toMatch(/\.today-decision-workspace\s*\{[^}]*grid-template-columns:/s)
expect(css).toMatch(/\.market-list\s*>\s*li\s*\{[^}]*min-height:\s*2\.75rem/s)
expect(css).toMatch(/@media \(max-width: 64rem\)[\s\S]*\.today-decision-workspace/s)
expect(css).toMatch(/@media \(max-width: 48rem\)[\s\S]*\.market-list/s)
```

**Step 2: Run and verify RED**

Run:

```bash
pnpm --dir web exec vitest --run tests/visual-system-contract.test.ts
```

Expected: FAIL on missing density token and responsive workspace rules.

**Step 3: Implement the desktop and responsive CSS**

- add `--space-dashboard` without changing the minimum 13px body/data text;
- cap the desktop heading at 44px and reduce the Today heading block height;
- use a two-column top tier for Portfolio and Market Regime;
- use a wider market-list column plus a compact activity rail below it;
- render market rows with aligned symbol/context, decision, price, and change columns;
- keep each interactive row/control at least `2.75rem` high;
- reduce card padding and section gaps by 20–30% only in the dense workspace;
- collapse at 64rem, then use one column at 48rem without shrinking text;
- keep the availability summary one row and all disclosure content keyboard accessible.

**Step 4: Run component and type regressions**

Run:

```bash
pnpm --dir web exec vitest --run tests/visual-system-contract.test.ts tests/today-page.test.tsx tests/api-pages.test.tsx tests/home.test.tsx tests/page-states.test.tsx
pnpm --dir web run typecheck
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/app/globals.css web/tests/visual-system-contract.test.ts
git commit -m "style: fit decision facts in the desktop viewport"
```

---

### Task 4: Verify the 1440×900 viewport and accessibility contract

**Files:**
- Modify: `web/tests/e2e/product-shell.spec.ts`
- Modify: `web/tests/e2e/accessibility.spec.ts`
- Modify: `docs/progress.md`

**Step 1: Write the failing browser assertions**

At viewport `{ width: 1440, height: 900 }`, assert:

```ts
const workspace = page.getByRole('region', { name: 'Today decision workspace' })
await expect(workspace).toBeVisible()
const box = await workspace.boundingBox()
expect(box).not.toBeNull()
expect(box!.y + box!.height).toBeLessThanOrEqual(900)
await expect(page.getByRole('group', { name: 'Provider diagnostics' })).not.toHaveAttribute('open', '')
```

Also retain mobile overflow, keyboard navigation, theme, and serious/critical Axe assertions.

**Step 2: Run browser test and verify RED if geometry is not yet within target**

Run:

```bash
pnpm --dir web exec playwright test tests/e2e/product-shell.spec.ts tests/e2e/accessibility.spec.ts --project=chromium
```

Expected before final tuning: geometry assertion may FAIL; semantic and accessibility checks must remain valid.

**Step 3: Make only measured CSS adjustments**

Adjust desktop gaps, card padding, and visible row count until the complete decision workspace fits at 1440×900. Do not reduce text below 13px, controls below 44px, or hide required facts.

**Step 4: Run final frontend verification**

Run:

```bash
pnpm --dir web test
pnpm --dir web run typecheck
pnpm --dir web run build
pnpm --dir web exec playwright test tests/e2e/product-shell.spec.ts tests/e2e/accessibility.spec.ts --project=chromium
```

Expected: PASS.

**Step 5: Record evidence and commit**

Append exact commands, exit codes, test counts, viewport result, and any warnings to `docs/progress.md`, then run:

```bash
git add web/tests/e2e/product-shell.spec.ts web/tests/e2e/accessibility.spec.ts docs/progress.md
git commit -m "test: verify dense Today workspace"
```

Before claiming branch completion, invoke `@superpowers:verification-before-completion` and run `make verify` as required by `AGENTS.md`.
