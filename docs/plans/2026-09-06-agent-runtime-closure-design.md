# Agent Runtime Closure Design

## Goal

Complete one honest, user-visible Research Agent vertical slice. A user can admit a deterministic
research run from the web interface, observe its durable execution, recover the trace after a
refresh or transport interruption, and read the persisted result. This increment does not add a
real LLM provider, manual Portfolio or Weekly Review controls, or any live-broker path.

## Chosen approach

Implement a Research-only vertical slice through the existing control plane:

```text
Research page
  -> Next.js server action
  -> POST /api/v1/research-runs with Idempotency-Key
  -> persisted QUEUED AgentRun
  -> Celery research worker
  -> DailyResearchGraph
  -> PostgreSQL checkpoint and append-only AgentEvent records
  -> same-origin durable SSE proxy
  -> /runs/{run_id} live trace
  -> persisted report and decision lineage
```

This preserves the API as the authority for admission and execution. The browser never calls an
Agent graph directly and never infers durable state from transient client state.

## Scope

### Included

- A symbol input and `Run deterministic research` action on the Research page.
- Server-side construction of aware UTC `decision_time` and `data_cutoff` values.
- One stable idempotency key for each user submission, retained across safe retries.
- Redirect to the admitted run's canonical `/runs/{run_id}` page.
- A same-origin Next.js SSE proxy that forwards the durable `Last-Event-ID` cursor.
- A live Run Trace client that renders persisted events in sequence order.
- Terminal-state retrieval and rendering of the persisted research report.
- Explicit Loading, Empty, Degraded, Failure, and completed-with-limitations behavior.
- Runtime and browser verification against FastAPI, Celery, Redis, PostgreSQL, and MinIO where the
  existing execution path requires them.

### Excluded

- Real OpenAI, Anthropic, or other model inference.
- Claims that deterministic Planner, Analyst, or Writer nodes are LLM-generated.
- Manual Portfolio Decision or Weekly Review execution controls.
- Live brokerage, real-money execution, automatic policy activation, or notifications.
- Fixture fallback in API mode.

## User experience

The Research page presents a compact run control beside the current symbol context. It identifies
the operation as a `Deterministic Research Workflow`. Submission disables duplicate interaction,
shows admission progress, and then navigates to the new run.

The Run Trace page prioritizes run status, current node, elapsed time, retries, degradations,
checkpoint count, data cutoff, and the durable resume cursor. The chronological event list is built
only from persisted AgentEvent facts. At a terminal state, the page renders the persisted
ResearchOpinion, confidence, thesis, linked evidence, gaps, citation verification, and deterministic
DecisionDiff.

`ABSTAIN` and `COMPLETED_WITH_LIMITATIONS` are valid, visible outcomes. They are not relabelled as a
positive recommendation.

## Data and control boundaries

- Run creation continues to use the existing locked REST request and response contracts.
- The server action generates aware UTC timestamps and rejects invalid symbols before admission.
- The idempotency key is opaque and contains no user or credential material.
- The backend remains responsible for task admission limits, persistence, Celery dispatch, version
  pins, and point-in-time enforcement.
- The browser receives backend data through Next.js server boundaries. No provider credential or
  private backend URL is exposed to client code.
- The SSE proxy streams bytes without reconstructing events and forwards `Last-Event-ID` on
  reconnect. The client rejects cross-run events, non-monotonic sequences, collisions, and naive
  timestamps through the existing durable SSE reducer.
- Report rendering uses only the run's persisted report endpoint and related persisted contracts.

## Error handling and recovery

- Admission validation errors stay on the Research page with a specific actionable message.
- `429` admission limits expose a retryable busy state without creating a second run.
- API unavailability produces Failure; partial provider evidence produces Degraded or
  completed-with-limitations; neither path imports Fixture data.
- A disconnected SSE client reconnects to the same run with its last durable event ID.
- A page refresh reloads persisted run metadata before resuming the stream.
- A restarted API may replay persisted events; the client deduplicates identical events and rejects
  sequence collisions.
- A restarted worker resumes from the PostgreSQL LangGraph checkpoint and idempotent business
  persistence prevents duplicate decisions.
- Terminal run failure remains inspectable and does not automatically submit another run.

## Testing and acceptance

Each behavior follows a RED-GREEN-refactor cycle. Acceptance requires:

1. Repeated submission with one idempotency key produces one AgentRun.
2. Celery executes the admitted DailyResearchGraph and persists terminal state.
3. AgentEvent sequences are monotonic and resumable with `Last-Event-ID`.
4. Refresh, SSE disconnect, and API restart continue the same run trace.
5. Checkpoint recovery does not repeat completed collection or duplicate immutable facts.
6. The terminal page displays the persisted report and decision lineage.
7. Worker, API, and provider failures never fall back to Fixture data.
8. Desktop and mobile keyboard flows pass, with no serious or critical owned-DOM axe violations.
9. The focused runtime suite and full `make verify` pass.
10. Commands, exit codes, counts, limitations, and artifact paths are recorded in
    `docs/progress.md`.

## Delivery sequence

Work continues on `codex/frontend-experience-closure`, which is based directly on the current
`main` and contains the approved frontend experience work. The runtime closure will be implemented
as small ordered commits after this design and its executable plan. No push, PR, merge, or external
tracker status change is implied by the local implementation work.
