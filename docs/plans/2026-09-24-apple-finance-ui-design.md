# Apple Finance UI redesign

## Outcome

Make the research platform feel calm, precise, and native to the device while preserving every
truthfulness boundary already enforced by API mode. The interface should reveal the most useful
decision facts in the first viewport, keep secondary provenance available without dominating the
page, and remain equally legible in light, dark, reduced-transparency, high-contrast, and
reduced-motion environments.

The redesign does not change provider status, point-in-time eligibility, Agent behavior, Paper
Trading rules, or Fixture/API routing.

## Chosen direction

Use an Apple Finance-inspired product language rather than an editorial landing page or a dense
terminal. The visual character is quiet and information-led:

- platform system typography with optical sizing and size-specific tracking;
- a floating translucent navigation layer with one obvious current-page indicator;
- soft blue-gray page material, high-contrast content surfaces, restrained shadows, and consistent
  16–20px radii;
- semantic color reserved for market direction, risk, runtime health, and primary actions;
- compact summaries first, with provenance and diagnostic detail disclosed one level deeper.

## Information hierarchy

### Shared shell

The shell remains the stable wayfinding anchor across every route. On desktop it uses one compact
floating bar containing product identity, primary destinations, and appearance control. On narrow
screens it becomes a compact title row plus an anchored navigation sheet. The header material is
translucent only once: cards beneath it are opaque enough to avoid stacked-glass legibility loss.

The shell answers three questions immediately: which product is open, which page is active, and
where the user can go next. The active destination uses a quiet blue capsule; inactive destinations
use text, not boxed buttons.

### Page heading and runtime context

Oversized marketing headings are replaced with compact product headings. Page title and purpose sit
on the left; cutoff time and runtime provenance sit in a small context cluster on the right. Fixture
Mode, API Mode, stale data, and degraded coverage remain explicit, but use short badges rather than
large empty banners.

Availability summaries retain their canonical state, exact reason, and safe action. The collapsed
row is visually compact. Expanded details become a readable list of state, subject, reason, and
action rather than a field of chips.

### Today

The first viewport is organized by decision value:

1. Portfolio value, daily return, and drawdown form the primary overview.
2. Market regime is a compact supporting card rather than an equal-sized empty column.
3. Watchlist movers use a dense quote row with symbol, company/context, sparkline when available,
   price, and percent change.
4. Alerts and running research follow as actionable work, with provider diagnostics below them.

This removes the current large unused area under Market Regime and makes the page scan vertically in
one predictable rhythm.

### Remaining pages

Watchlist, Research, Run Trace, Portfolio, Alerts, Weekly Review, and Eval/Admin adopt the same
tokens and surface rules. Dense evidence tables stay tables; they are not converted into decorative
cards. Important actions remain adjacent to the object they affect. Empty and failure states keep
their reasons and recovery actions rather than becoming visually polished but ambiguous.

## Visual system

### Type

- Use the platform system font stack with `font-optical-sizing: auto`.
- Display/page titles use tight leading and approximately `-0.03em` tracking.
- Section titles use moderate weight, not all-caps size alone.
- Small labels use positive tracking only where uppercase improves scanning.
- Body copy stays near zero tracking with comfortable leading.

### Color and material

- Light canvas: quiet blue-gray with a subtle radial wash, not a flat saturated background.
- Dark canvas: near-black blue, with distinct elevated and grouped surfaces.
- Primary surfaces: mostly opaque for sustained reading.
- Floating chrome: translucent with blur and saturation, plus a soft edge highlight.
- Positive/negative colors meet WCAG AA and never act as the sole status indicator.
- Borders are reserved for containment or focus; section separation prefers spacing and tonal change.

### Spacing and shape

- Use a small spacing scale based on `0.25rem`, with page rhythm at 24–32px.
- Major cards use 20px radii; compact controls use capsules or 12px radii.
- Related labels and values stay close; unrelated groups gain visibly more space.
- Desktop content width remains bounded for readable scanning. Mobile cards use the full safe width.

## Interaction and motion

- Buttons and links respond on press with a short scale/tonal change.
- Navigation and disclosure transitions use critically damped, non-bouncy motion around 300–400ms.
- No interaction is locked while a visual transition finishes.
- Focus indicators remain visible and use the same spatial shape as the control.
- `prefers-reduced-motion` removes displacement and keeps short opacity/color feedback.
- `prefers-reduced-transparency` replaces blur with an opaque surface.
- `prefers-contrast: more` increases surface opacity and boundary contrast.

No new animation dependency is required for this pass. Gesture physics are unnecessary because the
approved interaction set has no draggable or momentum-driven surface.

## Component and token strategy

The redesign should be implemented through shared primitives rather than page-specific overrides:

- revise global color, type, radius, shadow, spacing, and motion tokens;
- update `AppShell`, page headings, navigation, theme control, `StateBoundary`, surface cards, metric
  lists, quote/watchlist rows, tables, and form controls;
- keep page data contracts and server components unchanged unless markup is needed for semantic
  grouping;
- prefer existing components and CSS; do not introduce a broad UI framework.

## Data and safety boundaries

All displayed values continue to come from existing props and API contracts. The redesign must not:

- infer or fabricate unavailable data;
- hide Fixture Mode or provider coverage;
- convert current-market TradingView context into historical evidence;
- create a Live Broker setting, endpoint, or execution path;
- weaken `available_at <= decision_time` behavior;
- make an LLM responsible for deterministic risk, accounting, or policy decisions.

## Responsive behavior

Desktop uses a bounded multi-column layout only when both columns contain useful content. Tablet
reduces columns before text or controls become cramped. Mobile uses one reading column, minimum 44px
interactive targets, horizontally scrollable data tables with an accessible region label, and no
page-level horizontal overflow.

## Error handling

Loading, Empty, Unsupported, Unconfigured, Stale, Degraded, Failure, and Success keep their current
semantics. Visual weight changes by severity, but every state remains textually named. Failure and
warning surfaces include their recovery action when one exists; unsupported domains explicitly say
that no approved producer exists.

## Verification

Implementation follows visual TDD:

1. Add or update token/layout contract tests before changing CSS.
2. Preserve current behavioral unit and API-boundary tests.
3. Capture desktop and mobile screenshots for Today and representative dense pages.
4. Exercise keyboard navigation, disclosures, mobile navigation, theme switching, and press feedback.
5. Run Axe with WCAG A/AA tags and assert no serious or critical violations.
6. Verify reduced-motion, reduced-transparency, high-contrast, light, and dark variants.
7. Run the complete frontend suite, production build, managed browser matrix, and `make verify`.

## Delivery sequence

1. Shared tokens, typography, canvas, and shell.
2. Shared state, surface, metric, table, and control primitives.
3. Today hierarchy and Watchlist quote presentation.
4. Remaining routes normalized onto the shared system.
5. Desktop/mobile/dark/accessibility polish and full verification.

