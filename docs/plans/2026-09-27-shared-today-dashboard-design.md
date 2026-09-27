# Shared Today Dashboard Design

Date: 2026-09-27
Status: Approved

## Objective

Restore the compact two-column Today dashboard shown by the approved Fixture design while keeping
API Mode authoritative. API Mode must continue to render persisted backend facts, point-in-time
timestamps, explicit unavailable states, the 60-second refresh controller, and durable run progress.
It must never substitute Fixture facts.

## Approach

Extract the common Today dashboard composition into a shared presentation component. Fixture and API
routes will adapt their own contracts into an explicit dashboard view model. This prevents the two
modes from drifting into unrelated page structures while preserving their different provenance and
availability semantics.

The rejected alternatives are:

- Styling `ApiTodayPage` independently, which would preserve duplicate layout trees and invite
  another visual divergence.
- Switching `WEB_DATA_MODE` back to Fixture, which would reproduce the screenshot by presenting
  synthetic facts and violate the approved real-data boundary.

## Information Architecture

The first viewport uses the approved MacBook Air 13-inch dashboard hierarchy:

1. Today heading, dual timezone context, data-mode/provenance label, and compact availability status.
2. Left primary surface: Paper Portfolio performance summary with Market Regime context alongside it.
3. Right upper surface: Watchlist signals from the authoritative persisted watchlist and quotes.
4. Right lower surfaces: actionable persisted alerts and current research-run progress.
5. Default-closed Provider diagnostics and complete lineage below the decision workspace.

Desktop uses the existing asymmetric two-column dashboard. Mobile keeps every critical fact and action
in a deliberate single-column order rather than hiding content.

## Data Adaptation

The shared component accepts presentation-safe data only. Fixture Mode maps its frozen snapshot into
the view model and retains the Fixture notice. API Mode maps persisted Portfolio, quote, research,
alert, run and provider-health contracts into the same slots.

API data rules remain unchanged:

- Every historical fact must satisfy the existing PIT cutoff.
- Money stays string/Decimal-backed; the frontend does not introduce floating-point calculations.
- Missing facts render compact Empty, Degraded or Unavailable content in their assigned slot.
- API Mode never imports or reads Fixture snapshots.
- Current external market context remains labelled separately from decision-time evidence.

Where the API does not yet provide a Fixture-only metric such as the illustrative market-regime model,
the shared slot presents the persisted/derived API fact if available or an explicit unavailable state;
it never copies the Fixture value.

## Interaction and Error Handling

- API pages keep the existing 60-second visible-page refresh behavior.
- Active run progress uses the existing durable run/SSE path rather than synthetic progress.
- Provider diagnostics and full lineage remain default-closed to protect first-viewport density.
- Transport or contract failures retain the shared Failure/Degraded surfaces and retry affordances.
- Theme selection remains independent of data mode; the layout must match in light and dark themes.

## Verification

Implementation follows TDD:

1. Add a failing structural contract proving Fixture and API Today pages use the same dashboard
   composition and ordering.
2. Add API-mode assertions for no Fixture content, real provenance, explicit missing-slot states and
   live refresh.
3. Add browser acceptance at 1440x800, 1280x720 and mobile widths for first-viewport density,
   no overlap, no horizontal overflow, dark theme and keyboard accessibility.
4. Run focused tests, the complete frontend suite, the live API browser regression and `make verify`.
5. Record final evidence in `docs/progress.md` before review.
