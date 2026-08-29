# Interview guide

## Architecture decisions

### Why separate ResearchOpinion from PortfolioAction?

A research conclusion describes evidence. An allocation action is constrained by portfolio state,
risk, liquidity, and execution policy. Keeping them separate prevents a bullish narrative from
becoming an order without deterministic authorization.

### Why use both `event_time` and `available_at`?

Event time says when a fact occurred; availability says when the system could know it. Enforcing both
at the decision cutoff prevents look-ahead leakage in research, replay, and paper execution.

### Why PostgreSQL plus MinIO and Redis?

PostgreSQL owns queryable authoritative facts and constraints. MinIO preserves immutable raw bytes by
content hash. Redis transports recoverable work/SSE data but is not the system of record. Durable
outboxes bridge commit-to-dispatch gaps.

### Why can the LLM not place paper orders directly?

Even paper execution affects evaluation and learning. The LLM may propose; deterministic code freezes
inputs, maps opinions to actions, applies RiskPolicy, and creates an intent only when authorized.

### Why require separate approval and activation?

Approval means a human accepts a Candidate Lesson or policy candidate for consideration. Activation
changes the online policy pointer and therefore requires a second explicit, audited action. V1 has no
automatic promotion.

## Likely review questions

- **How is replay deterministic?** Frozen fixtures, versioned policies/prompts/models, UTC cutoffs,
  Decimal arithmetic, stable IDs, and append-only facts.
- **What happens when a provider is down?** Typed failure/degradation, bounded retry/circuit state,
  preserved prior facts, and no API-to-Fixture fallback.
- **How do you prove a claim?** Follow Decision → Thesis → ThesisEvidenceLink → Evidence →
  DerivedMetric → NormalizedRecord → RawDataObject and ToolCall audit.
- **How do you prevent duplicate alerts/fills?** Stable idempotency keys, database constraints,
  serialized validation, durable-first ACK, and transactional outboxes.
- **What do the Eval numbers mean?** Reproducible measurements on the frozen `eval-v0.2.0` corpus.
  They prove release behavior, not live-market skill or investment returns.
- **What remains before production?** Real entitlement-aware provider validation, licensing review,
  deployed SLO evidence, longer Paper Trading observation, security review, and human operations.

## Honest trade-offs

The design favors auditability and safety over low latency or autonomous action. Fixture Mode makes
the demo reproducible but limits external validity. PostgreSQL constraints add migration complexity,
while preventing application-only checks from silently weakening historical facts.
