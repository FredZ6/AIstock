# GitHub Actions CI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a least-privilege GitHub Actions workflow that runs the repository's complete Fixture Mode verification gate on pull requests and `main`.

**Architecture:** A single Ubuntu `verify` job provisions the locked Python/Web runtimes and reuses the existing Docker Compose and Make targets. A small contract test guards the workflow against accidental removal of triggers, services, migration, safety boundaries, or the authoritative `make verify` command.

**Tech Stack:** GitHub Actions, Ubuntu, Docker Compose, Python 3.12, uv, Node.js 22, pnpm 11, Pytest.

---

### Task 1: Lock the CI workflow contract

**Files:**
- Create: `backend/tests/contract/ci/test_github_actions.py`

**Step 1: Write the failing test**

Add a test that reads `.github/workflows/ci.yml` and asserts:

- pull requests and `main` pushes are configured;
- `workflow_dispatch`, `contents: read`, concurrency cancellation, and Ubuntu are present;
- Python 3.12, Node 22, pnpm 11, and uv setup are present;
- PostgreSQL, Redis, and MinIO start through Docker Compose;
- Alembic upgrades a fresh database before `make verify`;
- Fixture Mode is explicit and no live-provider or broker credential is configured.

**Step 2: Run the test to verify it fails**

Run: `uv run pytest backend/tests/contract/ci/test_github_actions.py -q`

Expected: FAIL because `.github/workflows/ci.yml` does not exist.

**Step 3: Record RED evidence**

Append the command, exit code, and expected missing-workflow failure to `docs/progress.md`.

### Task 2: Add the minimal workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Implement the workflow**

Create one `verify` job with:

- PR-to-main, push-to-main, and manual triggers;
- `contents: read` and per-ref concurrency cancellation;
- checkout, Python 3.12, uv, Node 22, and pnpm 11 setup;
- dependency caching through the setup actions;
- `make bootstrap`;
- `docker compose up -d --wait postgres redis minio`;
- `uv run alembic -c backend/alembic.ini upgrade head`;
- `make verify`;
- failure-only Docker status/log collection and unconditional Compose teardown.

**Step 2: Run the focused test to verify it passes**

Run: `uv run pytest backend/tests/contract/ci/test_github_actions.py -q`

Expected: PASS.

**Step 3: Run related contract tests**

Run: `uv run pytest backend/tests/contract -q`

Expected: PASS with only explicitly credential-gated skips, if any.

### Task 3: Verify and deliver

**Files:**
- Modify: `docs/progress.md`

**Step 1: Run the full local gate**

Run: `make verify`

Expected: exit 0.

**Step 2: Record GREEN and final evidence**

Append focused and full command results, counts, and known risks to `docs/progress.md`.

**Step 3: Review and commit only intended files**

Run: `git diff --check`, inspect the exact diff, stage only the two plan files, CI contract test,
workflow, and progress log, then commit with `ci: add GitHub Actions verification gate`.

**Step 4: Push and verify GitHub**

Push `codex/m6-control-plane`, confirm PR #5 contains the commit, and wait for the `verify` check.
If it fails, use `superpowers:systematic-debugging` and `gh-fix-ci` before changing code.
