# Market Quote Rank List Design

## Goal

Replace the Today page's large quote-card grid with a compact, scannable market rank list modeled on the approved reference: symbol and company name on the left, a point-in-time sparkline in the middle, and latest price plus daily return on the right.

## Source of truth and data integrity

- The list uses only persisted backend facts visible at the page `decision_time`.
- Every bar used by the sparkline and return calculation must satisfy `available_at <= decision_time` and `event_time <= decision_time`.
- Company names come from persisted security-master records, not a frontend lookup table.
- Daily return is deterministic code derived from persisted decimal closes. It is absent when a valid previous close is unavailable.
- Sparkline points are decimal strings in the API and are converted only for SVG coordinates at the presentation boundary; money remains decimal strings everywhere else.
- Missing enrichment is rendered as `Unavailable`. Fixture data and TradingView data are never substituted in API mode.

## Presentation

Each row is one link to `/research/{symbol}` and contains:

1. Symbol and company name.
2. A lightweight inline SVG sparkline with a non-color direction label for accessibility.
3. Latest USD close and signed daily percentage return.
4. Provider, entitlement coverage, and availability time as compact provenance text.

Rows use separators rather than independent cards. Positive, negative, and neutral movement use semantic colors, while text and accessible labels preserve meaning without relying on color. Desktop uses three columns; narrow screens retain the same reading order and reduce the chart width.

## Apple design constraints

- **Purpose and simplicity:** make symbol, current price, and movement the dominant scan path; demote provenance without hiding it.
- **Familiarity:** the whole row behaves as one predictable navigation target and retains a visible keyboard focus ring.
- **Craft:** use tabular numerals, optical heading tracking, consistent baselines, system typography, and deliberate `rem`-based spacing.
- **Response:** apply immediate pointer-down feedback with a restrained scale/color change; do not add decorative or looping animation.
- **Flexibility:** preserve a minimum 44px row target, readable order under text scaling, light/dark theme contrast, and a narrow-screen layout without horizontal scrolling.
- **Accessibility:** the sparkline has an accessible movement description, visual meaning never relies on color alone, and reduced-motion/high-contrast preferences are respected.

## Failure and degraded behavior

- No latest quote: the existing missing-symbol and degraded-state behavior remains authoritative.
- No security-master name: show `Company unavailable`.
- Fewer than two daily closes: show `Return unavailable` and a neutral chart state.
- No history: show `Chart unavailable` without fabricated points.

## Verification

- Backend integration tests prove PIT filtering, deterministic return calculation, company-name enrichment, and unavailable history behavior.
- Web contract tests reject malformed enrichment fields.
- Component tests prove row semantics, links, provenance, signed return, and accessible chart fallback.
- Existing API degradation and full web verification suites remain green.
