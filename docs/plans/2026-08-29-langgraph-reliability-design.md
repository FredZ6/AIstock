# LangGraph Reliability Upgrade Design

**Goal:** Make the research and paper-portfolio graphs durable, genuinely parallel, validation-gated, capable of bounded evidence remediation, and demonstrably restart-safe.

## Architecture

Both graphs will accept a LangGraph `BaseCheckpointSaver`. Production workers will construct a `PostgresSaver` from the configured PostgreSQL URL, run its idempotent setup, compile the graph with that saver, and invoke it with `run_id` as the stable LangGraph `thread_id`. Tests will use LangGraph's in-memory saver. Business persistence remains outside checkpoint durability boundaries: terminal graph nodes produce deterministic state, and the graph runner or worker idempotently persists the returned business result. This prevents a completed graph checkpoint from suppressing a business write that was rolled back in another transaction.

Research collection becomes a map/reduce route. A dispatcher emits one `Send` per allowed feed, collection workers fetch independently, and reducers merge results deterministically. Evidence analysis similarly emits one `Send` per evidence item and merges claims. Reducers de-duplicate stable domain identifiers so replay and reflection cannot duplicate state.

After evidence judging, one bounded remediation pass derives feed targets from missing/conflicted evidence, re-fetches only those feeds, normalizes the new evidence, and judges again. The reflection budget remains authoritative and prevents runaway loops.

Citation and numeric verification become a graph gate. A verified result proceeds normally. A failed result is deterministically downgraded to `ABSTAIN`, records explicit warnings, and finishes as `COMPLETED_WITH_LIMITATIONS`; it cannot be represented as an unrestricted completed decision.

## Failure and recovery semantics

- Each invocation uses `configurable.thread_id = run_id`.
- PostgreSQL checkpoints survive worker and process restarts.
- Re-invoking a completed graph returns the checkpointed result and idempotent business persistence prevents duplicates.
- A failure before a node completes resumes from the last committed superstep.
- Stable UUIDs and de-duplicating reducers make repeated supersteps safe.
- Paper-trading persistence remains idempotent and no live-broker path is introduced.

## Testing

Tests will prove each behavior with red-green cycles: stable checkpoint configuration, recovery without repeating completed collection, fan-out/fan-in aggregation, deterministic replay, bounded targeted reflection, validation downgrade, and duplicate-free persistence. Integration coverage will exercise PostgreSQL checkpoint tables when the local database is available. Full completion requires `make verify`, followed by evidence recorded in `docs/progress.md`.

