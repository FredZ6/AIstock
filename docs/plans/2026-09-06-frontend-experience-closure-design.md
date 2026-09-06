# Frontend Experience Closure Design

Date: 2026-09-06  
Status: Approved  
Authority: Notion v0.2, repository safety constraints, and the user-approved progressive system-closure approach (方案 C)

## Objective

Make the existing research and paper-trading interface faster to scan, easier to navigate, and reliable across desktop and mobile without changing backend contracts or weakening the distinction between persisted evidence, external current-market context, and unavailable data.

The experience is desktop-research-first while remaining fully usable on mobile. The interface should feel calm and precise in the Apple design tradition: strong hierarchy, restrained materials, predictable spacing, and controls that reveal themselves through placement and state rather than decoration.

## Baseline findings

- Eight primary destinations compete in one horizontal navigation row. At narrower desktop widths and zoomed layouts, the hidden scrollbar makes destinations discoverable only by accident.
- Large page titles, generous outer spacing, repeated rounded containers, and blue/purple ambient gradients consume attention that should belong to research facts and exceptions.
- The page family has several parallel surface patterns (`surface-card`, `terminal-section`, hero panels, rails, performance panels) with inconsistent spacing and visual weight.
- Tables remain useful on desktop but often rely on wide minimum widths. Mobile layouts need explicit disclosure or priority-column treatment rather than generic horizontal overflow.
- Today has the right evidence boundaries, but its first viewport should prioritize market movement, portfolio state, risk, and actionable gaps over explanatory chrome.
- Loading, empty, stale, degraded, failure, and success states exist, but their prominence is not consistently proportional to user actionability.
- Current-market TradingView data and PIT-bounded persisted facts must remain visually and semantically distinct.

## Chosen approach

Use progressive system closure rather than a one-shot redesign:

1. Normalize the application shell, navigation, spacing, typography, and surface hierarchy.
2. Improve Today as the reference implementation for information priority.
3. Apply the same primitives to Watchlist and Stock Research.
4. Apply them to Portfolio, Run Trace, Alerts, Weekly Review, and Eval/Admin.
5. Finish with cross-page accessibility, responsive, state, and regression verification.

Existing API contracts, data-fetching behavior, paper-trading boundaries, and evidence semantics stay unchanged unless a failing test proves a presentation contract needs an explicit extension.

## Application shell

### Desktop

- Keep the brand compact and persistent.
- Replace the fragile eight-item single row with a clearly discoverable navigation system that fits the available width. Primary research destinations stay visible; operational and review destinations may be grouped behind an explicitly labelled control.
- Keep theme switching reachable with a minimum 44-by-44-point target.
- Use a restrained translucent header only where contrast remains sufficient; reduced-transparency mode must use an opaque surface.

### Mobile and zoomed layouts

- Expose an explicit navigation trigger and current location. Do not rely on hidden horizontal scrolling.
- Provide a focus-managed menu with Escape dismissal, visible focus, and correct `aria-expanded`/`aria-controls` semantics.
- Preserve direct access to every destination and the theme control.
- Prevent horizontal page overflow at 320 CSS pixels and at 200% browser zoom.

## Visual system

- Use the system font stack and tabular numerals for market, money, and time values.
- Establish a small tokenized spacing scale and apply it consistently to page gutters, section gaps, headings, rows, and controls.
- Reduce ambient gradients and large decorative empty areas. Color communicates current selection, status, gain/loss, and risk—not decoration.
- Use three surface levels only: canvas, grouped section, and interactive/selected element.
- Reduce corner-radius variety. Large sections use a moderate radius; nested rows and controls use smaller radii; data tables and lists should not become a mosaic of independent cards.
- Preserve light and dark themes with WCAG-compliant contrast. Respect reduced motion, transparency, and increased contrast preferences.

## Information architecture by page

### Today

The first viewport shows, in order:

1. Compact page identity, decision time, and environment provenance.
2. A concise degraded/failure summary only when needed, with details collapsed behind a labelled disclosure.
3. Current-market reference ranked for scanning.
4. Paper portfolio summary and its latest persisted timestamp.
5. Decision/risk attention items.

Explanatory copy and detailed lineage remain available below the primary facts. External current-market data must continue to state that it is not decision-time evidence.

### Watchlist

- Present the quote list as a dense, accessible ranked list with symbol/company identity, compact trend, price, change, quality, and persistence provenance.
- Keep add/remove, daily research, intraday monitoring, threshold, and earnings controls in one coherent configuration region.
- On mobile, preserve symbol, price, change, and state first; disclose secondary provider and timestamp detail without losing it.

### Stock Research

- Lead with symbol identity, latest opinion, confidence, thesis, and freshness.
- Keep current TradingView reference separate from PIT-bounded research evidence.
- Group fundamentals, earnings, news, options, analyst targets, evidence, and decision history by research question rather than as equally weighted cards.
- Make lineage and gaps easy to inspect without overwhelming the initial reading path.

### Portfolio

- Lead with NAV, daily return, drawdown, cash, and as-of time.
- Keep the performance chart as the dominant analytical surface.
- Present positions, risk decisions/rejections, paper fills, and cash ledger as evidence-oriented tables or lists with clear empty and unavailable states.
- Never imply live brokerage or executable real-money actions.

### Run Trace

- Show run status, elapsed time, current step, retry/degradation/checkpoint state, and data cutoff before verbose event detail.
- Use a chronological step/timeline model for nodes and tool calls.
- Keep prompt/model/policy pins and token/cost facts inspectable and auditable.

### Alerts

- Prioritize severity, category, symbol/portfolio scope, trigger, time, and acknowledgement state.
- Keep price, volume, options, earnings, news, target-price, provider, and portfolio-risk categories distinct.
- Failure to load alerts must not be confused with an empty alert queue.

### Weekly Review

- Lead with portfolio outcome, benchmark comparison, thesis hit/miss results, and confidence calibration.
- Keep attribution, evidence gaps, PIT replay, and candidate lesson/policy promotion controls subordinate to the review outcome.
- Preserve manual approval, audit, and rollback semantics.

### Eval & Admin

- Treat this as an operational workspace, not a consumer dashboard.
- Prioritize evaluation status, dataset/version pins, regressions, provider health, and policy approval state.
- Keep destructive or privileged actions visually separated and explicitly confirmed.

## State model

Shared states keep a consistent anatomy: state label, concise consequence, as-of time, next action, and optional technical detail.

- Loading: reserve layout and announce progress without indefinite shimmer.
- Empty: confirm a successful read with zero records and provide the next valid action.
- Stale: keep facts visible, label their timestamp and stale reason.
- Degraded: keep available facts visible; summarize unavailable domains once and disclose detail.
- Failure: show what could not be loaded, a retry action when safe, and no fixture substitution in API mode.
- Success: avoid celebratory chrome; show the persisted result and provenance.

## Interaction and accessibility

- All interactive targets are at least 44 CSS pixels in the primary mobile flow.
- Keyboard order follows visual order; focus is never hidden by the sticky header.
- Icons supplement accessible names and never carry meaning alone.
- Status is conveyed by text and shape in addition to color.
- Tables retain captions or labelled regions and appropriate row/column headers.
- Dynamic updates use restrained live-region announcements.
- Animations communicate continuity only, stay brief, and are removed under `prefers-reduced-motion`.

## Verification strategy

Every behavior change follows TDD: add or strengthen the failing component/contract/E2E assertion, observe the expected failure, implement the minimum change, and rerun the focused suite.

Required final evidence:

- Vitest, TypeScript, ESLint, and Next.js production build.
- Playwright desktop and mobile routes for all eight destinations.
- 320 px, 768 px, 1120 px, and 1440 px layout checks plus 200% zoom.
- Keyboard navigation, focus visibility, menu dismissal, and automated serious accessibility violation scan.
- Loading, empty, stale, degraded, failure, recovery, and success coverage in Fixture and API modes where applicable.
- Light/dark, reduced-motion, reduced-transparency, and increased-contrast checks.
- `make verify` with command, exit-code, pass/fail/skip counts recorded in `docs/progress.md`.

## Non-goals

- No backend schema or API redesign.
- No new provider, agent, MCP server, live brokerage, real-money trading path, credential field, or execution switch.
- No replacement of PIT-bounded data with TradingView or other current-market data.
- No fabricated values, provider availability, test result, or performance claim.
- No restoration or deletion of the stashed historical `output/` artifacts during implementation; that decision remains separate.

## Approval

The user approved方案 C on 2026-09-06: progressive system closure, desktop research efficiency first, with complete mobile usability and Apple-inspired restraint.
