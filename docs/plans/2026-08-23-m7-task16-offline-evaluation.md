# M7 Task 16 Offline Evaluation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reproducible frozen-fixture evaluation runner that measures the locked L0–L7 quality dimensions, emits raw evidence artifacts, and fails releases only on the approved hard gates.

**Architecture:** The evaluation domain owns immutable case/result/value objects. A deep application module exposes one runner interface that loads validated JSONL cases, computes deterministic aggregate metrics, evaluates versioned hard gates, and writes four reproducible reports. Dataset generation is deterministic and separate from evaluation; CI invokes the same public CLI used locally.

**Tech Stack:** Python 3.12, Pydantic v2, Decimal, JSONL, Pytest, GitHub Actions, existing frozen fixtures and repository verification tooling.

---

## Locked test seams

1. `EvalCase` JSONL interface: invalid timestamps, hashes, money-like decimals, enums, or missing provenance are rejected while loading.
2. Metric interface: known literal confusion matrices and calibration buckets produce exact Decimal results.
3. Release-gate interface: exact boundary, one unit below, and one unit above each threshold behave according to Notion v0.2; portfolio return never blocks by itself.
4. Runner CLI interface: a dataset directory produces `summary.json`, `cases.jsonl`, `junit.xml`, and `report.html`, returns non-zero on a hard-gate failure, and is byte-reproducible for the same inputs.
5. CI workflow interface: PR, nightly, and weekly schedules invoke the same runner with fixture-safe modes and no invented credentials.

### Task 1: Evaluation domain and dataset contract

**Files:**
- Create: `backend/src/stock_platform/domain/evaluation/__init__.py`
- Create: `backend/src/stock_platform/domain/evaluation/cases.py`
- Create: `backend/src/stock_platform/domain/evaluation/results.py`
- Test: `backend/tests/unit/evaluation/test_cases.py`

**Step 1: Write the failing tests**

- Parse one canonical case with an aware UTC `as_of`, pinned fixture/model/prompt/policy versions, seed, capabilities, forbidden tools, expected invariants, raw output, trace, latency, token usage, cost, verdict, and SHA-256 case hash.
- Reject a naive `as_of`, numeric cost, an invalid layer, a mutated hash, duplicate case IDs, and an unknown field.

**Step 2: Verify RED**

Run: `uv run pytest backend/tests/unit/evaluation/test_cases.py -q`

Expected: fail during import because the evaluation domain does not exist.

**Step 3: Implement the minimal domain**

- Use strict frozen Pydantic models and the shared aware-time invariant.
- Keep monetary/cost values as Decimal strings at the JSON seam.
- Canonicalize the payload excluding `case_hash`, then verify SHA-256.
- Expose one `load_cases(paths)` interface that enforces unique IDs.

**Step 4: Verify GREEN**

Run: `uv run pytest backend/tests/unit/evaluation/test_cases.py -q`

Expected: all domain contract tests pass.

### Task 2: Deterministic metrics and calibration

**Files:**
- Create: `backend/src/stock_platform/application/evaluation/__init__.py`
- Create: `backend/src/stock_platform/application/evaluation/metrics.py`
- Test: `backend/tests/unit/evaluation/test_metrics.py`

**Step 1: Write failing literal-example tests**

- Tool precision/recall/F1 and argument-schema validity.
- Research success, evidence coverage, citation precision/recall, conflict recall, freshness, and critical numeric accuracy.
- Directional Accuracy, Thesis Hit Rate, Brier Score, ECE, reliability buckets, and Abstain Accuracy.
- Alert precision/recall/dedup and latency P95.
- Recovery, checkpoint, audit completeness, leakage, unauthorized tool execution, live-trading calls, loop rate, and portfolio/learning measurements.

**Step 2: Verify RED**

Run: `uv run pytest backend/tests/unit/evaluation/test_metrics.py -q`

Expected: fail because the metric interface is absent.

**Step 3: Implement minimal deterministic calculations**

- Use `Decimal` for ratios, probabilities, cost, and portfolio measurements.
- Use a documented nearest-rank percentile for latency.
- Treat zero-denominator metrics explicitly and deterministically.
- Keep calibrated LLM-judge fields separate from deterministic judges; fixture cases use deterministic judges only.

**Step 4: Verify GREEN**

Run: `uv run pytest backend/tests/unit/evaluation/test_metrics.py -q`

Expected: exact worked examples pass.

### Task 3: Versioned hard release gates

**Files:**
- Create: `backend/src/stock_platform/application/evaluation/gates.py`
- Test: `backend/tests/unit/evaluation/test_gates.py`
- Test: `backend/tests/integration/evaluation/test_release_gates.py`

**Step 1: Write boundary-first failing tests**

- Test exact pass/fail behavior at, below, and above every approved threshold.
- Enforce zero leakage, unauthorized success, live-trading calls, and runaway loops.
- Enforce accounting, checkpoint, audit, numeric, schema, evidence, citation, conflict, recovery, and latency gates.
- Prove negative portfolio return, alpha, Sharpe, and win rate remain measured but non-blocking.

**Step 2: Verify RED**

Run: `uv run pytest backend/tests/unit/evaluation/test_gates.py backend/tests/integration/evaluation/test_release_gates.py -q`

Expected: fail because the gate policy is absent.

**Step 3: Implement the minimal gate policy**

- Define one pinned `evaluation-gates-v0.2` policy.
- Return structured pass/fail findings with threshold, observed value, and evidence metric.
- Never call an LLM and never activate or mutate a Policy.

**Step 4: Verify GREEN**

Run: `uv run pytest backend/tests/unit/evaluation backend/tests/integration/evaluation/test_release_gates.py -q`

Expected: all metric and threshold cases pass.

### Task 4: Exactly 200 frozen cases and reproducible report runner

**Files:**
- Create: `backend/src/stock_platform/application/evaluation/runner.py`
- Create: `backend/src/stock_platform/application/evaluation/report.py`
- Create: `scripts/generate_eval_datasets.py`
- Create: `scripts/run_offline_eval.py`
- Create: `evals/datasets/tool.jsonl`
- Create: `evals/datasets/research.jsonl`
- Create: `evals/datasets/evidence.jsonl`
- Create: `evals/datasets/security.jsonl`
- Create: `evals/datasets/alert.jsonl`
- Create: `evals/datasets/portfolio.jsonl`
- Create: `evals/datasets/learning.jsonl`
- Test: `backend/tests/unit/evaluation/test_runner.py`
- Test: `backend/tests/integration/evaluation/test_release_gates.py`

**Step 1: Write failing runner tests**

- Require counts 40/40/30/30/20/20/20, totaling exactly 200 frozen cases.
- Run the same directory twice and assert identical summary/case evidence.
- Require all four report files and a non-zero exit on an injected hard-gate failure.
- Require every summary metric to link to contributing case IDs and hashes.

**Step 2: Verify RED**

Run: `uv run pytest backend/tests/unit/evaluation/test_runner.py backend/tests/integration/evaluation/test_release_gates.py -q`

Expected: fail because datasets and runner do not exist.

**Step 3: Implement generator, runner, and reports**

- Generate only synthetic frozen observations from deterministic templates; label them `fixture`, never live market data.
- Pin dataset/model/prompt/policy versions and random seed in every case.
- Write artifacts atomically in stable case/metric order.
- Include raw outputs, trace, latency, token usage, Decimal-string cost, verdict, case hash, gate policy version, and provenance.
- HTML is a static escaped view of the same summary; JUnit contains one testcase per hard gate.

**Step 4: Generate and verify datasets**

Run: `uv run python scripts/generate_eval_datasets.py --output evals/datasets`

Run: `uv run python scripts/run_offline_eval.py --dataset evals/datasets --output evals/reports/latest`

Expected: both exit 0; `summary.json`, `cases.jsonl`, `junit.xml`, and `report.html` exist and all hard gates pass.

### Task 5: PR, nightly, and weekly CI layers

**Files:**
- Create: `.github/workflows/pr.yml`
- Create: `.github/workflows/nightly.yml`
- Create: `.github/workflows/weekly.yml`
- Modify: `scripts/verify.sh`
- Test: `backend/tests/unit/evaluation/test_ci_workflows.py`

**Step 1: Write failing workflow-contract tests**

- PR runs the fixture evaluation once within a ten-minute job timeout.
- Nightly runs the full fixture suite three times and preserves reports.
- Weekly runs fixture evaluation and an explicitly credential-gated live-provider smoke without asserting prices.
- Actions are SHA-pinned, permissions are read-only, and no live-broker credential or endpoint is present.

**Step 2: Verify RED**

Run: `uv run pytest backend/tests/unit/evaluation/test_ci_workflows.py -q`

Expected: fail because the three workflow files are absent.

**Step 3: Implement workflows and verification hook**

- Reuse locked setup and service steps from `ci.yml`.
- Upload deterministic reports as artifacts.
- Add the fast evaluation unit/integration suite to `make verify`; keep the full 200-case runner explicit in Task 16 acceptance and scheduled jobs.

**Step 4: Verify GREEN**

Run: `uv run pytest backend/tests/unit/evaluation/test_ci_workflows.py -q`

Expected: workflow contracts pass.

### Task 6: Task 16 acceptance and delivery evidence

**Files:**
- Modify: `docs/progress.md`

**Step 1: Run authoritative Task 16 tests**

Run: `uv run pytest backend/tests/unit/evaluation backend/tests/integration/evaluation/test_release_gates.py -q`

Run: `uv run python scripts/run_offline_eval.py --dataset evals/datasets --output evals/reports/latest`

Run: `make verify`

Run: `git diff --check`

**Step 2: Record exact evidence**

- Record commands, exit codes, test counts, report paths, dataset counts/hashes, elapsed time, skips/warnings, and residual risks in `docs/progress.md`.
- Perform Matt `code-review` and repository invariant review; repair every P0/P1/P2 blocker through a new RED/GREEN cycle.

**Step 3: Deliver through GitHub**

- Commit only after local review and all gates pass.
- Push `codex/m7-evaluation`, create a PR linked to FRE-20, wait for CI, re-review the remote diff, and merge only after the explicit quality gate is satisfied.
- Add PR, CI, commit, merge commit, reports, and risks to Notion and Linear; set FRE-20 to Done only after merge.

**Step 4: Continue M7 in order**

- Fast-forward local `main` to the Task 16 merge commit.
- Re-read Task 17, move FRE-21 to In Progress, and create a fresh Task 17 worktree from updated main.
