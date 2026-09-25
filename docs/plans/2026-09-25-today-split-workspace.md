# Today Split Workspace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Recompose Today into an adaptive two-column desktop split so Portfolio/Market and Watchlist/Alerts/Run all fit inside the MacBook Air first viewport.

**Architecture:** Keep the existing semantic DOM and data contracts, and change only the Today grid placement and compact right-column presentation. Fixture and API Today share the same direct-child classes; desktop CSS assigns those children to the two-column workspace, while the existing 64rem breakpoint restores semantic single-column order.

**Tech Stack:** Next.js 15, React 19, TypeScript, CSS Grid, Vitest/Testing Library, Playwright, Axe.

---

### Task 1: Lock the approved desktop geometry

**Files:**
- Modify: `web/e2e/happy-path.spec.ts`

**Step 1: Write the failing test**

At 1440×800 and 1280×720, assert that:

```ts
expect(summaryBounds.x).toBeLessThan(watchlistBounds.x)
expect(Math.abs(watchlistBounds.x - activityBounds.x)).toBeLessThanOrEqual(2)
expect(watchlistBounds.y).toBeLessThan(activityBounds.y)
expect(workspaceBounds.y + workspaceBounds.height).toBeLessThanOrEqual(viewport.height)
```

Keep the existing no-overlap assertions for Watchlist facts.

**Step 2: Run the test and verify RED**

Run:

```bash
PLAYWRIGHT_WEB_PORT=3011 pnpm --dir web exec playwright test e2e/happy-path.spec.ts --project=desktop-chrome --grep "Today uses the approved split workspace" --workers=1
```

Expected: FAIL because the existing layout stacks the full-width summary above the lower grid and exceeds the first viewport.

**Step 3: Commit the test with the implementation in Task 2 after GREEN**

Do not weaken the existing 1440×800, 1280×720, text-zoom, or mobile overflow assertions.

---

### Task 2: Implement the 65/35 split without changing data behavior

**Files:**
- Modify: `web/app/globals.css`

**Step 1: Apply minimal desktop grid placement**

- Set the Today workspace to `minmax(0, 1.5fr) minmax(24rem, 1fr)` so the action rail remains readable at 1280×720.
- Place `.market-portfolio-grid` and API `.portfolio-overview` in column 1 spanning both rows.
- Place `.today-watchlist` in column 2, row 1.
- Place `.decision-activity` in column 2, row 2.
- Keep the 64rem breakpoint reset to one column and automatic rows.

**Step 2: Compact only the right-column internals**

- Use two equal Watchlist cards on wide desktop where both remain readable.
- Reduce Today-only card gaps/padding without reducing data text below 13px.
- Keep Alerts and Research Run as separate surfaces with visible headings and actions.
- Do not hide provider, freshness, coverage, delay, conflict, or decision fields.

**Step 3: Run the focused test and verify GREEN**

Run:

```bash
PLAYWRIGHT_WEB_PORT=3011 pnpm --dir web exec playwright test e2e/happy-path.spec.ts --project=desktop-chrome --grep "Today uses the approved split workspace" --workers=1
```

Expected: PASS at both locked desktop viewports.

**Step 4: Run component regressions**

Run:

```bash
pnpm --dir web test --run tests/today-page.test.tsx tests/home.test.tsx tests/api-pages.test.tsx
pnpm --dir web typecheck
```

Expected: PASS with no Fixture/API truthfulness regression.

---

### Task 3: Verify the complete frontend story

**Files:**
- Modify: `docs/progress.md` only if this change is included in a milestone handoff.

**Step 1: Perform visual review**

Capture 1440×800 and confirm Portfolio/Market is left, Watchlist/Alerts/Run is right, and all critical content is visible without overlap.

**Step 2: Run full frontend verification**

Run:

```bash
pnpm --dir web test --run
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web build
PLAYWRIGHT_WEB_PORT=3011 pnpm --dir web exec playwright test e2e/happy-path.spec.ts e2e/accessibility.spec.ts --workers=1
```

Expected: 238+ unit tests pass, production build succeeds, and all desktop/mobile browser and accessibility tests pass.

**Step 3: Commit the verified change**

```bash
git add web/app/globals.css web/e2e/happy-path.spec.ts
git commit -m "fix: fit Today workspace in MacBook viewport"
```
