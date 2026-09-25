# Today Responsive Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Resolve the five remaining Today responsive and density findings without changing product data or safety semantics.

**Architecture:** Add one Playwright regression file at the rendered-page seam, then make narrowly scoped CSS changes in priority order. Keep every fix independently committed and re-verified against its original viewport.

**Tech Stack:** Next.js, React, CSS Grid/Flexbox, Playwright, Vitest

---

### Task 1: Prevent mobile summary clipping

**Files:**
- Create: `web/e2e/today-responsive-closure.spec.ts`
- Modify: `web/app/globals.css`

1. Add a 393×852 test asserting Portfolio Overview precedes Market Regime vertically and both regions remain inside the summary bounds.
2. Run the focused test and confirm it fails.
3. Add the compact-breakpoint specificity override that stacks the shared summary grid.
4. Re-run the focused test and confirm it passes.
5. Commit as `style(design): FINDING-001 — stack mobile Today summary`.

### Task 2: Bring decision facts forward on mobile

**Files:**
- Modify: `web/e2e/today-responsive-closure.spec.ts`
- Modify: `web/app/globals.css`

1. Add an assertion that the Portfolio Overview begins within the first 400px at 393×852 and the redundant mobile current label is hidden.
2. Confirm the test fails.
3. Compact the mobile chrome, Today heading, timezone grid, Fixture notice, and status spacing.
4. Confirm the focused test passes.
5. Commit as `style(design): FINDING-002 — compact mobile Today context`.

### Task 3: Rebalance Decision Activity at 1280px

**Files:**
- Modify: `web/e2e/today-responsive-closure.spec.ts`
- Modify: `web/app/globals.css`

1. Add a 1280×720 assertion that the Actionable alerts heading and `View all` remain on one line.
2. Confirm the test fails.
3. Give the alert panel a larger share of the two-column activity grid.
4. Confirm the focused test passes.
5. Commit as `style(design): FINDING-003 — rebalance Today activity rail`.

### Task 4: Keep NAV together

**Files:**
- Modify: `web/e2e/today-responsive-closure.spec.ts`
- Modify: `web/app/globals.css`

1. Assert that the NAV value has a single rendered line at 1440×800 and 1280×720.
2. Confirm the test fails.
3. Apply a Today-specific non-wrapping, optically scaled NAV rule.
4. Confirm the focused test passes.
5. Commit as `style(design): FINDING-004 — keep Today NAV together`.

### Task 5: Expose collapsed diagnostics at 1280×720

**Files:**
- Modify: `web/e2e/today-responsive-closure.spec.ts`
- Modify: `web/app/globals.css`

1. Assert that the collapsed Provider diagnostics disclosure intersects the 1280×720 viewport.
2. Confirm the test fails.
3. Tighten the Today-only collapsed disclosure height without changing its expanded contents.
4. Confirm the focused test passes.
5. Commit as `style(design): FINDING-005 — expose Today diagnostics`.

### Task 6: Full verification

1. Run `pnpm --dir web test --run && pnpm --dir web lint && pnpm --dir web typecheck && pnpm --dir web build`.
2. Run `CI=1 PLAYWRIGHT_WEB_PORT=3012 pnpm --dir web exec playwright test e2e/happy-path.spec.ts e2e/accessibility.spec.ts e2e/today-responsive-closure.spec.ts --workers=1 --reporter=line`.
3. Capture 1440×800, 1280×720, and 393×852 after screenshots and compare against the audit evidence.
4. Run `git diff --check` and report any remaining concerns.
