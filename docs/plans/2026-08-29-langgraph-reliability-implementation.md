# LangGraph Reliability Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add durable PostgreSQL graph recovery, real parallel map/reduce stages, hard validation gating, evidence remediation, and recovery-focused tests.

**Architecture:** Inject a native LangGraph checkpointer into both graphs and use the run ID as the thread ID. Convert research collection and analysis to dynamic `Send` fan-out with deterministic reducers, make reflection loop through targeted collection, and separate terminal state construction from idempotent business persistence.

**Tech Stack:** Python 3.12, LangGraph, langgraph-checkpoint-postgres, psycopg, SQLAlchemy, pytest, Celery.

---

### Task 1: Checkpoint configuration and lifecycle

**Files:**
- Modify: `pyproject.toml`
- Modify: `backend/src/stock_platform/agents/research/graph.py`
- Modify: `backend/src/stock_platform/agents/portfolio/graph.py`
- Create: `backend/src/stock_platform/agents/checkpointing.py`
- Test: `backend/tests/unit/agents/test_checkpointing.py`

1. Write tests asserting both graphs compile with an injected saver and invoke with a stable `thread_id` equal to `run_id`.
2. Run the focused tests and confirm they fail because checkpointer injection is absent.
3. Add `langgraph-checkpoint-postgres`, a PostgreSQL saver context factory, constructor injection, and invocation configuration.
4. Re-run the focused tests and existing graph route tests.

### Task 2: Real collection fan-out/fan-in

**Files:**
- Modify: `backend/src/stock_platform/agents/research/state.py`
- Modify: `backend/src/stock_platform/agents/research/graph.py`
- Modify: `backend/src/stock_platform/agents/research/nodes/core.py`
- Test: `backend/tests/unit/agents/research/test_graph_parallelism.py`

1. Write a blocking provider test proving two collection branches overlap and all responses merge in deterministic feed order.
2. Confirm the test fails with the current sequential `for` loop.
3. Add collection task state, a dispatcher returning `Send` objects, one-feed worker nodes, and deterministic de-duplicating reducers.
4. Re-run parallelism and route tests.

### Task 3: Real analyst fan-out/fan-in

**Files:**
- Modify: `backend/src/stock_platform/agents/research/state.py`
- Modify: `backend/src/stock_platform/agents/research/graph.py`
- Modify: `backend/src/stock_platform/agents/research/nodes/core.py`
- Test: `backend/tests/unit/agents/research/test_graph_parallelism.py`

1. Write a graph test proving every evidence item passes through an independently dispatched analyst branch and merged claims are deterministic and duplicate-free.
2. Confirm failure against the current tuple comprehension.
3. Add evidence dispatch and single-evidence analysis nodes using `Send` and stable claim reducers.
4. Re-run research tests.

### Task 4: Bounded evidence remediation

**Files:**
- Modify: `backend/src/stock_platform/agents/research/state.py`
- Modify: `backend/src/stock_platform/agents/research/graph.py`
- Modify: `backend/src/stock_platform/agents/research/nodes/core.py`
- Test: `backend/tests/unit/agents/research/test_graph_routes.py`

1. Write tests showing gaps/conflicts select targeted feeds, trigger exactly one re-fetch, re-run normalization/judging, and never exceed the reflection budget.
2. Confirm the tests fail because `reflect` only increments a counter.
3. Make reflection derive collection targets and route back to the fan-out stage; clear or de-duplicate transient judging state as required.
4. Re-run route, fallback, and abstention tests.

### Task 5: Citation and numeric validation gate

**Files:**
- Modify: `backend/src/stock_platform/agents/research/graph.py`
- Modify: `backend/src/stock_platform/agents/research/nodes/core.py`
- Test: `backend/tests/unit/agents/research/test_validation_gate.py`

1. Write a test with invalid citation/numeric evidence asserting the persisted opinion is `ABSTAIN` and status is `COMPLETED_WITH_LIMITATIONS`.
2. Confirm it fails because the graph always routes to persistence.
3. Add a conditional validation edge and deterministic downgrade node with explicit warnings.
4. Re-run all research tests.

### Task 6: Restart safety and persistence boundary

**Files:**
- Modify: `backend/src/stock_platform/agents/research/graph.py`
- Modify: `backend/src/stock_platform/workers/research_tasks.py`
- Modify: `backend/src/stock_platform/workers/portfolio_tasks.py`
- Test: `backend/tests/unit/agents/research/test_checkpoint_recovery.py`
- Test: `backend/tests/integration/api/test_worker_execution.py`

1. Write a failure-injection test that fails after collection, recreates the graph with the same saver/run ID, and proves completed provider calls are not repeated.
2. Add repeated execution tests proving stable results and a single business persistence effect.
3. Confirm failures before changing the persistence boundary.
4. Make the research terminal node pure and perform idempotent result persistence after invocation; wire PostgreSQL saver contexts in both workers.
5. Re-run recovery and worker tests.

### Task 7: Full verification and evidence

**Files:**
- Modify: `docs/progress.md`

1. Run focused unit and integration tests.
2. Run `make verify`.
3. Record exact commands, pass counts, and any environment limitations in `docs/progress.md`.
4. Inspect the final diff to ensure no live-broker path, naive datetime, float money, or unrelated frontend change was introduced.
