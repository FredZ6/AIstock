# Apple Finance UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the loose editorial-terminal presentation with a calm, compact Apple Finance-inspired interface that preserves every existing data-truth and paper-only boundary.

**Architecture:** Keep the existing Next.js server/data boundaries and React component ownership. Establish the visual language through shared CSS tokens and a small set of existing primitives (`AppShell`, `PageHeading`, `StateBoundary`, surfaces, metrics, tables, and quote rows), then migrate pages onto those primitives without introducing a UI framework or changing API contracts.

**Tech Stack:** Next.js 15, React 19, TypeScript, CSS, Vitest/Testing Library, Playwright, Axe, Python verification wrapper.

**Required skills:** `@apple-design`, `@superpowers:test-driven-development`, `@playwright`, and `@superpowers:verification-before-completion`.

---

### Task 1: Lock the Apple Finance visual contract

**Files:**
- Modify: `web/tests/visual-system-contract.test.ts`
- Modify: `web/app/globals.css`

**Step 1: Replace the obsolete editorial-terminal assertions with failing Apple Finance assertions**

Assert the shared stylesheet provides:

```ts
expect(css).toContain('--radius-section: 1.25rem;')
expect(css).toContain('--radius-control: 0.75rem;')
expect(css).toContain('--material-chrome:')
expect(css).toContain('--shadow-elevated:')
expect(css).toMatch(/\.app-chrome\s*\{[^}]*backdrop-filter:\s*blur\(/s)
expect(css).toMatch(/\.surface-card\s*\{[^}]*border-radius:\s*var\(--radius-section\)/s)
expect(css).toMatch(/@media \(prefers-reduced-transparency: reduce\)/)
expect(css).toMatch(/@media \(prefers-contrast: more\)/)
expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/)
expect(css).toContain('font-optical-sizing: auto;')
```

Keep the existing numeric alignment, state-not-by-color-alone, and TradingView containment checks.

**Step 2: Run the contract and confirm RED**

Run:

```bash
pnpm --dir web exec vitest --run tests/visual-system-contract.test.ts
```

Expected: FAIL on the larger radii, material tokens, translucent chrome, and accessibility preference queries.

**Step 3: Implement the minimal shared token and material layer**

In `web/app/globals.css`:

- replace the terminal radii with 20px section and 12px control radii;
- add light/dark material, shadow, focus, and motion tokens;
- use system typography with optical sizing and size-dependent tracking;
- introduce one subtle canvas wash and one floating chrome material;
- keep reading surfaces sufficiently opaque;
- add reduced-motion, reduced-transparency, and increased-contrast fallbacks.

Do not change page-specific layout in this task.

**Step 4: Run the contract and existing layout tests**

Run:

```bash
pnpm --dir web exec vitest --run tests/visual-system-contract.test.ts tests/layout-contract.test.tsx
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/app/globals.css web/tests/visual-system-contract.test.ts
git commit -m "style: establish Apple Finance visual tokens"
```

---

### Task 2: Make the shared shell compact, translucent, and predictable

**Files:**
- Modify: `web/components/layout/app-shell.tsx`
- Modify: `web/components/ui/product-ui.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tests/product-shell.test.tsx`
- Modify: `web/tests/layout-contract.test.tsx`

**Step 1: Write failing shell and heading tests**

Add assertions that:

```ts
expect(screen.getByRole('banner')).toHaveClass('app-chrome')
expect(screen.getByRole('navigation', { name: 'Primary' })).toHaveAttribute('data-open', 'false')
expect(screen.getByRole('link', { name: 'Today' })).toHaveAttribute('aria-current', 'page')
expect(screen.getByLabelText('Snapshot time')).toBeInTheDocument()
expect(screen.getByText('API Mode', { exact: true })).toHaveClass('runtime-badge')
```

Add a markup contract for a compact page-heading context cluster rather than a large hero region.

**Step 2: Run and confirm RED**

Run:

```bash
pnpm --dir web exec vitest --run tests/product-shell.test.tsx tests/layout-contract.test.tsx
```

Expected: FAIL on the missing runtime badge/context markup or class contract.

**Step 3: Implement the shell and heading changes**

- Keep the existing navigation destinations and semantics.
- Keep mobile Escape dismissal and current-page behavior.
- Render product identity, navigation, and theme control in one floating desktop bar.
- Make mobile navigation an anchored sheet from the navigation control.
- Add a reusable compact runtime badge presentation to `FixtureNotice` and API-mode headings.
- Preserve skip-link and focus behavior.

Use CSS press feedback on pointer-down/`:active`; do not add fixed-duration decorative motion or an animation dependency.

**Step 4: Run shell, theme, and accessibility-facing unit tests**

Run:

```bash
pnpm --dir web exec vitest --run tests/product-shell.test.tsx tests/layout-contract.test.tsx tests/page-states.test.tsx
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/layout/app-shell.tsx web/components/ui/product-ui.tsx web/app/globals.css web/tests/product-shell.test.tsx web/tests/layout-contract.test.tsx
git commit -m "style: refine the shared product shell"
```

---

### Task 3: Redesign availability and feedback surfaces without weakening truthfulness

**Files:**
- Modify: `web/components/states/state-boundary.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tests/page-states.test.tsx`
- Modify: `web/tests/availability.test.ts`

**Step 1: Write the failing compact-disclosure test**

Render a degraded state containing `UNCONFIGURED`, `UNSUPPORTED`, and `FAILURE` facts and assert:

```ts
const summary = screen.getByText('3 unavailable facts')
expect(summary.closest('details')).toHaveClass('state-details')
expect(screen.getByText('No approved read-only producer exists for options.')).toBeInTheDocument()
expect(screen.getByRole('link', { name: 'Review runtime configuration' })).toHaveAttribute('href', '/eval')
expect(screen.queryByRole('link', { name: /options/i })).not.toBeInTheDocument()
```

Add a class/markup assertion for a structured availability row instead of chip-like tags.

**Step 2: Run and confirm RED**

Run:

```bash
pnpm --dir web exec vitest --run tests/page-states.test.tsx tests/availability.test.ts
```

Expected: FAIL on the new structured-row presentation contract.

**Step 3: Implement the feedback surface**

- Keep `role=status`/`role=alert`, canonical state names, exact reason, and action semantics.
- Make the collapsed state one compact row.
- Render expanded facts as aligned rows with state, label, reason, and optional action.
- Use tonal severity and an icon/dot plus text; never rely on color alone.
- Apply the same surface rules to loading, empty, stale, degraded, partial, failure, and success states.

**Step 4: Run focused and route degradation tests**

Run:

```bash
pnpm --dir web exec vitest --run tests/page-states.test.tsx tests/availability.test.ts tests/api-route-degradation.test.tsx
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/states/state-boundary.tsx web/app/globals.css web/tests/page-states.test.tsx web/tests/availability.test.ts
git commit -m "style: clarify availability feedback surfaces"
```

---

### Task 4: Recompose Today around portfolio value and compact market context

**Files:**
- Modify: `web/components/today-page.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/components/portfolio/performance-chart.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tests/today-page.test.tsx`
- Modify: `web/tests/home.test.tsx`
- Modify: `web/tests/api-pages.test.tsx`

**Step 1: Write failing hierarchy tests**

For Fixture and API Today variants, assert the first overview region contains:

```ts
expect(screen.getByRole('region', { name: 'Portfolio overview' })).toHaveClass('portfolio-overview')
expect(screen.getByText('Net asset value')).toBeInTheDocument()
expect(screen.getByText('Day return')).toBeInTheDocument()
expect(screen.getByRole('region', { name: 'Market regime' })).toHaveClass('market-regime-compact')
expect(screen.getByRole('list', { name: 'Watchlist signals' })).toHaveClass('market-list')
```

Keep assertions that Fixture labels, API facts, persisted cutoff, and unavailable domains remain visible.

**Step 2: Run and confirm RED**

Run:

```bash
pnpm --dir web exec vitest --run tests/today-page.test.tsx tests/home.test.tsx tests/api-pages.test.tsx
```

Expected: FAIL on the new semantic regions/classes.

**Step 3: Implement the new Today hierarchy**

- Put portfolio overview first and make NAV the strongest value.
- Place compact Market Regime beside or immediately below it without equal-height empty space.
- Convert Watchlist cards into dense market rows; keep symbol, price, change, opinion/action, and quality.
- Keep the existing performance chart and truthful synthetic/persisted labels.
- Put alerts and active research above provider diagnostics.
- Use CSS grid that collapses before either column becomes sparse.

Do not change calculations, formatting precision, provider identity, or routing.

**Step 4: Run Today tests and production typecheck**

Run:

```bash
pnpm --dir web exec vitest --run tests/today-page.test.tsx tests/home.test.tsx tests/api-pages.test.tsx
pnpm --dir web run typecheck
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/today-page.tsx web/components/live/api-pages.tsx web/components/portfolio/performance-chart.tsx web/app/globals.css web/tests/today-page.test.tsx web/tests/home.test.tsx web/tests/api-pages.test.tsx
git commit -m "style: prioritize decision facts on Today"
```

---

### Task 5: Normalize dense workflow pages onto the shared system

**Files:**
- Modify: `web/components/watchlist/watchlist-page.tsx`
- Modify: `web/components/watchlist/watchlist-api-controls.tsx`
- Modify: `web/components/research/research-directory-page.tsx`
- Modify: `web/components/research/research-page.tsx`
- Modify: `web/components/trace/run-trace-page.tsx`
- Modify: `web/components/portfolio/portfolio-page.tsx`
- Modify: `web/components/alerts/alerts-page.tsx`
- Modify: `web/components/learning/weekly-review-page.tsx`
- Modify: `web/components/eval/eval-admin-page.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tests/watchlist-route.test.tsx`
- Modify: `web/tests/research-workflow-pages.test.tsx`
- Modify: `web/tests/review-and-portfolio-pages.test.tsx`

**Step 1: Add failing shared-surface assertions to representative routes**

Assert Watchlist uses `market-list`, Research evidence retains accessible tables/disclosures,
Portfolio uses one `portfolio-overview`, and Weekly Review/Eval keep their evidence table labels.
Add an assertion that destructive Watchlist removal remains explicitly confirmed.

**Step 2: Run and confirm RED**

Run:

```bash
pnpm --dir web exec vitest --run tests/watchlist-route.test.tsx tests/research-workflow-pages.test.tsx tests/review-and-portfolio-pages.test.tsx
```

Expected: FAIL only on the new shared presentation contract, not on data behavior.

**Step 3: Apply the shared layout deliberately**

- Use compact grouped surfaces for summaries and controls.
- Keep evidence-heavy content in tables/disclosures with sticky headers where useful.
- Align primary actions with the object they affect.
- Eliminate page-specific border/radius/shadow values that duplicate global tokens.
- Preserve every accessible name, confirmation, empty state, and data-quality label.

**Step 4: Run the complete frontend suite**

Run:

```bash
pnpm --dir web exec vitest --run
pnpm --dir web run typecheck
pnpm --dir web run lint
pnpm --dir web run build
```

Expected: all frontend tests, typecheck, lint, and production build PASS.

**Step 5: Commit**

```bash
git add web/components web/app/globals.css web/tests
git commit -m "style: normalize research workflow pages"
```

---

### Task 6: Verify desktop, mobile, dark mode, and accessibility in a real browser

**Files:**
- Modify: `web/e2e/api-runtime.spec.ts`
- Modify: `web/e2e/fixture-smoke.spec.ts` if present; otherwise use the existing fixture browser spec
- Modify: `web/app/globals.css` only for defects reproduced by the browser matrix

**Step 1: Add the failing browser expectations**

Using the existing desktop/mobile projects, assert:

```ts
await expect(page.locator('.app-chrome')).toBeVisible()
await expect(page.getByRole('region', { name: 'Portfolio overview' })).toBeVisible()
expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
```

Then:

- keyboard-open and close mobile navigation;
- toggle dark mode and reload to prove persistence;
- emulate reduced motion and verify no transform displacement is applied;
- run Axe with WCAG A/AA tags and require zero serious/critical violations;
- capture full-page desktop and mobile screenshots under `output/playwright/apple-finance-ui/`.

**Step 2: Run and confirm RED**

Run the repository's existing browser command for Fixture mode first, then the managed API matrix.
Expected: initial failure on new layout/theme/reduced-motion assertions or a visually reproduced defect.

**Step 3: Fix only reproduced defects**

Adjust shared tokens or components. Do not add browser-test-only selectors or hide accessibility
violations.

**Step 4: Rerun the full browser matrix**

Run:

```bash
RUN_API_BROWSER=1 PYTHONPATH=backend/src UV_CACHE_DIR=.uv-cache uv run pytest backend/tests/integration/api/test_browser_runtime.py -q
```

Also run the existing Fixture Playwright command discovered in `scripts/verify.sh`.
Expected: PASS for desktop and mobile, zero serious/critical Axe violations, no horizontal overflow.

**Step 5: Commit**

```bash
git add web/e2e web/app/globals.css
git commit -m "test: cover Apple Finance responsive behavior"
```

---

### Task 7: Record evidence and run the final repository gate

**Files:**
- Modify: `docs/progress.md`

**Step 1: Add the delivery record**

Record:

- the approved Apple Finance design decisions;
- each RED/GREEN command and actual exit code;
- frontend test counts;
- browser projects, viewport sizes, theme/preference variants, and Axe result;
- production build result;
- any deliberately deferred visual debt.

**Step 2: Run the final fresh gate**

Run:

```bash
make verify
git diff --check
git status --short
```

Expected: `make verify` and `git diff --check` exit 0; status contains only the intended progress edit.

**Step 3: Commit the evidence**

```bash
git add docs/progress.md
git commit -m "docs: record Apple Finance UI verification"
```

**Step 4: Review the complete branch**

Review `git diff <merge-base>...HEAD`, confirm no API/data behavior changed, and verify the worktree is
clean before push or PR creation.

