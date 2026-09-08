# Frontend Experience Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a calm, information-dense, responsive eight-page research and paper-trading interface without changing API contracts or evidence semantics.

**Architecture:** Keep the existing Next.js server-component routes and data boundaries. Introduce only the smallest shared client behavior needed for explicit responsive navigation, normalize the visual system in `globals.css`, and improve pages in dependency order from shell to core decision surfaces to operational surfaces. Every behavior is locked by Vitest or Playwright before implementation.

**Tech Stack:** Next.js 15, React 19, TypeScript, CSS/Tailwind import, Vitest, Testing Library, Playwright, axe-core.

---

Implementation authority: `docs/plans/2026-09-06-frontend-experience-closure-design.md` and Notion v0.2. Use `superpowers:executing-plans`, `superpowers:test-driven-development`, `superpowers:systematic-debugging` when a failure is unexpected, `apple-design` for interface judgment, and `superpowers:verification-before-completion` before any completion claim.

### Task 1: Explicit responsive application navigation

**Files:**
- Modify: `web/components/layout/app-shell.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tests/product-shell.test.tsx`
- Modify: `web/e2e/happy-path.spec.ts`

**Step 1: Write failing component tests**

Add tests that render `AppShell`, find a button named `Open navigation`, open it, verify all eight links remain available, then close it with the same control and with Escape. Verify `aria-expanded`, `aria-controls`, and the current-page label.

```tsx
const trigger = screen.getByRole('button', { name: 'Open navigation' })
expect(trigger).toHaveAttribute('aria-expanded', 'false')
fireEvent.click(trigger)
expect(trigger).toHaveAttribute('aria-expanded', 'true')
expect(screen.getByRole('link', { name: 'Weekly Review' })).toBeVisible()
fireEvent.keyDown(document, { key: 'Escape' })
expect(trigger).toHaveAttribute('aria-expanded', 'false')
```

**Step 2: Run the focused test and observe RED**

Run: `pnpm --dir web test --run tests/product-shell.test.tsx`
Expected: FAIL because no explicit navigation trigger or controlled menu exists.

**Step 3: Add the minimum accessible shell behavior**

In `AppShell`, add `navigationOpen` state, an `id="primary-navigation"` navigation container, a labelled toggle, Escape handling, close-on-link behavior, and a visible current-location label for compact layouts. Keep the existing eight routes and theme persistence unchanged.

```tsx
const [navigationOpen, setNavigationOpen] = useState(false)

useEffect(() => {
  function dismiss(event: KeyboardEvent) {
    if (event.key === 'Escape') setNavigationOpen(false)
  }
  document.addEventListener('keydown', dismiss)
  return () => document.removeEventListener('keydown', dismiss)
}, [])
```

Use CSS breakpoints to keep the full nav visible where it fits and expose the trigger below that point. The compact menu must be an explicit surface, not a horizontally clipped row.

**Step 4: Run focused tests and observe GREEN**

Run: `pnpm --dir web test --run tests/product-shell.test.tsx tests/layout-contract.test.tsx`
Expected: PASS.

**Step 5: Add failing browser assertions**

Extend `happy-path.spec.ts` for the mobile project: open the menu, visit every destination, verify Escape dismissal and visible focus, then assert `scrollWidth <= innerWidth` at 393 px. Add a temporary 320 px viewport and a 200% zoom-equivalent viewport check.

**Step 6: Run the browser test and observe RED, then GREEN**

Run: `pnpm --dir web exec playwright test e2e/happy-path.spec.ts --project=mobile-chrome`
Expected before CSS completion: FAIL on navigation/overflow.
Expected after minimal CSS completion: PASS.

**Step 7: Commit**

```bash
git add web/components/layout/app-shell.tsx web/app/globals.css web/tests/product-shell.test.tsx web/e2e/happy-path.spec.ts
git commit -m "feat(web): make product navigation explicitly responsive"
```

### Task 2: Normalize typography, spacing, and surfaces

**Files:**
- Modify: `web/app/globals.css`
- Modify: `web/tests/layout-contract.test.tsx`
- Create: `web/tests/visual-system-contract.test.ts`

**Step 1: Write the failing token contract**

Read `globals.css` in the test and assert the approved primitives exist and obsolete visual duplication is absent.

```ts
expect(css).toContain('--space-page:')
expect(css).toContain('--radius-section:')
expect(css).toContain('--surface-section:')
expect(css).not.toMatch(/body \{[^}]*radial-gradient/s)
expect(css).not.toMatch(/\.primary-nav::?-webkit-scrollbar[^}]*display:\s*none/s)
```

**Step 2: Run the focused test and observe RED**

Run: `pnpm --dir web test --run tests/visual-system-contract.test.ts`
Expected: FAIL because the normalized tokens do not exist and the ambient gradients remain.

**Step 3: Implement the minimum visual normalization**

In `globals.css`:

- add shared page/section/row/control spacing and radius tokens;
- use a quiet canvas in light and dark themes;
- reduce heading scale and decorative letter spacing;
- collapse surface definitions into canvas, section, and interactive levels;
- remove duplicated heavy shadows and nested-card treatment;
- preserve signal, positive, and negative colors for meaning;
- retain reduced-motion, reduced-transparency, and increased-contrast behavior.

Do not rename page-level classes yet; this task changes only the shared visual grammar.

**Step 4: Run focused tests, typecheck, and lint**

Run: `pnpm --dir web test --run tests/visual-system-contract.test.ts tests/layout-contract.test.tsx`
Run: `pnpm --dir web typecheck`
Run: `pnpm --dir web lint`
Expected: all PASS.

**Step 5: Commit**

```bash
git add web/app/globals.css web/tests/layout-contract.test.tsx web/tests/visual-system-contract.test.ts
git commit -m "style(web): normalize the product visual system"
```

### Task 3: Prioritize Today information and shared state anatomy

**Files:**
- Modify: `web/components/today-page.tsx`
- Modify: `web/components/states/state-boundary.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tests/today-page.test.tsx`
- Modify: `web/tests/page-states.test.tsx`
- Modify: `web/e2e/api-failure-matrix.spec.ts`

**Step 1: Write failing Today hierarchy tests**

Assert DOM order: compact identity/provenance, degraded summary, current-market reference, portfolio summary, then attention items. Assert detailed unavailable domains are collapsed and reachable by a labelled disclosure.

```tsx
const main = screen.getByRole('main')
const degraded = screen.getByRole('button', { name: /unavailable facts/i })
expect(degraded).toHaveAttribute('aria-expanded', 'false')
expect(main.compareDocumentPosition(screen.getByRole('region', { name: /current market/i })))
  .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
```

Add shared-state tests requiring consequence, timestamp when known, retry/next action when applicable, and no Fixture substitution in API-mode failure.

**Step 2: Run focused tests and observe RED**

Run: `pnpm --dir web test --run tests/today-page.test.tsx tests/page-states.test.tsx`
Expected: FAIL on hierarchy/disclosure anatomy.

**Step 3: Implement the minimal hierarchy and state changes**

- Keep the Today heading compact.
- Keep time/environment provenance visible without a large banner.
- Render one concise degraded/failure summary; move domain lists into `<details>` or an equivalent accessible disclosure.
- Keep TradingView-labelled current-market context separate from persisted quote evidence.
- Keep paper portfolio facts timestamped and never synthesize missing API data.

**Step 4: Run focused and failure/recovery tests**

Run: `pnpm --dir web test --run tests/today-page.test.tsx tests/page-states.test.tsx tests/home.test.tsx tests/api-route-degradation.test.tsx`
Run: `WEB_DATA_MODE=api API_BASE_URL=http://127.0.0.1:8000 pnpm --dir web exec playwright test e2e/api-failure-matrix.spec.ts --project=desktop-chrome`
Expected: PASS with Failure/Degraded displayed and no Fixture fallback.

**Step 5: Commit**

```bash
git add web/components/today-page.tsx web/components/states/state-boundary.tsx web/app/globals.css web/tests/today-page.test.tsx web/tests/page-states.test.tsx web/e2e/api-failure-matrix.spec.ts
git commit -m "feat(web): prioritize Today decision information"
```

### Task 4: Recompose Watchlist and Stock Research

**Files:**
- Modify: `web/components/watchlist/watchlist-page.tsx`
- Modify: `web/components/watchlist/watchlist-api-controls.tsx`
- Modify: `web/components/research/research-page.tsx`
- Modify: `web/components/market/tradingview-ticker-list.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tests/watchlist-route.test.tsx`
- Modify: `web/tests/research-workflow-pages.test.tsx`
- Modify: `web/tests/tradingview-ticker-list.test.tsx`

**Step 1: Write failing Watchlist tests**

Require a labelled ranked list whose rows expose symbol/company, compact trend, price, change, quality, and persisted provenance without turning each row into a standalone card. Require one labelled configuration region containing add/remove, daily research, intraday monitoring, threshold, and earnings settings.

**Step 2: Write failing Research tests**

Require initial reading order: identity, opinion/confidence, thesis, freshness, then separate current-market reference and PIT evidence. Require labelled groups for fundamentals, earnings, news, options, analyst targets, evidence gaps, and decision history.

**Step 3: Run tests and observe RED**

Run: `pnpm --dir web test --run tests/watchlist-route.test.tsx tests/research-workflow-pages.test.tsx tests/tradingview-ticker-list.test.tsx`
Expected: FAIL on new labelled regions/order.

**Step 4: Implement the minimum structural changes**

Use semantic list/table structures and section headings. Preserve existing values, API actions, TradingView disclaimer, and PIT timestamps. On mobile, prioritize identity/price/change/state and allow secondary provenance to wrap or disclose.

**Step 5: Run focused and related tests**

Run: `pnpm --dir web test --run tests/watchlist-route.test.tsx tests/watchlist-actions.test.ts tests/watchlist-api.test.ts tests/research-workflow-pages.test.tsx tests/tradingview-ticker-list.test.tsx`
Expected: PASS.

**Step 6: Commit**

```bash
git add web/components/watchlist web/components/research web/components/market/tradingview-ticker-list.tsx web/app/globals.css web/tests
git commit -m "feat(web): improve watchlist and research scanning"
```

### Task 5: Recompose Portfolio and operational/review pages

**Files:**
- Modify: `web/components/portfolio/portfolio-page.tsx`
- Modify: `web/components/portfolio/performance-chart.tsx`
- Modify: `web/components/trace/run-trace-page.tsx`
- Modify: `web/components/alerts/alerts-page.tsx`
- Modify: `web/components/learning/weekly-review-page.tsx`
- Modify: `web/components/eval/eval-admin-page.tsx`
- Modify: `web/components/live/api-pages.tsx`
- Modify: `web/app/globals.css`
- Modify: `web/tests/review-and-portfolio-pages.test.tsx`
- Modify: `web/tests/research-workflow-pages.test.tsx`
- Modify: `web/tests/api-pages.test.tsx`
- Modify: `web/tests/eval-report.test.ts`

**Step 1: Write failing page-priority tests**

- Portfolio: NAV, return, drawdown, cash, and as-of time precede the chart; positions, risk decisions, fills, and cash ledger remain explicit.
- Run Trace: status, elapsed time, current step, retry/degradation/checkpoint, and cutoff precede the chronological event list.
- Alerts: severity/category/scope/trigger/time/acknowledgement are present, and empty differs from failure.
- Weekly Review: outcome/benchmarks/thesis hits/calibration precede attribution, replay, and lessons.
- Eval/Admin: report status/version/regressions/provider health/policy state are grouped as operational evidence.

**Step 2: Run focused tests and observe RED**

Run: `pnpm --dir web test --run tests/review-and-portfolio-pages.test.tsx tests/research-workflow-pages.test.tsx tests/api-pages.test.tsx tests/eval-report.test.ts`
Expected: FAIL on the new order and labelled-region expectations.

**Step 3: Implement the minimum semantic recomposition**

Reorder existing facts and replace nested card mosaics with section/list/table groupings. Preserve Decimal-formatted money strings, aware timestamps, persisted provenance, manual policy approval, rollback, and the paper-trading-only boundary.

**Step 4: Run focused and related tests**

Run: `pnpm --dir web test --run tests/review-and-portfolio-pages.test.tsx tests/research-workflow-pages.test.tsx tests/api-pages.test.tsx tests/eval-report.test.ts tests/api-route-degradation.test.tsx`
Expected: PASS.

**Step 5: Commit**

```bash
git add web/components/portfolio web/components/trace web/components/alerts web/components/learning web/components/eval web/components/live/api-pages.tsx web/app/globals.css web/tests
git commit -m "feat(web): clarify portfolio and review workflows"
```

### Task 6: Complete cross-page browser and accessibility gates

**Files:**
- Modify: `web/e2e/accessibility.spec.ts`
- Modify: `web/e2e/happy-path.spec.ts`
- Modify: `web/e2e/api-failure-matrix.spec.ts`
- Modify: `web/playwright.config.ts`
- Modify: `docs/progress.md`

**Step 1: Add failing browser-matrix assertions**

For all eight pages, cover:

- 320, 393, 768, 1120, and 1440 CSS-pixel widths;
- no document-level horizontal overflow;
- one visible `h1`, reachable navigation, visible focus, and sticky-header-safe focus placement;
- serious/critical axe scan with owned DOM only;
- light/dark and reduced-motion behavior;
- API-mode loading, empty, stale, degraded, failure, recovery, and success where contracts support them.

Do not treat an unavailable provider domain as a failed page and do not substitute Fixture data in API mode.

**Step 2: Run new tests and observe RED**

Run: `pnpm --dir web exec playwright test e2e/accessibility.spec.ts e2e/happy-path.spec.ts --project=desktop-chrome --project=mobile-chrome`
Expected: FAIL on any remaining overflow, focus, or hierarchy defect.

**Step 3: Make only the CSS/markup corrections proven by failures**

Use `superpowers:systematic-debugging` for unexpected failures. Prefer CSS and semantic markup; do not add JavaScript solely to mask layout defects.

**Step 4: Run the complete frontend gate**

Run: `pnpm --dir web typecheck`
Run: `pnpm --dir web lint`
Run: `pnpm --dir web test --run`
Run: `pnpm --dir web build`
Run: `pnpm --dir web exec playwright test --project=desktop-chrome --project=mobile-chrome`
Expected: all PASS; credential-gated live tests may skip only when the gate condition is explicitly reported.

**Step 5: Run repository verification and record evidence**

Run: `make verify`
Expected: exit 0.

Append to `docs/progress.md`:

- each RED and GREEN command;
- actual exit code;
- Vitest/Playwright/backend pass/fail/skip counts;
- build and `make verify` result;
- screenshot/report paths;
- unresolved risks, including any third-party TradingView frame excluded from owned-DOM axe scanning.

**Step 6: Verify scope and commit**

Run: `git diff --check`
Run: `git status --short`
Inspect the final diff for accidental live brokerage, credential, provider, schema, naive datetime, floating-point money, or Fixture fallback changes.

```bash
git add web docs/progress.md
git commit -m "test(web): close the frontend experience gate"
```

### Task 7: Pre-PR professional review

**Files:**
- Review only: all changes since `1ac7b30`

**Step 1: Use verification-before-completion**

Read `superpowers:verification-before-completion` and rerun any command whose evidence is stale or incomplete.

**Step 2: Review the branch diff**

Run: `git diff --stat 1ac7b30...HEAD`
Run: `git diff --check 1ac7b30...HEAD`
Run: `git log --oneline --decorate 1ac7b30..HEAD`

Review for accessibility regression, contract drift, duplicated components, unsupported API data, hidden Fixture fallback, current-market/PIT ambiguity, and unsafe paper/live language.

**Step 3: Resolve findings through TDD**

For every actionable finding: write a failing regression test, observe RED, implement the minimum fix, rerun the focused and related suites, and commit separately.

**Step 4: Stop for user review**

Report verification evidence and remaining risks. Do not push, open a PR, merge, or update external trackers without the user's next authorization.
