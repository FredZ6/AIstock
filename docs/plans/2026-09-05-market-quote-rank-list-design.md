# TradingView Market Reference List Design

## Goal

Replace the Today page's large persisted-quote card grid with the approved TradingView-powered compact market list: symbol identity, current price, daily movement, and inline chart context in a vertically scannable presentation.

## Data boundary

- TradingView is a read-only **current market reference** and is never decision-time evidence.
- The widget does not feed research, portfolio decisions, alerts, or paper execution.
- Persisted Alpaca quotes remain available in a collapsed audit disclosure with the page PIT cutoff, provider coverage, price, and `available_at`.
- If the third-party widget is blocked or slow, an explicit loading/unavailable placeholder remains. Fixture data is never substituted.

## Technical approach

Use TradingView's isolated Market Data iframe widget for one compact multi-symbol list. The initially evaluated Web Component bundle was rejected after real-browser verification showed its module response lacked the cross-origin header required by browsers. One supported iframe still replaces eleven independent chart documents. Symbols are derived only from the successfully returned persisted quote list, normalized and allowlisted before being passed to the widget.

The widget is reinitialized with its supported `colorTheme` option when the page theme changes, so the existing light/dark toggle remains authoritative. The wrapper owns sizing, loading copy, provenance disclosure, and the visual separation between external current data and internal persisted facts.

## Apple design constraints

- **Purpose and simplicity:** the TradingView list is the primary scan surface; provider evidence is one level deeper in a disclosure.
- **Safety and understanding:** “Current market reference” and “Not decision-time evidence” remain visible above the widget.
- **Craft:** use one rounded material, deliberate spacing, stable reserved height, and system typography around the external surface.
- **Response:** keep widget loading non-blocking and use an immediate, restrained disclosure press state.
- **Flexibility:** no horizontal page overflow, usable narrow-screen sizing, high-contrast boundary, reduced-motion support, and light/dark theme inheritance.

## Verification

- Component tests lock the external-data warning, normalized exchange-qualified TradingView symbols, isolated widget configuration, placeholder, compact height, theme, and collapsed PIT evidence.
- Existing API tests prove the underlying persisted quote contract remains unchanged.
- Route-degradation tests prove no Fixture substitution when backend data is missing.
