# MacBook Air Dense Interface Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make all eight primary routes expose their decision-critical content within a 1440×800 MacBook Air browser viewport while preserving readable text, 44px targets, and complete disclosed evidence.

**Architecture:** Extend the existing Apple Finance token layer with one responsive density system shared by headings, summary grids, compact lists, tables, and disclosures. Recompose route markup only where semantic grouping is required; existing API contracts, calculations, availability states, and Paper Trading boundaries remain unchanged. Use native `details` for secondary diagnostics and full audit records.

**Tech Stack:** Next.js 15, React 19, TypeScript, CSS, Vitest/Testing Library, Playwright, Axe.

---

### Task 1: Establish the MacBook Air density contract

**Files:**
- Modify: `web/tests/visual-system-contract.test.ts`
- Modify: `web/tests/product-shell.test.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/components/ui/product-ui.tsx`

**Step 1: Write failing density assertions**

Assert the stylesheet and shared heading expose:

```ts
expect(css).toContain('--space-dashboard: clamp(0.75rem, 1.4vw, 1.25rem);')
expect(css).toContain('--row-compact: 2.75rem;')
expect(css).toMatch(/\.page-heading-compact\s+h1\s*\{[^}]*font-size:\s*clamp\(2\.25rem,[^;]*2\.75rem\)/s)
expect(css).toMatch(/@media \(max-width: 80rem\)/)
expect(css).toMatch(/@media \(max-width: 64rem\)/)
expect(screen.getByLabelText('Snapshot time')).toHaveClass('page-context')
```

Keep the existing reduced-motion, reduced-transparency, contrast, focus, and theme assertions.

**Step 2: Run RED**

```bash
pnpm --dir web exec vitest --run tests/visual-system-contract.test.ts tests/product-shell.test.tsx
```

Expected: FAIL on the new density tokens and breakpoint contract.

**Step 3: Implement the shared density layer**

- add `--space-dashboard` and `--row-compact`;
- cap compact page titles at 44px;
- reduce shared section/card padding and heading gaps by 20–30% on desktop;
- retain at least 13px body/data text and 44px controls/rows;
- add 80rem, 64rem, and 48rem layout transitions without shrinking typography;
- keep current accessibility preference fallbacks.

**Step 4: Run GREEN**

```bash
pnpm --dir web exec vitest --run tests/visual-system-contract.test.ts tests/product-shell.test.tsx tests/layout-contract.test.tsx
pnpm --dir web run typecheck
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/app/globals.css web/components/ui/product-ui.tsx web/tests/visual-system-contract.test.ts web/tests/product-shell.test.tsx
git commit -m "style: establish MacBook Air density system"
```

---

### Task 2: Finish Fixture and API Today composition

**Files:**
- Modify: `web/components/today-page.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/tests/today-page.test.tsx`
- Modify: `web/tests/api-pages.test.tsx`
- Modify: `web/tests/home.test.tsx`
- Modify: `web/app/globals.css`

**Step 1: Write/complete failing Today hierarchy tests**

For Fixture and API variants assert a `Today decision workspace`, `Portfolio overview`, dense market
list, `Decision activity`, and closed `Provider diagnostics`. For API mode assert exact persisted
cutoff/provider facts and no Fixture fallback. The Fixture markup from commit `486e951` is the
starting point and must remain covered.

**Step 2: Run RED**

```bash
pnpm --dir web exec vitest --run tests/today-page.test.tsx tests/api-pages.test.tsx tests/home.test.tsx
```

Expected: API Today hierarchy assertions FAIL.

**Step 3: Implement API parity and Today density**

- preserve Portfolio-first Fixture markup from `486e951`;
- align API Today with the same semantic workspace using only existing persisted facts;
- show latest Research decisions where an Active Run is unavailable rather than inventing run data;
- limit visible Alert/Research records to three with routes to full history;
- put provider diagnostics and complete quote lineage in closed disclosures;
- keep TradingView labeled as external current-market context;
- apply desktop grid/list styles and responsive collapse.

**Step 4: Run GREEN**

```bash
pnpm --dir web exec vitest --run tests/today-page.test.tsx tests/api-pages.test.tsx tests/home.test.tsx tests/api-route-degradation.test.tsx tests/page-states.test.tsx
pnpm --dir web run typecheck
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/today-page.tsx web/components/live/api-pages.tsx web/app/globals.css web/tests/today-page.test.tsx web/tests/api-pages.test.tsx web/tests/home.test.tsx
git commit -m "style: fit Today decisions into the MacBook viewport"
```

---

### Task 3: Compact Watchlist and Research workflows

**Files:**
- Modify: `web/components/watchlist/watchlist-page.tsx`
- Modify: `web/components/watchlist/watchlist-api-controls.tsx`
- Modify: `web/components/research/research-directory-page.tsx`
- Modify: `web/components/research/research-page.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/tests/watchlist-page.test.tsx`
- Modify: `web/tests/research-directory-page.test.tsx`
- Modify: `web/tests/research-page.test.tsx`
- Modify: `web/tests/api-pages.test.tsx`
- Modify: `web/app/globals.css`

**Step 1: Write failing route-summary tests**

Assert each page has a classed `route-critical-summary` region containing its current status and
primary action. Assert Watchlist controls, thresholds, monitoring, and earnings summary are present;
assert Research symbol selection, latest conclusion, current market reference, evidence summary, and
decision-history summary are present. Assert full domain tables live in closed counted disclosures.

**Step 2: Run RED**

```bash
pnpm --dir web exec vitest --run tests/watchlist-page.test.tsx tests/research-directory-page.test.tsx tests/research-page.test.tsx tests/api-pages.test.tsx
```

Expected: FAIL on missing compact summary markup/classes.

**Step 3: Implement minimal markup and shared compact styles**

- use dense rows for symbols and monitoring configuration;
- keep controls adjacent to affected symbols/rules;
- lead Research with selector + conclusion + market reference;
- convert SEC, earnings, news, options, quality, and complete decision history to closed counted
  disclosures without removing tables or provenance;
- preserve all unavailable reasons and API/Fixture labels.

**Step 4: Run GREEN and typecheck**

```bash
pnpm --dir web exec vitest --run tests/watchlist-page.test.tsx tests/research-directory-page.test.tsx tests/research-page.test.tsx tests/api-pages.test.tsx tests/api-route-degradation.test.tsx
pnpm --dir web run typecheck
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/watchlist web/components/research web/components/live/api-pages.tsx web/app/globals.css web/tests
git commit -m "style: compact Watchlist and Research workflows"
```

---

### Task 4: Compact Run Trace and Portfolio evidence

**Files:**
- Modify: `web/components/trace/run-trace-page.tsx`
- Modify: `web/components/portfolio/portfolio-page.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/tests/run-trace-page.test.tsx`
- Modify: `web/tests/portfolio-page.test.tsx`
- Modify: `web/tests/api-pages.test.tsx`
- Modify: `web/app/globals.css`

**Step 1: Write failing critical-summary tests**

Assert Run Trace first viewport contains status/progress, node/tool activity, budgets, retry/degraded
state, and checkpoint. Assert Portfolio contains NAV/return/drawdown, cash, positions summary, risk
decisions summary, fills summary, and CashLedger summary. Assert complete events and accounting tables
remain in closed disclosures.

**Step 2: Run RED**

```bash
pnpm --dir web exec vitest --run tests/run-trace-page.test.tsx tests/portfolio-page.test.tsx tests/api-pages.test.tsx
```

Expected: FAIL on missing summary group/disclosure contracts.

**Step 3: Implement minimal layout changes**

- group operational facts into compact definition grids;
- keep progress and current checkpoint visually primary;
- keep NAV and accounting totals primary;
- summarize counts/status without replacing PaperFill, CashLedger, position, order, or risk evidence;
- disclose complete tables and event streams below the critical summary.

**Step 4: Run GREEN and typecheck**

```bash
pnpm --dir web exec vitest --run tests/run-trace-page.test.tsx tests/portfolio-page.test.tsx tests/api-pages.test.tsx
pnpm --dir web run typecheck
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/trace web/components/portfolio web/components/live/api-pages.tsx web/app/globals.css web/tests
git commit -m "style: compact run and portfolio evidence"
```

---

### Task 5: Compact Alerts, Weekly Review, and Eval/Admin

**Files:**
- Modify: `web/components/alerts/alerts-page.tsx`
- Modify: `web/components/learning/weekly-review-page.tsx`
- Modify: `web/components/eval/eval-page.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/tests/alerts-page.test.tsx`
- Modify: `web/tests/weekly-review-page.test.tsx`
- Modify: `web/tests/eval-page.test.tsx`
- Modify: `web/tests/api-pages.test.tsx`
- Modify: `web/app/globals.css`

**Step 1: Write failing critical-summary tests**

Assert Alerts exposes current filters/categories and actionable stream; Weekly Review exposes outcomes,
calibration, attribution, replay, and lesson summaries; Eval/Admin exposes result, version pins, gates,
runtime/provider status, and manual policy controls. Assert historical/raw detail is closed by default.

**Step 2: Run RED**

```bash
pnpm --dir web exec vitest --run tests/alerts-page.test.tsx tests/weekly-review-page.test.tsx tests/eval-page.test.tsx tests/api-pages.test.tsx
```

Expected: FAIL on missing dense summary contracts.

**Step 3: Implement route composition**

- reuse `route-critical-summary`, compact metrics, and dense rows;
- keep state names, policy safeguards, manual approval, 403 behavior, and deterministic facts intact;
- move only complete history/raw evidence below the primary viewport into disclosures.

**Step 4: Run GREEN and typecheck**

```bash
pnpm --dir web exec vitest --run tests/alerts-page.test.tsx tests/weekly-review-page.test.tsx tests/eval-page.test.tsx tests/api-pages.test.tsx
pnpm --dir web run typecheck
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/alerts web/components/learning web/components/eval web/components/live/api-pages.tsx web/app/globals.css web/tests
git commit -m "style: compact review and administration pages"
```

---

### Task 6: Verify all routes at MacBook Air dimensions

**Files:**
- Modify: `web/tests/e2e/product-shell.spec.ts`
- Modify: `web/tests/e2e/accessibility.spec.ts`
- Modify: `docs/progress.md`

**Step 1: Write failing geometry checks**

For `/`, `/watchlist`, `/research`, `/runs/latest`, `/portfolio`, `/alerts`, `/weekly-review`, and
`/eval`, use `1440×800` and assert the route's `route-critical-summary` or decision workspace bottom
is `<= 800`. At `1280×720`, assert no page-level horizontal overflow and all primary actions remain
visible. Keep mobile, dark, keyboard, and Axe assertions.

**Step 2: Run RED/measure**

```bash
pnpm --dir web exec playwright test tests/e2e/product-shell.spec.ts tests/e2e/accessibility.spec.ts --project=chromium
```

Expected: geometry failures identify routes requiring measured CSS tuning.

**Step 3: Tune only measured spacing/layout failures**

Adjust grid proportions, gaps, padding, and visible record limits. Do not lower text below 13px,
targets below 44px, or hide required facts.

**Step 4: Run final frontend and repository verification**

```bash
pnpm --dir web test
pnpm --dir web run typecheck
pnpm --dir web run build
pnpm --dir web exec playwright test tests/e2e/product-shell.spec.ts tests/e2e/accessibility.spec.ts --project=chromium
make verify
```

Expected: PASS.

**Step 5: Record and commit evidence**

Append commands, exit codes, counts, viewport results, and warnings to `docs/progress.md`, then:

```bash
git add web/tests/e2e/product-shell.spec.ts web/tests/e2e/accessibility.spec.ts docs/progress.md
git commit -m "test: verify MacBook Air dense interface"
```

Before claiming completion, invoke `@superpowers:verification-before-completion`, then use
`@superpowers:finishing-a-development-branch` for delivery choices.
