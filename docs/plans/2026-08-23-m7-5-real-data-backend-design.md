# M7.5 Real Data Backend — Approved Design

Date: 2026-08-23
Status: Approved for implementation
Milestone: M7.5 Real Data Backend
Authority: Notion v0.2 plus the approved selective provider override

## Outcome

M7.5 adds a read-only, raw-first ingestion backend for Alpaca market/news data,
SEC EDGAR filings/facts, and Alpha Vantage earnings-calendar data before M8 begins.
It does not add product pages, public API endpoints, Agents, MCP servers, live-broker
integration, or a real-money path.

The implementation remains a modular monolith:

```text
Watchlist / Beat
    -> IngestionJob
    -> ProviderAdapter
    -> immutable MinIO object
    -> RawDataObject + NormalizationDispatch transaction
    -> versioned normalizer
    -> NormalizedRecord + domain facts
    -> DataQualityObservation
    -> PointInTimeRepository
    -> existing Agent / MCP / API consumers
```

PostgreSQL is authoritative. Redis and Celery provide delivery and coordination only.
Delivery is at least once; correctness comes from deterministic idempotency keys,
append-only facts, leases, and database constraints.

## Engineering approval

The design is approved with the following mandatory refinements already incorporated:

1. A SIP entitlement must be detected and recorded. The system must not assume that a
   free Alpaca account includes delayed or consolidated SIP data.
2. `RESEARCH` can complete with typed evidence gaps when SIP market inputs are absent,
   but it cannot relabel IEX as consolidated data. `REPLAY` and `PAPER_EXECUTION` must
   reject or produce `NO_ACTION` when required SIP inputs are unavailable.
3. Historical visibility requires both `event_time <= decision_time` and
   `available_at <= decision_time`.
4. Raw and normalized facts are append-only. Persistence uses `DO NOTHING` plus a
   deterministic re-read, never `DO UPDATE`.
5. Provider retry is orchestrated by Celery/job state and honors `Retry-After`; workers
   must not block on in-process sleep.
6. Five initially proposed tables are removed until a proven consumer exists:
   `MarketTrade`, `SecDocument`, `EarningsCalendarSnapshot`, `ReconciliationResult`, and
   `ProviderHealthSnapshot`.
7. A durable `NormalizationDispatch` outbox is retained because it closes the crash
   window between raw metadata commit and Celery delivery.

## Four sequential tasks

### RDB-1 — Canonical ingestion foundation

- Add Security, versioned identifiers/profiles, and migrate Watchlist to `security_id`
  without changing the existing symbol-based REST contract.
- Add IngestionJob, IngestionAttempt, IngestionCursor, IngestionDeadLetter,
  IngestionRawLink, and NormalizationDispatch.
- Harden RawDataObject and NormalizedRecord as append-only; add deterministic
  `record_key` to normalized uniqueness.
- Add lease token/generation compare-and-set transitions and durable dispatch recovery.
- Fix point-in-time repositories to enforce both time predicates.
- Preserve existing data, fixtures, FMP compatibility code, and Watchlist settings.

### RDB-2 — Alpaca market and news ingestion

- Refactor the existing Alpaca REST/stream code behind the provider-neutral adapter
  seam instead of creating a parallel stack.
- Store REST responses and WebSocket batches in MinIO before normalization.
- Persist typed MarketBar and NewsArticle facts. Trades, quotes, status messages, and
  updated-bar source messages remain replayable in Raw/Normalized records unless a
  downstream consumer demonstrates a need for a dedicated table.
- Keep IEX, SIP, and overnight data as separate series with explicit coverage/session.
- Implement bounded daily/minute/news backfills, reconnect gap recovery, pagination,
  and entitlement-aware routing.

### RDB-3 — SEC and Alpha Vantage ingestion

- Resolve Watchlist securities to CIK and filing regime; support 10-K, 10-Q, 8-K,
  20-F, 6-K, DEF 14A, S-1/F-1, and 424B as applicable.
- Store SEC submissions/documents raw; persist SecFiling and FinancialFact domain facts.
- Version deterministic US-GAAP/IFRS concept mappings as EXACT, DERIVED, UNMAPPED, or
  AMBIGUOUS. LLM-based concept mapping is prohibited.
- Store each Alpha Vantage calendar CSV as raw; persist versioned EarningsEvent facts.
- Treat SEC acceptance time as availability when supplied and never overwrite amendments.

### RDB-4 — Quality, release gates, replay, and operations

- Add DataQualityObservation for freshness, coverage, provider, delay, conflict,
  reconciliation, and health transitions. A/B/C/D remains a UI derivation only.
- Add deterministic bar-gap/duplicate/revision reconciliation and corporate-action
  handling.
- Add replay from immutable MinIO objects with a newer normalizer version.
- Add provider dashboards/alerts from job, cursor, quality, and metrics data rather than
  a periodic health-snapshot table.
- Add credential-gated live smoke tests, runbooks, recovery drills, and M7.5 evidence.

Tasks execute strictly in this order. Each task uses TDD and receives its own review
evidence before the next task begins.

## Authoritative model

### Security master data

- `Security`: permanent identity and instrument type.
- `SecurityIdentifierVersion`: symbol, exchange, provider identifier, effective time,
  availability time, and `supersedes_id`.
- `SecurityProfileVersion`: company/profile, currency, CIK, filing regime, ADR metadata,
  effective/availability time, and `supersedes_id`.
- `WatchlistItem`: references `security_id`; research, intraday, news, filing flags,
  thresholds, and priority remain mutable configuration.

Ticker is a lookup alias, not identity. Symbol changes add a version; history is not
rewritten.

### Control plane

- `IngestionJob`: normalized request hash, dataset, window, state, attempt budget,
  lease token/generation, policy version, and timestamps.
- `IngestionAttempt`: one immutable attempt record with error classification and timing.
- `IngestionCursor`: current committed provider cursor/watermark; updated only through a
  guarded compare-and-set after a continuous successful range.
- `IngestionDeadLetter`: immutable exhausted/non-retryable failure evidence.
- `IngestionRawLink`: many-to-many provenance between jobs and deduplicated raw objects.
- `NormalizationDispatch`: durable outbox claimed with leases and retried independently.

### Raw, normalized, and facts

- `RawDataObject`: existing required provider/feed/time/hash/object-key fields; unique on
  `(provider, feed_type, content_hash)` and protected against UPDATE/DELETE.
- `NormalizedRecord`: references raw, includes record type, normalization version,
  record key, payload, and is unique on
  `(raw_data_object_id, record_type, normalization_version, record_key)`.
- `NormalizationRejection`: immutable raw/record/error/version evidence.
- Typed facts: `MarketBar`, `NewsArticle`, `SecFiling`, `FinancialFact`,
  `EarningsEvent`, `CorporateAction`, and `DataQualityObservation`.
- Every typed fact references `normalized_record_id`; transitional raw IDs may remain
  while existing data is migrated, but new facts must have normalized lineage.

Prices, amounts, ratios, and derived numeric facts use PostgreSQL `Numeric` and Python
`Decimal`. All timestamps are timezone-aware `timestamptz`/UTC.

## State machine and failure semantics

```text
QUEUED -> RUNNING
RUNNING -> SUCCEEDED | COMPLETED_WITH_GAPS | RETRY_SCHEDULED | FAILED | DEAD_LETTER
RETRY_SCHEDULED -> QUEUED
QUEUED | RETRY_SCHEDULED -> CANCELLED
```

Terminal states cannot reopen. State writes and worker completion require the active
`lease_token + generation`; stale workers are rejected.

Retryable failures are timeouts, network errors, HTTP 429/5xx, and temporary DB/MinIO
failures. Non-retryable failures are 401/403, missing credentials, unsupported dataset,
or invalid Security. Schema drift keeps raw bytes, writes a rejection, and moves the
record to replayable quarantine. Retry scheduling persists the next-attempt time and
does not sleep inside a worker.

MinIO success followed by metadata failure may leave an orphan object. The next attempt
reuses the content-addressed key; an operational sweep reports unreferenced objects but
does not delete them automatically.

## Availability and query policy

- Live Alpaca events: `available_at` is the platform's first observation time.
- SEC: use EDGAR acceptance time when present; also preserve ingestion time.
- Historical news without a provable observation time is `pit_eligible=false`.
- Alpha calendar: each raw CSV observation creates new event versions; its first ingest
  time is availability.
- Amendments and corrected bars append versions. Query-time selection chooses the latest
  version visible at `decision_time`, not the database's current latest row.

Data purposes are explicit:

| Purpose | Market-data policy |
| --- | --- |
| `REALTIME_CONTEXT` | IEX is allowed with `PARTIAL_MARKET`; no consolidated-volume claim |
| `RESEARCH` | SIP required for SIP-dependent technical facts; otherwise emit EvidenceGap and degrade/abstain |
| `REPLAY` | SIP required for price/volume-dependent replay |
| `PAPER_EXECUTION` | SIP required; missing input denies execution or produces `NO_ACTION` |

Overnight data is context-only and cannot enter official volume, default indicators,
paper fills, or historical replay.

## Reconciliation and quality

- IEX and SIP differences are coverage differences, not conflicts.
- Updated bars append a revision linked to the prior visible version.
- SIP minute-to-daily checks deterministically detect missing intervals, duplicates,
  revisions, OHLC inconsistency, and volume mismatch.
- Corporate actions support at least split, cash/stock dividend, spin-off, symbol change,
  and merger/acquisition; unsupported adjustments create gaps rather than silent math.
- ADR ratio and source currency remain explicit; no implicit currency conversion occurs.
- Quality stores raw dimensions: freshness, coverage, provider, delay, and conflict.

SLA thresholds are versioned configuration targets, not measured provider guarantees:

- IEX health uses stream heartbeat/connection lag, not absence of symbol trades.
- SIP freshness is measured relative to the entitlement-declared delay plus configured
  margins; no fixed 15-minute entitlement is assumed.
- Initial operational targets: news degraded/unavailable at 10/30 minutes, SEC at
  15/60 minutes after acceptance during polling coverage, and Alpha schedule at
  36/72 hours.
- SEC is limited internally to 5 requests/second. Alpaca and Alpha limits follow provider
  responses and versioned configuration.

## Security and licensing

- Provider credentials live only in environment variables/local secret stores and
  GitHub Actions secrets. They are never stored in PostgreSQL, MinIO, logs, traces,
  fixtures, reports, or screenshots.
- Logs redact authorization headers, API keys, query credentials, URLs containing
  credentials, and WebSocket authentication messages.
- SEC User-Agent is required and identifies the application/version/contact.
- Adapters expose GET/read-only WebSocket capabilities only.
- Missing credentials produce typed UNAVAILABLE or an explicit live-smoke skip. API mode
  never falls back to Fixture.
- Provider licensing must be re-reviewed before public display, commercial use, or data
  redistribution.

## Test topology and acceptance

```text
domain/property tests
        |
adapter recorded-contract tests
        |
Postgres + MinIO integration tests
        |
worker crash/retry/replay tests
        |
PIT + quality release gates
        |
credential-gated live smoke
        |
make verify (twice for idempotency evidence)
```

Mandatory coverage includes:

- empty-db and upgrade-from-0024 migrations; rollback is inspected but destructive
  downgrade is not run against user data;
- seed and migration idempotency; existing Watchlist configuration is preserved;
- database rejection of UPDATE/DELETE on raw, normalized, typed facts, dead-letter, and
  quality history;
- deterministic deduplication under duplicate/concurrent delivery;
- lease expiry and stale-worker rejection;
- crash points before/after MinIO, raw transaction, dispatch delivery, normalization,
  and cursor advancement;
- PIT property tests for both time predicates and revised facts;
- Decimal/no-naive-time invariants;
- Alpaca REST/WS, SEC JSON/document, and Alpha CSV recorded fixtures;
- pagination, `Retry-After`, 401/403, 429/5xx, schema drift, reconnect, and replay;
- DST, holiday, half-day, historical-news eligibility, IEX/SIP separation, and ADR cases;
- SQL query-count/query-plan checks for the 11-security target universe;
- explicit proof that API mode cannot invoke FixtureAdapter;
- opt-in live smoke only when corresponding credentials and entitlements exist;
- `make verify`, fresh Alembic upgrade, seed, recovery drill, and a second verification
  run with commands/exits recorded in `docs/progress.md`.

## Reuse and migration strategy

Reuse the current Celery/Beat control plane, MinioRawObjectStore, CircuitBreaker,
observability/redaction, fixture catalog, market-bar storage, Watchlist API, and
point-in-time repository seam. Refactor `GovernedHttpProvider` so adapters return raw
batches/events and orchestration owns persistence/retry. Do not build a second provider
stack beside it.

FMP leaves active production routing after the selective override, but its adapter and
historical fixtures remain temporarily for backwards-compatible tests. Their removal is
not part of M7.5.

## Explicitly out of scope

- M8 packaging and interview collateral;
- new product UI or public API contracts;
- new Agent or MCP server;
- options or analyst-target provider ingestion;
- Kafka, provider-specific microservices, multi-region ingestion, or automatic scaling;
- public data redistribution or commercial licensing work;
- live brokerage, broker credentials, real orders, or real funds.

## Release decision

The M7.5 requirements are approved for implementation. This approval freezes the design
but does not claim that provider ingestion exists or that live credentials/entitlements
are configured. RDB-1 starts only from a clean branch based on the latest `main`, follows
TDD, and must enter review before RDB-2 begins.
