# Product completeness audit — 2026-08-31

Status: Open
Branch: `codex/live-runtime-closure`
Scope: API-mode frontend, provider ingestion runtime, paper portfolio, research, alerts, learning,
and developer verification isolation.

This is the authoritative local remediation list for the post–M7.5 runtime closure review. It
records observed facts only. Fixture values are never accepted as evidence for API-mode completion.

## Confirmed facts

- Alpaca credentials are configured for read-only IEX Market Data in `paper` mode.
- PostgreSQL contains persisted Alpaca facts for AVGO and NVDA; nine other configured Watchlist
  symbols currently have no visible quote.
- `portfolio_nav`, `paper_order`, `paper_fill`, `cash_ledger`, `risk_decision`,
  `weekly_review_run`, `candidate_lesson`, `research_opinion`, `investment_thesis`, and
  `alert_event` each contain zero rows in the current local database.
- API-mode outage behavior was verified: it renders Failure/Degraded and does not substitute Fixture
  data.
- The current `make verify` gate passes only when long-running Celery workers are paused because the
  runtime worker and one integration test share the same Redis queue.

## Remediation register

| ID | Severity | Area | Finding | Required outcome | Status |
| --- | --- | --- | --- | --- | --- |
| AUD-001 | P1 | Alpaca stream | An unsupported Alpaca control/error message raises `ValueError`; `run_forever` does not catch it, so the supervisor can terminate. | Classify supported control/error messages, archive auditable failures, reconnect with bounded backoff, and prove recovery without losing raw lineage. | Fixed locally; full gate pending |
| AUD-002 | P1 | Test isolation | A live `ingestion-low` worker can consume the Celery/MinIO/PostgreSQL E2E test task from shared Redis and leave the isolated job `QUEUED`. | Give the test an isolated broker/queue namespace so `make verify` passes while the local runtime remains active. | Fixed locally; live-runtime full gate pending |
| AUD-003 | P1 | API contract delivery | The local response allowlist fix prevents raw Alpaca short fields from causing strict response validation HTTP 500, but it is not committed or pushed. | Keep the regression, complete review, commit, push, and land through PR. | Implemented locally; delivery open |
| AUD-004 | P1 | Weekly Review | `/weekly-review` unconditionally renders `fixtureWeeklyReviewSnapshot`, even when the rest of the product is in API Mode. | Route by explicit data mode; API Mode must read persisted weekly-review facts or show an honest Empty/Failure state, never Fixture data. | Fixed locally; full gate pending |
| AUD-005 | P1 | Portfolio | A successful API response with `latest_nav=null` is presented as `Failure`, and `Try again` cannot initialize missing facts. | Distinguish Empty from transport/contract Failure; initialize the approved singleton paper portfolio with USD 100,000 through an audited, idempotent paper-only path. | Fixed locally; full gate pending |
| AUD-006 | P1 | Product data flow | Research, Alerts, Portfolio, and Weekly Review have no persisted business facts, so most API-mode decision surfaces cannot fulfill their primary purpose. | Run or repair the real Research → Decision → Paper Portfolio → Outcome/Weekly Review chain; preserve explicit gaps for unavailable licensed feeds. | Fixed locally; full gate passed |
| AUD-007 | P1 | Today status | The compact degraded banner mixes provider failures, quality state, per-symbol quote gaps, and missing product domains into roughly 15 equal-weight pills, including overlapping Provider-health labels. | Show a concise severity/count summary; group details by Provider, Market Data, and Decision Domain behind progressive disclosure. | Fixed locally; full gate passed |
| AUD-008 | P2 | Market coverage | Only 2 of 11 Watchlist symbols have persisted visible quotes. | Execute bounded, licensed IEX backfills for the remaining symbols, with PIT, MinIO, quality, and idempotency evidence. | Open |
| AUD-009 | P2 | Ingestion classification | Eleven manually invoked weekend bar jobs are append-only `DEAD_LETTER` rows classified as `SCHEMA_DRIFT`, although the interval contained no completed trading session. | Reject or complete no-session windows deterministically before Provider parsing and reserve `SCHEMA_DRIFT` for actual contract changes. Preserve existing audit rows. | Open |
| AUD-010 | P2 | Responsive UI | Weekly Review content/navigation is visibly clipped at the right edge in the supplied desktop viewport. | Remove horizontal page overflow, keep tables locally scrollable, and verify desktop/mobile/200% zoom. | Open |
| AUD-011 | P2 | Next.js development | Dev server warns that cross-origin requests from `127.0.0.1` will require explicit `allowedDevOrigins` in a future major version. | Configure the intentionally supported local origins without broad wildcards and add a config regression. | Open |
| AUD-012 | P2 | Provider status | Market-closed/stale data can make Provider Health read `FAILURE` while the latest ingestion job is `SUCCEEDED` and latest quality observation is `PASS`. | Review session-aware freshness semantics so market closure is not confused with an active Provider outage, without masking genuinely stale data. | Open |
| AUD-013 | P1 | API-mode boundaries | Alerts, Run Trace, and Weekly Review always import Fixture snapshots; Eval merges a local report into Fixture policy/admin data. They therefore display synthetic facts while the product can otherwise say API Mode. | Give every route one explicit data-mode boundary. API Mode must use persisted contracts or honest Loading/Empty/Stale/Degraded/Failure states and must never import Fixture facts. | Fixed locally; full gate pending |
| AUD-014 | P1 | REST contracts | Alerts, orders, fills, stock research, and weekly reviews return unbounded database rows without pagination; several have no closed response model, and alerts/orders/fills do not accept a PIT cutoff. The contract suite proves only that most routes are callable. | Define strict versioned response schemas, deterministic ordering/cursors and bounded limits; require `available_at <= decision_time` wherever historical facts are exposed; extend OpenAPI closure tests to every locked read. | Fixed locally; full gate pending |
| AUD-015 | P1 | Portfolio API | The portfolio read exposes only the latest NAV and `paper_only`. It omits the persisted portfolio configuration, cash, positions and P&L, risk decisions/rejections, orders, fills, CashLedger, and performance history required by the UI. | Add a PIT-safe portfolio summary/detail contract built from authoritative paper-only facts, including an explicit Empty state before initialization. | Fixed locally; full gate pending |
| AUD-016 | P1 | Weekly Review API | `/weekly-reviews` exposes only `weekly_review_run` rows. It cannot supply outcomes, error attribution, candidate lessons and approvals, point-in-time replay, or confidence calibration shown by the page/specification. | Provide bounded summary and detail contracts joining the normalized learning facts without mutating historical records or leaking future lessons into replay. | Fixed locally; full gate pending |
| AUD-017 | P1 | Durable SSE | `/events` passes a request-scoped `Engine.begin()` connection into the entire streaming generator. A running stream can hold a transaction and pool slot indefinitely; each poll also loads every unseen event without a batch limit. | Validate the run/resume cursor up front, then poll through short-lived read transactions with bounded batches, keepalive/disconnect handling, and pool-exhaustion/replay regressions. | Fixed locally; full gate pending |
| AUD-018 | P2 | Provider inventory | Provider Health reports an `fmp` capability even though implemented earnings ingestion uses `alpha_vantage_api_key`; Alpha Vantage is absent from the response. | Derive health inventory from implemented provider adapters/configuration so operator status names match the actual data path. | Fixed locally; full gate pending |
| AUD-019 | P2 | API-mode E2E | Automated accessibility passes in API Mode, but behavioral E2E coverage defaults to Fixture and does not prove all API-mode routes, Empty/Degraded/Failure recovery, SSE replay, or responsive overflow. | Add an isolated API-mode E2E matrix with seeded authoritative facts and outage cases; retain the no-Fixture assertion. | Open |
| AUD-020 | P2 | Error observability | Several server routes collapse all fetch/parse errors through silent `catch` blocks into a generic page state. The UI cannot distinguish timeout, HTTP, or contract drift, and operators receive no route-level diagnostic context. | Preserve safe user-facing states while logging typed failure kind and correlation context without secrets. | Fixed locally; full gate pending |
| AUD-021 | P2 | Route resilience | No App Router `loading.tsx`, `error.tsx`, or route-local not-found boundaries exist for the audited pages. Slow APIs and unexpected render errors therefore lack native progressive and recovery UI. | Add shared, accessible route boundaries consistent with Loading/Failure/Empty semantics. | Fixed locally; full gate pending |
| AUD-022 | P2 | Navigation | Eight top-level items live in one horizontally scrollable row with its scrollbar hidden; the supplied Weekly Review viewport clips the final item/content and gives no discoverable overflow cue. | Use a responsive navigation pattern with visible focus/overflow affordance and prove keyboard, 200% zoom, and narrow desktop behavior. | Open |
| AUD-023 | P2 | Chart accessibility | Performance-chart controls declare `role=tab` and `aria-selected` but lack associated tab/panel IDs, `aria-controls`, and arrow-key tab behavior. | Implement the complete WAI-ARIA tabs interaction or use simpler native buttons if panels do not need tab semantics. | Open |
| AUD-024 | P2 | Theme startup | Theme preference is applied in a client effect after first paint, allowing a light/dark flash and hydration-time visual inconsistency. | Apply the saved/system theme before first paint with a CSP-compatible bootstrap and keep token contrast verified in both themes. | Open |

## Current acceptance gates

- No API-mode route imports or renders Fixture snapshots.
- No live-broker endpoint, credential, configuration flag, or execution path is introduced.
- Alpaca WebSocket control/error messages cannot terminate the long-running supervisor.
- `make verify` passes with the normal local API, Beat, and both Celery workers running.
- Every UI state distinguishes Loading, Empty, Stale, Degraded, Failure, and Success by actual cause.
- Portfolio initialization is idempotent, paper-only, Decimal-based, and fully audited.
- Historical reads continue to enforce `available_at <= decision_time`.
- Watchlist backfill proves PostgreSQL/MinIO lineage and does not fabricate unavailable domains.

## Evidence captured so far

- `output/playwright/api-mode-today.png`
- `output/playwright/api-outage-no-fixture.png`
- User screenshots captured at 2026-08-31 12:43–12:44 Asia/Shanghai: degraded Today banner,
  uninitialized API Portfolio, and Fixture-only Weekly Review.
- API-mode Axe run: desktop Chrome and mobile Chrome both passed with no serious/critical
  automated violations (2 tests passed).
- Static SSE inspection: `/api/v1/events` streams through the request dependency's
  `Engine.begin()` connection and `load_events` has no batch limit.
- Targeted REST/SSE verification (sandbox-exempt local PostgreSQL):
  `UV_CACHE_DIR=.uv-cache uv run pytest -q backend/tests/contract/api/test_rest_contract.py backend/tests/integration/api/test_sse_resume.py`
  exited 0 with 15 passed. The first sandboxed attempt produced 13 environment errors because local
  TCP was denied; those were not product failures.
- AUD-005/AUD-015 TDD closure: the singleton `default-paper` portfolio now has an explicit,
  idempotent `POST /api/v1/portfolio/initialize` path that persists the USD 100,000 opening balance
  as two balanced append-only ledger entries. `GET /api/v1/portfolio` is a strict PIT contract for
  configuration, cash, Decimal positions, risk decisions, orders, fills, ledger, NAV, and
  performance history. Before initialization it returns `EMPTY`; after initialization without a
  NAV it displays authoritative cash as `Degraded`, never Fixture data. Related backend regression
  passed 19/19, complete frontend Vitest passed 22 files / 122 tests, and the regenerated OpenAPI
  artifact passed its drift check.
- AUD-006 worker-path RED proved `execute_weekly_review_run` had no data-mode input and always loaded
  `FixtureCatalog`. GREEN propagates `Settings.fixture_mode`; paper mode reads only cutoff-visible,
  persisted `ALPACA` market bars, selects the latest deterministic revision, and leaves missing
  horizons Pending instead of filling them with synthetic prices. A full Worker execution regression
  passed 18/18. The end-to-end product chain remains open until persisted Research/Portfolio facts and
  the Weekly Review detail API/UI are verified together.
- AUD-016 RED returned 404 for a persisted Weekly Review detail. GREEN adds a strict closed detail
  contract for the frozen review, outcomes, attribution, Candidate Lessons, human approval facts,
  replay runs, and deterministic calibration inputs. Every nested fact is bounded by the requested
  cutoff; a regression proves future Approval and Replay rows remain invisible. API Mode now loads
  the latest persisted detail and renders outcomes/calibration/attribution/lessons, while Empty and
  Failure remain honest and never import Fixture data. Related backend tests passed 33/33 and the
  complete frontend suite passed 22 files / 125 tests.
- AUD-006 runtime closure found and reproduced a paper-mode provider-boundary defect: the generic
  PostgreSQL research adapter discarded real SEC facts by applying an Alpaca-only filter to every
  feed, while a subsequent diagnostic run proved persisted Fixture company facts/options/targets
  could enter a paper-mode thesis. The first diagnostic run
  `a01322d7-b06d-4895-a91e-0c075ed54b37` is retained as append-only invalid evidence. An idempotent,
  deterministic DecisionDiff now links its decision to the corrected run, and PIT product reads plus
  Portfolio/Weekly workers exclude it once that correction fact is visible. RED then proved the
  mixed SEC/Fixture response; GREEN retains real SEC and Alpaca
  records while excluding every Fixture record in paper mode. Four focused provider/worker tests and
  the 29-test Research/Portfolio/Weekly integration set passed.
- Corrected runtime evidence: Research run `df630fa8-b751-4db9-b296-6f4711fb6c79` completed with an
  `ABSTAIN` decision, only ALPACA evidence, and explicit `MISSING`/`UNAVAILABLE` gaps for unavailable
  domains and SIP. The approved `default-paper` account initialized idempotently with two balanced
  USD 100,000 ledger entries. Portfolio admission returned deterministic HTTP 403
  `MARKET_DATA_NOT_ENTITLED` because entitlement is IEX-only, and persisted zero orders, fills, risk
  decisions, or actions. Weekly run `7cb2f805-7369-4430-b436-7eacb2d09a3b` completed from persisted
  facts without Fixture fallback; outcomes remain empty because no post-decision horizon has matured.
  Research, Portfolio, Weekly list, and Weekly detail read contracts all returned HTTP 200.
- Final repository gate exited 0 after correcting five tests that assumed an empty database or old
  response contract. Backend reported 710 passed / 4 credential- or condition-gated skips; Web
  reported 22 files / 125 tests passed. Ruff format/lint, strict Mypy over 278 source files, Alembic
  drift, TypeScript, ESLint, and the Next.js production build all passed.

## Frontend quality score

| Dimension | Score | Evidence |
| --- | ---: | --- |
| Accessibility | 3/4 | API-mode desktop/mobile Axe passed; chart tabs and responsive navigation still need manual/interaction closure. |
| Performance | 2/4 | Parallel server fetches and abort timeouts are positive; unbounded reads, long-lived SSE transactions, and missing route loading boundaries remain. |
| Responsive behavior | 2/4 | Tables have local overflow containers, but navigation/content clipping is visible in the supplied Weekly Review viewport. |
| Theming | 2/4 | Shared tokens and two themes exist; preference is applied after first paint and dark styling contains duplicated/hard-coded overrides. |
| Visual/product anti-patterns | 1/4 | Oversized headings, numerous equal-weight pills, repeated rounded cards, and blue/purple glow reduce information hierarchy. |
| **Total** | **10/20** | **Acceptable foundation; significant product-completeness and hierarchy work remains.** |

Severity summary: **0 P0, 12 P1, 12 P2, 0 P3**.

## Recommended repair sequence

1. **Runtime safety:** AUD-001, AUD-002, AUD-017, then land AUD-003. These protect the supervisor,
   test gate, SSE database capacity, and already-written API regression.
2. **Honest API boundaries:** AUD-013, AUD-014, AUD-018, AUD-020, AUD-021. Close strict contracts
   and remove every API-mode Fixture path before presenting more data.
3. **Authoritative product chain:** AUD-005, AUD-015, AUD-006, AUD-016, then AUD-004. Initialize the
   approved paper account and expose research-to-decision-to-ledger-to-learning facts in order.
4. **Provider correctness:** AUD-009, AUD-012, AUD-008. Correct no-session/freshness semantics, then
   perform bounded licensed backfills.
5. **Experience closure:** AUD-007, AUD-010, AUD-022, AUD-023, AUD-024, AUD-019. Simplify status
   hierarchy and finish responsive, keyboard, theming, and API-mode E2E evidence.

## Audit continuation

The following areas still require targeted verification before remediation begins:

1. Reproduce the SSE connection-pool failure with concurrent running streams and prove bounded
   replay behavior.
2. Capture API-mode keyboard/overflow evidence once the local Playwright permission blocker is
   cleared.
3. Verify provider-health behavior across an open session, a normal market closure, and a genuinely
   overdue feed.
4. Re-run database invariant and append-only suites when remediation starts; existing schema tests
   remain positive evidence, not a substitute for missing read-contract tests.
