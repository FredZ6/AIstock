# Today Responsive Closure Design

## Goal

Close the five remaining Today layout findings in priority order while preserving the approved dense desktop workspace, Fixture/API truthfulness, and accessible navigation.

## Approved changes

1. At compact widths, stack Portfolio Overview above Market Regime so every fact remains inside the shared summary surface.
2. Reduce mobile chrome and metadata height: remove the redundant `Current · Today` line, place the two timezone facts side by side, and tighten only the Today header/status spacing.
3. At narrow desktop widths, give Actionable Alerts more width than Research execution so headings and actions wrap less aggressively.
4. Keep the NAV currency and amount together as one typographic unit with responsive sizing.
5. Reduce the collapsed Provider diagnostics row height so it remains discoverable without competing with primary facts.

## Boundaries

- CSS-first; no backend or data-contract changes.
- No information is hidden except the redundant mobile `Current · Today` orientation line; the page heading and current navigation state remain visible and accessible.
- Mobile may scroll vertically, but no fact may be horizontally clipped or escape its containing surface.
- Desktop 1440×800 and 1280×720 retain the approved split workspace and bottom alignment.

## Verification

- Add a browser regression file covering 393×852 internal containment, first-fact position, 1280×720 activity-card wrapping, NAV single-line presentation, and collapsed diagnostics visibility.
- Run each new test red before its corresponding CSS change.
- Run the full unit, lint, typecheck, build, desktop/mobile E2E, and accessibility suite after all five slices.
