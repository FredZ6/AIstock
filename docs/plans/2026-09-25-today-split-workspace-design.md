# Today Split Workspace Design

## Goal

Fit every decision-critical Today module inside a 1440×800 MacBook Air browser viewport without
shrinking body text below 13px, hiding facts, or changing any data behavior.

## Approved desktop composition

At widths above 1024px, Today uses an approximately 60/40 split workspace with a 24rem minimum
action column. The wider action column prevents decision labels and timestamps from wrapping into a
tall rail at the 1280×720 safety viewport:

- The left column spans both workspace rows and contains the Paper Portfolio plus Market Regime.
- The right column places Watchlist first, followed by Alerts and Research Run activity.
- Provider diagnostics and complete lineage remain collapsed below the workspace.
- Fixture and API Today retain the same spatial hierarchy. API mode continues to show only persisted
  facts and explicit unavailable states; it never substitutes Fixture data.

The wide portfolio chart remains the strongest visual object. The right column uses compact rows and
cards rather than reducing type size, so scanning order stays Portfolio → Watchlist → Action.

## Responsive behavior

- Above 1024px: approximately 60/40 split with the left summary spanning both rows.
- At or below 1024px: one readable column in semantic DOM order.
- At 1280×720: all critical regions remain usable without page-level horizontal scrolling.
- At mobile widths and 200% text zoom: readability takes priority over the single-screen target.

## Accessibility and safety

- Preserve semantic regions, heading order, keyboard navigation, focus visibility, light/dark themes,
  reduced-motion behavior, and minimum 44px controls.
- Preserve Paper Trading-only copy, data-quality dimensions, provider identity, cutoff timestamps,
  and degraded/unavailable states.
- No calculations, API contracts, provider permissions, execution paths, or Fixture/API routing change.

## Acceptance criteria

- At 1440×800, the Today decision workspace ends inside the first viewport.
- The left summary begins at the workspace top and spans the height of the right stack.
- Watchlist appears above Decision activity in the right column.
- Watchlist facts do not overlap at 1440×800 or 1280×720.
- Below the desktop breakpoint, every region returns to one column with no horizontal overflow.
- Unit, type, build, desktop/mobile Playwright, and automated accessibility checks pass.
