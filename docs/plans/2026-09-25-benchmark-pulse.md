# Benchmark Pulse Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace unused Market Regime space with a compact Benchmark pulse built from the existing portfolio benchmark facts.

**Architecture:** Keep `TodaySnapshot` and all backend contracts unchanged. Move the existing benchmark rendering from Portfolio Overview into the Market Regime region, add restrained layout styles, and lock the placement and first-viewport behavior with component and Playwright tests.

**Tech Stack:** Next.js, React, TypeScript, CSS, Vitest/Testing Library, Playwright

---

### Task 1: Lock benchmark ownership with a failing component test

**Files:**
- Modify: `web/tests/today-page.test.tsx`

**Step 1: Write the failing test**

Add an assertion that the Market Regime region contains a `Benchmark pulse` heading and all four benchmark labels, and that each label appears only once on the page.

**Step 2: Run the focused test to verify it fails**

Run: `pnpm --dir web test --run tests/today-page.test.tsx`

Expected: FAIL because Market Regime does not yet contain `Benchmark pulse`.

### Task 2: Move the existing benchmark facts

**Files:**
- Modify: `web/components/today-page.tsx`
- Modify: `web/app/globals.css`

**Step 1: Implement the minimal component change**

Remove `benchmark-strip` from Portfolio Overview. Add a labelled `benchmark-pulse` section beneath the regime metric list and render the same four values from `snapshot.portfolio.benchmarks` with `formatPercent`.

**Step 2: Add restrained layout styles**

Use the existing 8pt Today spacing token, a soft top separator, and a two-column definition-list grid. Do not introduce another card or shadow.

**Step 3: Run the focused test to verify it passes**

Run: `pnpm --dir web test --run tests/today-page.test.tsx`

Expected: PASS.

### Task 3: Lock viewport behavior

**Files:**
- Modify: `web/e2e/happy-path.spec.ts`

**Step 1: Extend the Today workspace browser test**

Assert that Benchmark pulse is inside Market Regime, does not overlap the regime metrics, and remains above the shared surface bottom at both locked desktop viewports.

**Step 2: Run the focused browser test**

Run: `PLAYWRIGHT_WEB_PORT=3011 pnpm --dir web exec playwright test e2e/happy-path.spec.ts --grep "Today uses the approved split workspace" --workers=1`

Expected: PASS at desktop and mobile projects.

### Task 4: Verify and commit

**Files:**
- Modify: `docs/progress.md` only if this work is included in a milestone review

**Step 1: Run frontend verification**

Run: `pnpm --dir web test --run && pnpm --dir web lint && pnpm --dir web typecheck && pnpm --dir web build`

Expected: all commands exit 0.

**Step 2: Run browser verification**

Run: `PLAYWRIGHT_WEB_PORT=3011 pnpm --dir web exec playwright test e2e/happy-path.spec.ts e2e/accessibility.spec.ts --workers=1`

Expected: all tests pass.

**Step 3: Commit**

```bash
git add web/components/today-page.tsx web/app/globals.css web/tests/today-page.test.tsx web/e2e/happy-path.spec.ts
git commit -m "feat: add Today benchmark pulse"
```
