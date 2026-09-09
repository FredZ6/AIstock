import os
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from stock_platform.application.evaluation.persistence import persist_evaluation_run
from stock_platform.application.evaluation.runner import run_evaluation
from stock_platform.infrastructure.db.models.tables import (
    eval_metric,
    eval_run,
    regression_gate_result,
)

REPO_ROOT = Path(__file__).parents[4]
DATASET_DIR = REPO_ROOT / "evals" / "datasets"
BASELINE_PATH = REPO_ROOT / "evals" / "baselines" / "eval-v0.2.0.json"


def test_persists_one_idempotent_version_pinned_evaluation_run(
    engine: Engine, tmp_path: Path
) -> None:
    output = tmp_path / "report"
    result = run_evaluation(DATASET_DIR, output, baseline_path=BASELINE_PATH)
    summary_hash = sha256((output / "summary.json").read_bytes()).hexdigest()
    run_id = uuid4()
    created_at = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)

    with engine.connect() as connection:
        transaction = connection.begin()
        first = persist_evaluation_run(
            connection,
            result,
            run_id=run_id,
            summary_hash=summary_hash,
            created_at=created_at,
        )
        second = persist_evaluation_run(
            connection,
            result,
            run_id=run_id,
            summary_hash=summary_hash,
            created_at=created_at,
        )

        row = connection.execute(select(eval_run).where(eval_run.c.id == run_id)).mappings().one()
        metric_count = connection.execute(
            select(func.count()).select_from(eval_metric).where(eval_metric.c.eval_run_id == run_id)
        ).scalar_one()
        gate_count = connection.execute(
            select(func.count())
            .select_from(regression_gate_result)
            .where(regression_gate_result.c.eval_run_id == run_id)
        ).scalar_one()
        transaction.rollback()

    assert first == second == run_id
    assert row["status"] == "PASSED"
    assert row["passed"] is True
    assert row["mode"] == "fixture"
    assert row["dataset_version"] == "eval-v0.2.0"
    assert row["case_count"] == 200
    assert row["data_cutoff"] == datetime(2026, 8, 21, 20, 0, tzinfo=UTC)
    assert row["model_version"] == "fixture-deterministic-v1"
    assert row["prompt_version"] == "offline-eval-v0.2"
    assert row["research_scoring_policy_version"] == "research-scoring-v0.2"
    assert row["risk_policy_version"] == "risk-v0.2"
    assert row["execution_policy_version"] == "execution-v0.2"
    assert row["confidence_policy_version"] == "confidence-v0.2"
    assert row["gate_policy_version"] == "evaluation-gates-v0.2"
    assert row["summary_hash"] == summary_hash
    assert row["created_at"] == created_at
    assert metric_count == len(result.metrics.values) == 38
    assert gate_count == len(result.release_decision.findings) == 18


def test_rejects_naive_persistence_time_before_database_write(
    engine: Engine, tmp_path: Path
) -> None:
    output = tmp_path / "report"
    result = run_evaluation(DATASET_DIR, output, baseline_path=BASELINE_PATH)

    with engine.begin() as connection, pytest.raises(ValueError, match="timezone-aware"):
        persist_evaluation_run(
            connection,
            result,
            run_id=uuid4(),
            summary_hash="a" * 64,
            created_at=datetime(2026, 9, 9, 8, 0),
        )


def test_offline_eval_cli_persists_only_when_database_url_is_explicit(
    engine: Engine, tmp_path: Path
) -> None:
    run_id = uuid4()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPO_ROOT / "backend" / "src")
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_offline_eval.py"),
            "--dataset",
            str(DATASET_DIR),
            "--baseline",
            str(BASELINE_PATH),
            "--output",
            str(tmp_path / "cli-report"),
            "--persist-database-url",
            engine.url.render_as_string(hide_password=False),
            "--run-id",
            str(run_id),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    with engine.connect() as connection:
        row = connection.execute(select(eval_run).where(eval_run.c.id == run_id)).mappings().one()
    assert row["case_count"] == 200
    assert f"persisted evaluation run: {run_id}" in result.stdout
