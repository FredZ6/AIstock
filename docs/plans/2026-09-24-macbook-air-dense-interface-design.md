# MacBook Air dense interface design

## Target device and viewport

The reference device is the user's MacBook Air M2 (`Mac14,2`) with a 13.6-inch display. Browser
verification uses a conservative `1440×800` CSS-pixel viewport to represent a full-screen browser
after browser chrome. A `1280×720` viewport is the safety regression. Narrow split-screen and mobile
contexts may scroll and must collapse before text or controls become cramped.

## Outcome

Every primary route must expose all decision-critical summaries, current state, and primary actions
inside the first `1440×800` viewport:

- Today: Portfolio, Market Regime, Watchlist, Alerts, and Research activity.
- Watchlist: configured symbols, controls, monitoring state, thresholds, and upcoming earnings.
- Research: authoritative symbol selection, latest conclusion, market reference, core evidence, and
  decision history summary.
- Run Trace: status, progress, node/tool activity, budgets, retries, degradation, and checkpoint.
- Portfolio: NAV, return, drawdown, cash, positions, risk decisions, fills, and ledger summary.
- Alerts: severity/category filters and the current actionable stream.
- Weekly Review: outcome attribution, calibration, error attribution, replay, and candidate lessons.
- Eval & Admin: evaluation result, version pins, gates, runtime/provider status, and safe policy
  controls.

Provider diagnostics, full lineage, complete historical tables, raw payloads, and exhaustive audit
records remain available through native disclosures after the first viewport. They are not deleted
or replaced by summary prose.

## Layout strategy

Use one shared compact page grammar rather than independent dashboards:

1. A shallow page context row contains title, mode, cutoff, and the highest-severity status.
2. A primary summary grid contains two or three information-dense surfaces sized by content value.
3. Dense lists and tables use 44px minimum rows, 13–14px body/data text, tabular numerals, and
   restrained separators rather than large card padding.
4. Secondary diagnostics use collapsed `details` elements with explicit counts and labels.
5. At `1280×720`, columns may reduce but critical summaries and actions remain visible; below that,
   the layout prioritizes readability over the single-screen target.

The interface will not use a user-selectable density mode. One predictable responsive system is
simpler and avoids inconsistent information priority.

## Density limits

- Page titles: 36–44px at the target viewport.
- Body and data text: never below 13px.
- Interactive targets and rows: at least 44px.
- Desktop gaps and padding: approximately 20–30% below the current presentation.
- Visible collections show the most relevant records and provide a route or disclosure to all
  records.
- Semantic state, unavailable reason, provider identity, point-in-time cutoff, and Paper Trading
  boundaries stay visible even when layout is compressed.

## Route-specific hierarchy

### Today

Portfolio remains the strongest value, Market Regime is supporting context, Watchlist uses market
rows, and Alerts plus Research activity form a compact rail. Provider diagnostics remain collapsed.

### Watchlist and Research

Configuration controls stay adjacent to the symbol or rule they affect. The authoritative symbol
selector and latest persisted research lead; full SEC, earnings, news, options, data-quality, and
history tables become counted disclosures.

### Run Trace and Portfolio

Operational progress and accounting facts lead. Long event streams, position/fill/risk tables, and
CashLedger records use compact summaries plus scrollable or disclosed full tables. No accounting
evidence is replaced with a decorative aggregate.

### Alerts, Weekly Review, and Eval & Admin

Current actionable status and gate results lead. Historical records, replay evidence, calibration
samples, policy audit, and raw evaluation detail remain available one disclosure level deeper.

## Safety and truthfulness

The redesign changes markup and CSS only unless an existing component needs a semantic wrapper. It
must not change calculations, API contracts, provider entitlement claims, point-in-time filtering,
Fixture/API routing, deterministic decisions, Paper Trading limits, or policy activation rules.
Unavailable facts remain unavailable and never receive synthetic values.

## Verification

- TDD component contracts for each route's critical summary and collapsed secondary evidence.
- Existing behavior, API-degradation, and data-truth regressions remain green.
- Playwright geometry at `1440×800` for all eight primary routes.
- Safety layout checks at `1280×720` and mobile overflow checks.
- Light/dark, keyboard, reduced-motion, reduced-transparency, high-contrast, and serious/critical Axe
  validation.
- Full frontend suite, production build, and repository `make verify` before completion.
