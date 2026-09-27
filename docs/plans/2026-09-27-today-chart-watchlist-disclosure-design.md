# Today chart and Watchlist disclosure design

## Goal

Make the Today workspace more useful without increasing its default visual height. The Paper
Portfolio presents one meaningful historical series at a time, while Watchlist leads with two symbols
and keeps the remaining persisted rows available on demand.

## Portfolio chart

The three existing headline metrics become an accessible tab set: Net asset value, Day return, and
Current drawdown. Net asset value is selected initially. Selecting another metric updates one shared
line chart, its units, caption, and accessible name. Different units are never overlaid in one chart.

Fixture mode uses the existing frozen history and may derive return and drawdown series from that
frozen dataset. API mode uses persisted portfolio history only. It must not interpolate or invent a
series when the persisted records cannot support the selected metric; instead, the chart reports that
history is insufficient. Monetary calculations remain outside binary floating point paths used for
business decisions; chart coordinates are presentation-only transformations of already formatted or
Decimal-derived values.

## Watchlist disclosure

The Today Watchlist renders the first two ranked symbols by default. When more symbols exist, the
header exposes a dedicated `Show all (N)` button with `aria-expanded=false`. Activating it reveals the
remaining rows in the same list and changes the control to `Show less`. The Manage watchlist link and
symbol links remain independent targets; the entire surface is not made clickable because doing so
would create nested and ambiguous interactions.

With zero, one, or two symbols, no disclosure control is shown. Expanded state is local presentation
state and is deliberately not persisted across navigation or reloads.

## Responsive and visual behavior

The collapsed state preserves the approved 1440x800 and 1280x720 split workspace. Expanded Watchlist
may increase the page height but must not create horizontal overflow. Mobile keeps the existing
single-column summary, Watchlist, and Decision activity order. Both themes reuse current tokens and
focus styles.

## Failure and accessibility behavior

Unavailable API facts remain explicit and never fall back to Fixture data. The metric controls use
tab semantics with keyboard focus and selected-state announcements. The Watchlist button exposes its
expanded state and controls the stable list region. Chart changes retain a descriptive accessible name
and text summary so color and line geometry are not the only carriers of meaning.

## Verification

- Unit tests prove Net asset value is the default series and the other two metrics switch the chart.
- API tests prove insufficient persisted history remains explicit without synthetic values.
- Component tests prove only two Watchlist rows appear initially and all rows appear after keyboard
  activation, with correct `aria-expanded` state.
- Browser tests cover 1440x800, 1280x720, 393x852, both themes, no horizontal overflow, and default
  first-viewport density.
- The final repository gate is `make verify`, recorded in `docs/progress.md` after writers are stopped.
