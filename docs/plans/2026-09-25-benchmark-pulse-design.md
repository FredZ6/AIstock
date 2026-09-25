# Benchmark Pulse Design

## Purpose

The compact Today workspace leaves unused vertical space below Market Regime because the adjacent Portfolio Overview determines the shared surface height. Fill that space with decision-relevant information already present on the page, without adding a new data contract or inventing market facts.

## Approved design

- Move the existing `Cash`, `QQQ`, `Equal weight`, and `Momentum` benchmark values out of the Portfolio Overview footer.
- Present those same values once, beneath Market Regime, in a compact `Benchmark pulse` section.
- Preserve Market Regime label, model version, and four existing regime metrics unchanged.
- Keep the Portfolio Overview focused on NAV, daily return, drawdown, and performance history.
- Use the existing Today spacing token and surface language so the new section feels like part of the market context rather than another nested card.

## Data and safety

The component reads only `snapshot.portfolio.benchmarks`; it performs no new API requests and creates no derived trading recommendation. Fixture, paper, freshness, provider, and point-in-time semantics remain unchanged.

## Responsive behavior

At the MacBook Air desktop viewport, Benchmark pulse occupies the lower portion of the Market Regime column. At compact breakpoints, it stays in document order after regime metrics and before the next Today section. Values remain a two-column grid and reflow with existing Today responsive rules.

## Verification

- Component tests prove each benchmark appears once and inside Market Regime.
- Browser tests prove Benchmark pulse remains inside the shared surface and does not push the critical Today workspace below the first MacBook Air viewport.
- Existing unit, accessibility, responsive, lint, typecheck, and production-build checks remain green.
