"""PostgreSQL-authoritative run admission shared by API and schedulers."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, create_engine, func, insert, select, text, update
from sqlalchemy.engine import RowMapping

from stock_platform.infrastructure.db.models.tables import agent_event, agent_run, policy_control
from stock_platform.infrastructure.observability.context import (
    CorrelationContext,
    correlation_scope,
)

RunType = Literal["RESEARCH", "PORTFOLIO", "ALERT_MONITOR", "WEEKLY_REVIEW"]
RunWork = Callable[[Connection, RowMapping, "RunControl"], None]

RUN_PINS: dict[RunType, tuple[str, str]] = {
    "RESEARCH": ("prompt-v1", "fixture-v1"),
    "PORTFOLIO": ("portfolio-prompt-v1", "fixture-proposer-v1"),
    "ALERT_MONITOR": ("deterministic-alert-v1", "none"),
    "WEEKLY_REVIEW": ("weekly-review-prompt-v1", "model-v1"),
}
DEFAULT_POLICY_PINS = {
    "RESEARCH_SCORING": "research-v1",
    "RISK": "risk-v1",
    "EXECUTION": "execution-v1",
    "CONFIDENCE": "confidence-v1",
}


class IdempotencyConflict(RuntimeError):
    pass


class RunAdmissionLimit(RuntimeError):
    pass


class RunCancelled(RuntimeError):
    pass


class RunLeaseLost(RuntimeError):
    pass


class RetryableRunError(RuntimeError):
    pass


class RunInputUnavailable(RetryableRunError):
    """A frozen run may be retried because a required durable input is not committed yet."""

    pass


@dataclass(frozen=True, slots=True)
class AdmittedRun:
    id: UUID
    run_type: RunType
    status: str
    symbol: str | None
    decision_time: datetime
    data_cutoff: datetime
    replayed: bool


def admit_run(
    connection: Connection,
    *,
    max_active_runs: int,
    run_type: RunType,
    idempotency_key: str,
    payload: dict[str, Any],
    symbol: str | None,
    decision_time: datetime,
    data_cutoff: datetime,
    correlation_id: UUID | None = None,
) -> AdmittedRun:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    request_hash = sha256(encoded.encode()).hexdigest()
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('agent-run-admission'))"))
    existing = (
        connection.execute(select(agent_run).where(agent_run.c.idempotency_key == idempotency_key))
        .mappings()
        .one_or_none()
    )
    if existing is not None:
        if existing["request_hash"] != request_hash:
            raise IdempotencyConflict
        return _admitted(existing, replayed=True)
    active = connection.execute(
        select(func.count())
        .select_from(agent_run)
        .where(agent_run.c.status.in_(("QUEUED", "RUNNING")))
    ).scalar_one()
    if active >= max_active_runs:
        raise RunAdmissionLimit
    policy_pins = dict(DEFAULT_POLICY_PINS)
    active_policies = connection.execute(
        select(policy_control.c.policy_kind, policy_control.c.active_version).where(
            policy_control.c.policy_kind.in_(tuple(DEFAULT_POLICY_PINS))
        )
    ).all()
    policy_pins.update({str(kind): str(version) for kind, version in active_policies})
    row = (
        connection.execute(
            insert(agent_run)
            .values(
                run_type=run_type,
                correlation_id=correlation_id or uuid4(),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                request_payload=payload,
                symbol=symbol,
                decision_time=decision_time,
                data_cutoff=data_cutoff,
                status="QUEUED",
                research_scoring_policy_version=policy_pins["RESEARCH_SCORING"],
                risk_policy_version=policy_pins["RISK"],
                execution_policy_version=policy_pins["EXECUTION"],
                confidence_policy_version=policy_pins["CONFIDENCE"],
                prompt_version=RUN_PINS[run_type][0],
                model_version=RUN_PINS[run_type][1],
            )
            .returning(agent_run)
        )
        .mappings()
        .one()
    )
    return _admitted(row, replayed=False)


def _admitted(row: Any, *, replayed: bool) -> AdmittedRun:
    return AdmittedRun(
        id=row["id"],
        run_type=row["run_type"],
        status=row["status"],
        symbol=row["symbol"],
        decision_time=row["decision_time"],
        data_cutoff=row["data_cutoff"],
        replayed=replayed,
    )


def _next_event_sequence(connection: Connection, run_id: UUID) -> int:
    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:run_id))"), {"run_id": str(run_id)}
    )
    latest = connection.execute(
        select(func.coalesce(func.max(agent_event.c.sequence), 0)).where(
            agent_event.c.run_id == run_id
        )
    ).scalar_one()
    return int(latest) + 1


def append_run_event(
    connection: Connection,
    run_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    correlation_id = connection.execute(
        select(agent_run.c.correlation_id).where(agent_run.c.id == run_id)
    ).scalar_one()
    connection.execute(
        insert(agent_event).values(
            run_id=run_id,
            correlation_id=correlation_id,
            sequence=_next_event_sequence(connection, run_id),
            event_type=event_type,
            payload=payload,
        )
    )


class RunControl:
    """Small durable boundary used by graph nodes for events and cancellation."""

    def __init__(self, database_url: str, run_id: UUID, attempt: int) -> None:
        self._engine = create_engine(database_url)
        self._run_id = run_id
        self._attempt = attempt

    def close(self) -> None:
        self._engine.dispose()

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._engine.begin() as connection:
            status, attempt = connection.execute(
                select(agent_run.c.status, agent_run.c.attempt_count)
                .where(agent_run.c.id == self._run_id)
                .with_for_update()
            ).one()
            if status == "CANCELLED":
                raise RunCancelled
            if status != "RUNNING" or attempt != self._attempt:
                raise RunLeaseLost
            append_run_event(connection, self._run_id, event_type, payload)

    def node_completed(self, node: str) -> None:
        self.emit("node.completed", {"node": node, "status": "COMPLETED"})


def _claim_run(engine: Any, run_id: UUID, expected_type: RunType) -> tuple[RowMapping, int] | None:
    with engine.begin() as connection:
        row = (
            connection.execute(select(agent_run).where(agent_run.c.id == run_id).with_for_update())
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"agent run not found: {run_id}")
        if row["run_type"] != expected_type:
            raise ValueError("agent run type does not match worker")
        if row["status"] != "QUEUED":
            return None
        if row["attempt_count"] >= row["max_attempts"]:
            return None
        claimed_attempt = int(row["attempt_count"]) + 1
        connection.execute(
            update(agent_run)
            .where(agent_run.c.id == run_id)
            .values(
                status="RUNNING",
                attempt_count=agent_run.c.attempt_count + 1,
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=15),
                updated_at=func.now(),
            )
        )
        append_run_event(
            connection,
            run_id,
            "run.started",
            {"run_type": expected_type, "attempt": claimed_attempt},
        )
        return cast(RowMapping, row), claimed_attempt


def _finish_failure(engine: Any, run_id: UUID, attempt: int, exception: Exception) -> str:
    with engine.begin() as connection:
        row = (
            connection.execute(select(agent_run).where(agent_run.c.id == run_id).with_for_update())
            .mappings()
            .one()
        )
        if row["status"] == "CANCELLED":
            return "CANCELLED"
        if row["status"] != "RUNNING" or row["attempt_count"] != attempt:
            return "LEASE_LOST"
        retryable = isinstance(exception, RetryableRunError)
        exhausted = row["attempt_count"] >= row["max_attempts"]
        status = "QUEUED" if retryable and not exhausted else "FAILED"
        connection.execute(
            update(agent_run)
            .where(agent_run.c.id == run_id)
            .values(
                status=status,
                lease_expires_at=None,
                last_error={"type": type(exception).__name__, "message": "worker failed"},
                updated_at=func.now(),
            )
        )
        append_run_event(
            connection,
            run_id,
            "run.retry_scheduled" if status == "QUEUED" else "run.failed",
            {"attempt": row["attempt_count"], "status": status},
        )
        return status


def execute_run(
    database_url: str,
    run_id: UUID,
    expected_type: RunType,
    work: RunWork,
) -> bool:
    engine = create_engine(database_url)
    control: RunControl | None = None
    try:
        claim = _claim_run(engine, run_id, expected_type)
        if claim is None:
            return False
        row, attempt = claim
        control = RunControl(database_url, run_id, attempt)
        try:
            with engine.begin() as connection:
                context = CorrelationContext(
                    correlation_id=row["correlation_id"],
                    run_id=run_id,
                )
                with correlation_scope(context):
                    work(connection, row, control)
                completed = connection.execute(
                    update(agent_run)
                    .where(
                        agent_run.c.id == run_id,
                        agent_run.c.status == "RUNNING",
                        agent_run.c.attempt_count == attempt,
                    )
                    .values(status="COMPLETED", lease_expires_at=None, updated_at=func.now())
                )
                if completed.rowcount != 1:
                    current_status = connection.execute(
                        select(agent_run.c.status).where(agent_run.c.id == run_id)
                    ).scalar_one()
                    if current_status == "CANCELLED":
                        raise RunCancelled
                    raise RunLeaseLost
                append_run_event(connection, run_id, "run.completed", {"status": "COMPLETED"})
            return True
        except RunLeaseLost:
            return False
        except RunCancelled:
            with engine.begin() as connection:
                already_recorded = connection.execute(
                    select(func.count())
                    .select_from(agent_event)
                    .where(
                        agent_event.c.run_id == run_id,
                        agent_event.c.event_type == "run.cancelled",
                    )
                ).scalar_one()
                if not already_recorded:
                    append_run_event(connection, run_id, "run.cancelled", {"status": "CANCELLED"})
            return False
        except Exception as exception:
            failure_status = _finish_failure(engine, run_id, attempt, exception)
            if failure_status in {"CANCELLED", "LEASE_LOST"}:
                return False
            raise
    finally:
        if control is not None:
            control.close()
        engine.dispose()
