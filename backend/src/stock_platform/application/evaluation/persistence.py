"""Atomic append-only persistence for completed offline evaluation evidence."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from stock_platform.application.evaluation.runner import EvaluationRun
from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.db.models.tables import (
    eval_metric,
    eval_run,
    regression_gate_result,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _single(values: set[str], name: str) -> str:
    if len(values) != 1:
        raise ValueError(f"evaluation run must pin exactly one {name}")
    return next(iter(values))


def persist_evaluation_run(
    connection: Connection,
    run: EvaluationRun,
    *,
    run_id: UUID,
    summary_hash: str,
    created_at: datetime,
) -> UUID:
    """Persist one reproducible run and its normalized metric/gate evidence."""
    persisted_at = require_aware(created_at).astimezone(UTC)
    if not _SHA256.fullmatch(summary_hash):
        raise ValueError("summary_hash must be a lowercase SHA-256 digest")
    if not run.cases:
        raise ValueError("evaluation run must contain cases")

    dataset_version = _single({case.dataset_version for case in run.cases}, "dataset version")
    model_version = _single({case.model_version for case in run.cases}, "model version")
    prompt_version = _single({case.prompt_version for case in run.cases}, "prompt version")
    research_policy = _single(
        {case.policy_versions.research_scoring for case in run.cases},
        "research scoring policy version",
    )
    risk_policy = _single({case.policy_versions.risk for case in run.cases}, "risk policy version")
    execution_policy = _single(
        {case.policy_versions.execution for case in run.cases},
        "execution policy version",
    )
    confidence_policy = _single(
        {case.policy_versions.confidence for case in run.cases},
        "confidence policy version",
    )
    passed = run.release_decision.passed
    values = {
        "id": run_id,
        "status": "PASSED" if passed else "FAILED",
        "passed": passed,
        "mode": "fixture",
        "dataset_version": dataset_version,
        "case_count": len(run.cases),
        "data_cutoff": max(case.as_of for case in run.cases),
        "model_version": model_version,
        "prompt_version": prompt_version,
        "research_scoring_policy_version": research_policy,
        "risk_policy_version": risk_policy,
        "execution_policy_version": execution_policy,
        "confidence_policy_version": confidence_policy,
        "gate_policy_version": run.release_decision.policy_version,
        "summary_hash": summary_hash,
        "created_at": persisted_at,
    }
    inserted_id = connection.execute(
        insert(eval_run)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[eval_run.c.id])
        .returning(eval_run.c.id)
    ).scalar_one_or_none()
    if inserted_id is None:
        existing_hash = connection.execute(
            select(eval_run.c.summary_hash).where(eval_run.c.id == run_id)
        ).scalar_one()
        if existing_hash != summary_hash:
            raise ValueError("eval run id already refers to different evidence")
        return run_id

    connection.execute(
        insert(eval_metric),
        [
            {
                "eval_run_id": run_id,
                "metric_name": name,
                "metric_value": value,
                "case_ids": [case.case_id for case in run.evidence[name]],
                "case_hashes": [case.case_hash for case in run.evidence[name]],
                "created_at": persisted_at,
            }
            for name, value in sorted(run.metrics.values.items())
        ],
    )
    connection.execute(
        insert(regression_gate_result),
        [
            {
                "eval_run_id": run_id,
                "metric_name": finding.metric,
                "comparison": finding.comparison.value,
                "threshold": finding.threshold,
                "observed": finding.observed,
                "passed": finding.passed,
                "reason": finding.reason,
                "created_at": persisted_at,
            }
            for finding in run.release_decision.findings
        ],
    )
    return run_id
