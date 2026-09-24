# Apple Finance dense decision workspace

## Outcome

At a 1440×900 desktop viewport and 100% zoom, the Today page must show every decision-critical
region without scrolling: Portfolio, Market Regime, Watchlist, Alerts, and Research Run. Provider
diagnostics and complete lineage remain available below the first viewport through collapsed native
disclosures.

The layout must stay truthful and readable. It must not achieve density by hiding Fixture/API mode,
provider degradation, point-in-time cutoffs, or unavailable facts, and it must not reduce normal body
copy below 13px or interactive targets below 44px.

## Chosen approach

Use a compact two-tier decision workspace rather than a three-column dashboard or a user-selectable
density mode.

1. The first tier places the Portfolio overview beside a compact Market Regime summary.
2. The second tier places a dense Watchlist market list beside a compact action rail containing
   Alerts and Research Run.
3. The Degraded summary stays visible as a single compact row.
4. Provider diagnostics and full lineage use native disclosure elements and remain below the first
   viewport, collapsed by default.

This approach preserves useful column width for financial values and explanatory text while avoiding
the maintenance and cognitive cost of multiple density modes.

## Density system

- Reduce page-heading height, card padding, and section gaps by roughly 20–30% on desktop.
- Keep the page title between 36px and 44px at the target viewport.
- Use compact 13–14px body and data text with tabular numerals.
- Keep Portfolio NAV as the strongest value; density must not flatten hierarchy.
- Render Watchlist entries as rows, not large cards, and show approximately six to eight symbols in
  the first viewport.
- Limit the action rail to the two or three most relevant Alerts and the active/latest Research Run.
- Use concise visible summaries with exact reasons and evidence accessible through disclosure.

## Responsive behavior

The one-screen requirement applies only at 1440×900 and wider desktop contexts. Below 1024px the
workspace collapses to two columns and then one column before content becomes cramped. Typography
and controls do not shrink below the established accessibility bounds.

## Data and safety boundaries

No calculation, provider identity, API contract, point-in-time rule, Paper Trading constraint, or
availability state changes. The redesign may reorder existing facts and add semantic wrappers or
disclosures, but it may not fabricate missing data or silently fall back from API data to fixtures.

## Verification

- TDD markup contracts for the five first-viewport regions and collapsed diagnostics.
- Unit regression for Fixture and API Today variants.
- TypeScript verification.
- Playwright screenshot and bounding-box assertion at 1440×900.
- Mobile, dark-theme, keyboard, and serious/critical Axe checks.
- Full frontend verification and `make verify` before delivery.
