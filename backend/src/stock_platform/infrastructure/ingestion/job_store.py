"""Short-transaction PostgreSQL store for durable ingestion work."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from stock_platform.application.ingestion.jobs import IngestionJobSpec, IngestionLease
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    FeedType,
    IngestionErrorClass,
    IngestionJobState,
    IngestionRequest,
)
from stock_platform.infrastructure.db.models.tables import (
    ingestion_attempt,
    ingestion_cursor,
    ingestion_dead_letter,
    ingestion_job,
)


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


def _job_request(spec: IngestionJobSpec) -> IngestionRequest:
    return IngestionRequest(
        {
            "request": spec.request.canonical_payload,
            "provider": spec.provider,
            "dataset": spec.dataset,
            "window_start": spec.window_start,
            "window_end": spec.window_end,
            "purpose": spec.purpose,
            "policy_version": spec.policy_version,
            "max_attempts": spec.max_attempts,
        }
    )


class IngestionJobStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def enqueue(self, spec: IngestionJobSpec, *, now: datetime) -> UUID:
        queued_at = require_aware(now).astimezone(UTC)
        job_request = _job_request(spec)
        with self._engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:request_hash))"),
                {"request_hash": job_request.request_hash},
            )
            existing = connection.execute(
                select(ingestion_job.c.id).where(
                    ingestion_job.c.request_hash == job_request.request_hash,
                    ingestion_job.c.state.in_(("QUEUED", "RUNNING", "RETRY_SCHEDULED")),
                )
            ).scalar_one_or_none()
            if existing is not None:
                return cast(UUID, existing)
            return cast(
                UUID,
                connection.execute(
                    insert(ingestion_job)
                    .values(
                        request_hash=job_request.request_hash,
                        request_payload=_plain_json(job_request.canonical_payload),
                        provider=spec.provider,
                        dataset=spec.dataset.value,
                        window_start=spec.window_start,
                        window_end=spec.window_end,
                        purpose=spec.purpose.value,
                        state=IngestionJobState.QUEUED.value,
                        max_attempts=spec.max_attempts,
                        policy_version=spec.policy_version,
                        updated_at=queued_at,
                        created_at=queued_at,
                    )
                    .returning(ingestion_job.c.id)
                ).scalar_one(),
            )

    def claim(
        self,
        job_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        lease_for: timedelta,
    ) -> IngestionLease | None:
        claimed_at = require_aware(now).astimezone(UTC)
        if lease_for <= timedelta(0):
            raise ValueError("lease_for must be positive")
        token = uuid4()
        expires_at = claimed_at + lease_for
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    update(ingestion_job)
                    .where(
                        ingestion_job.c.id == job_id,
                        ingestion_job.c.state == IngestionJobState.QUEUED.value,
                        ingestion_job.c.attempt_count < ingestion_job.c.max_attempts,
                    )
                    .values(
                        state=IngestionJobState.RUNNING.value,
                        attempt_count=ingestion_job.c.attempt_count + 1,
                        lease_token=token,
                        lease_generation=ingestion_job.c.lease_generation + 1,
                        lease_owner=worker_id,
                        lease_expires_at=expires_at,
                        attempt_started_at=claimed_at,
                        updated_at=claimed_at,
                    )
                    .returning(ingestion_job.c.lease_generation)
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return IngestionLease(job_id, token, int(row["lease_generation"]), expires_at)

    def heartbeat(
        self,
        lease: IngestionLease,
        *,
        now: datetime,
        lease_for: timedelta,
    ) -> bool:
        heartbeat_at = require_aware(now).astimezone(UTC)
        if lease_for <= timedelta(0):
            raise ValueError("lease_for must be positive")
        with self._engine.begin() as connection:
            result = connection.execute(
                update(ingestion_job)
                .where(*self._lease_predicates(lease, heartbeat_at))
                .values(
                    lease_expires_at=heartbeat_at + lease_for,
                    updated_at=heartbeat_at,
                )
            )
            return result.rowcount == 1

    def complete(
        self,
        lease: IngestionLease,
        *,
        now: datetime,
        with_gaps: bool = False,
    ) -> bool:
        target = IngestionJobState.COMPLETED_WITH_GAPS if with_gaps else IngestionJobState.SUCCEEDED
        return self._finish(lease, target, now=now)

    def schedule_retry(
        self,
        lease: IngestionLease,
        *,
        error_class: IngestionErrorClass | str,
        error_detail: dict[str, object],
        next_attempt_at: datetime,
        now: datetime,
    ) -> bool:
        retry_at = require_aware(next_attempt_at).astimezone(UTC)
        finished_at = require_aware(now).astimezone(UTC)
        if retry_at <= finished_at:
            raise ValueError("next_attempt_at must be after now")
        return self._finish(
            lease,
            IngestionJobState.RETRY_SCHEDULED,
            now=finished_at,
            error_class=IngestionErrorClass(error_class).value,
            error_detail=error_detail,
            next_attempt_at=retry_at,
        )

    def dead_letter(
        self,
        lease: IngestionLease,
        *,
        error_class: IngestionErrorClass | str,
        error_detail: dict[str, object],
        now: datetime,
    ) -> bool:
        return self._finish(
            lease,
            IngestionJobState.DEAD_LETTER,
            now=now,
            error_class=IngestionErrorClass(error_class).value,
            error_detail=error_detail,
            dead_letter=True,
        )

    def fail(
        self,
        lease: IngestionLease,
        *,
        error_class: IngestionErrorClass | str,
        error_detail: dict[str, object],
        now: datetime,
    ) -> bool:
        return self._finish(
            lease,
            IngestionJobState.FAILED,
            now=now,
            error_class=IngestionErrorClass(error_class).value,
            error_detail=error_detail,
        )

    def cancel(self, job_id: UUID, *, now: datetime) -> bool:
        cancelled_at = require_aware(now).astimezone(UTC)
        with self._engine.begin() as connection:
            result = connection.execute(
                update(ingestion_job)
                .where(
                    ingestion_job.c.id == job_id,
                    ingestion_job.c.state.in_(("QUEUED", "RETRY_SCHEDULED")),
                )
                .values(
                    state=IngestionJobState.CANCELLED.value,
                    next_attempt_at=None,
                    completed_at=cancelled_at,
                    updated_at=cancelled_at,
                )
            )
            return result.rowcount == 1

    def requeue_due(self, *, now: datetime) -> int:
        cutoff = require_aware(now).astimezone(UTC)
        with self._engine.begin() as connection:
            result = connection.execute(
                update(ingestion_job)
                .where(
                    ingestion_job.c.state == IngestionJobState.RETRY_SCHEDULED.value,
                    ingestion_job.c.next_attempt_at <= cutoff,
                    ingestion_job.c.attempt_count < ingestion_job.c.max_attempts,
                )
                .values(
                    state=IngestionJobState.QUEUED.value,
                    next_attempt_at=None,
                    updated_at=cutoff,
                )
            )
            return int(result.rowcount)

    def recover_expired(self, *, now: datetime) -> int:
        recovered_at = require_aware(now).astimezone(UTC)
        recovered = 0
        with self._engine.begin() as connection:
            rows = (
                connection.execute(
                    select(ingestion_job)
                    .where(
                        ingestion_job.c.state == IngestionJobState.RUNNING.value,
                        ingestion_job.c.lease_expires_at <= recovered_at,
                    )
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            for row in rows:
                exhausted = int(row["attempt_count"]) >= int(row["max_attempts"])
                target = (
                    IngestionJobState.DEAD_LETTER
                    if exhausted
                    else IngestionJobState.RETRY_SCHEDULED
                )
                error_detail = {"reason": "lease_expired"}
                connection.execute(
                    insert(ingestion_attempt).values(
                        job_id=row["id"],
                        attempt_number=row["attempt_count"],
                        lease_generation=row["lease_generation"],
                        worker_id=row["lease_owner"],
                        started_at=row["attempt_started_at"],
                        finished_at=recovered_at,
                        outcome=target.value,
                        error_class="TIMEOUT",
                        error_detail=error_detail,
                    )
                )
                if exhausted:
                    connection.execute(
                        insert(ingestion_dead_letter).values(
                            job_id=row["id"],
                            attempt_number=row["attempt_count"],
                            error_class="TIMEOUT",
                            error_detail=error_detail,
                            created_at=recovered_at,
                        )
                    )
                connection.execute(
                    update(ingestion_job)
                    .where(
                        ingestion_job.c.id == row["id"],
                        ingestion_job.c.state == IngestionJobState.RUNNING.value,
                        ingestion_job.c.lease_generation == row["lease_generation"],
                    )
                    .values(
                        state=target.value,
                        lease_token=None,
                        lease_owner=None,
                        lease_expires_at=None,
                        attempt_started_at=None,
                        next_attempt_at=None if exhausted else recovered_at,
                        completed_at=recovered_at if exhausted else None,
                        updated_at=recovered_at,
                    )
                )
                recovered += 1
        return recovered

    def advance_cursor(
        self,
        *,
        provider: str,
        dataset: FeedType,
        scope_key: str,
        expected_generation: int,
        cursor: dict[str, object],
        watermark: datetime,
        now: datetime,
        lease: IngestionLease | None = None,
    ) -> bool:
        checked_watermark = require_aware(watermark).astimezone(UTC)
        changed_at = require_aware(now).astimezone(UTC)
        if expected_generation < 0:
            raise ValueError("expected_generation must not be negative")
        with self._engine.begin() as connection:
            if lease is not None:
                lease_valid = connection.execute(
                    select(ingestion_job.c.id)
                    .where(*self._lease_predicates(lease, changed_at))
                    .with_for_update()
                ).scalar_one_or_none()
                if lease_valid is None:
                    return False
            if expected_generation == 0:
                inserted = connection.execute(
                    pg_insert(ingestion_cursor)
                    .values(
                        provider=provider,
                        dataset=dataset.value,
                        scope_key=scope_key,
                        cursor_payload=cursor,
                        watermark=checked_watermark,
                        generation=1,
                        updated_at=changed_at,
                        created_at=changed_at,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            ingestion_cursor.c.provider,
                            ingestion_cursor.c.dataset,
                            ingestion_cursor.c.scope_key,
                        ]
                    )
                    .returning(ingestion_cursor.c.id)
                ).scalar_one_or_none()
                return inserted is not None
            updated = connection.execute(
                update(ingestion_cursor)
                .where(
                    ingestion_cursor.c.provider == provider,
                    ingestion_cursor.c.dataset == dataset.value,
                    ingestion_cursor.c.scope_key == scope_key,
                    ingestion_cursor.c.generation == expected_generation,
                    ingestion_cursor.c.watermark <= checked_watermark,
                )
                .values(
                    cursor_payload=cursor,
                    watermark=checked_watermark,
                    generation=ingestion_cursor.c.generation + 1,
                    updated_at=changed_at,
                )
            )
            return updated.rowcount == 1

    @staticmethod
    def _lease_predicates(lease: IngestionLease, now: datetime) -> tuple[Any, ...]:
        return (
            ingestion_job.c.id == lease.job_id,
            ingestion_job.c.state == IngestionJobState.RUNNING.value,
            ingestion_job.c.lease_token == lease.token,
            ingestion_job.c.lease_generation == lease.generation,
            ingestion_job.c.lease_expires_at > now,
        )

    def _finish(
        self,
        lease: IngestionLease,
        target: IngestionJobState,
        *,
        now: datetime,
        error_class: str | None = None,
        error_detail: dict[str, object] | None = None,
        next_attempt_at: datetime | None = None,
        dead_letter: bool = False,
    ) -> bool:
        finished_at = require_aware(now).astimezone(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    select(ingestion_job)
                    .where(*self._lease_predicates(lease, finished_at))
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return False
            if target is IngestionJobState.RETRY_SCHEDULED and int(row["attempt_count"]) >= int(
                row["max_attempts"]
            ):
                target = IngestionJobState.DEAD_LETTER
                next_attempt_at = None
                dead_letter = True
            connection.execute(
                insert(ingestion_attempt).values(
                    job_id=lease.job_id,
                    attempt_number=row["attempt_count"],
                    lease_generation=lease.generation,
                    worker_id=row["lease_owner"],
                    started_at=row["attempt_started_at"],
                    finished_at=finished_at,
                    outcome=target.value,
                    error_class=error_class,
                    error_detail=error_detail,
                )
            )
            if dead_letter:
                connection.execute(
                    insert(ingestion_dead_letter).values(
                        job_id=lease.job_id,
                        attempt_number=row["attempt_count"],
                        error_class=error_class,
                        error_detail=error_detail or {},
                        created_at=finished_at,
                    )
                )
            terminal = target in {
                IngestionJobState.SUCCEEDED,
                IngestionJobState.COMPLETED_WITH_GAPS,
                IngestionJobState.FAILED,
                IngestionJobState.DEAD_LETTER,
            }
            result = connection.execute(
                update(ingestion_job)
                .where(*self._lease_predicates(lease, finished_at))
                .values(
                    state=target.value,
                    lease_token=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    attempt_started_at=None,
                    next_attempt_at=next_attempt_at,
                    completed_at=finished_at if terminal else None,
                    updated_at=finished_at,
                )
            )
            return result.rowcount == 1
