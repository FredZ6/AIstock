"""Durable normalization-outbox dispatcher."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Engine, and_, create_engine, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from stock_platform.application.ingestion.raw_writer import report_orphaned_raw_objects
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import FeedType
from stock_platform.infrastructure.db.models.tables import (
    normalization_dispatch,
    normalization_rejection,
    normalized_record,
)
from stock_platform.infrastructure.observability.metrics import platform_metrics
from stock_platform.infrastructure.providers.object_store import MinioRawObjectStore
from stock_platform.settings import Settings

PublishNormalization = Callable[[UUID, str], None]
NORMALIZATION_MAX_ATTEMPTS = 5
NORMALIZATION_RETRY_AFTER = timedelta(minutes=1)
ORPHAN_LOG_SAMPLE_LIMIT = 20
logger = logging.getLogger(__name__)


class BarTimeframe(StrEnum):
    MINUTE = "1Min"
    DAY = "1Day"


class BackfillPriority(StrEnum):
    LOW = "LOW"


@dataclass(frozen=True, slots=True)
class AlpacaBackfillSlice:
    dataset: FeedType
    timeframe: BarTimeframe | None
    start: datetime
    end: datetime
    priority: BackfillPriority = BackfillPriority.LOW
    page_token: str | None = None


@dataclass(frozen=True, slots=True)
class ReconnectGapFill:
    start: datetime
    end: datetime
    truncated: bool


_BACKFILL_BOUNDS = {
    (FeedType.PRICE_BARS, BarTimeframe.DAY): (timedelta(days=365), timedelta(days=30)),
    (FeedType.PRICE_BARS, BarTimeframe.MINUTE): (timedelta(days=90), timedelta(days=5)),
    (FeedType.COMPANY_NEWS, None): (timedelta(days=365), timedelta(days=30)),
}


def plan_alpaca_backfill(
    *,
    dataset: FeedType,
    timeframe: BarTimeframe | None,
    start: datetime,
    end: datetime,
) -> tuple[AlpacaBackfillSlice, ...]:
    window_start = require_aware(start).astimezone(UTC)
    window_end = require_aware(end).astimezone(UTC)
    if window_start >= window_end:
        raise ValueError("backfill start must be before end")
    try:
        maximum, chunk = _BACKFILL_BOUNDS[(dataset, timeframe)]
    except KeyError as error:
        raise ValueError("unsupported Alpaca backfill dataset/timeframe") from error
    if window_end - window_start > maximum:
        raise ValueError("backfill window must be bounded")
    slices: list[AlpacaBackfillSlice] = []
    cursor = window_start
    while cursor < window_end:
        next_end = min(cursor + chunk, window_end)
        slices.append(
            AlpacaBackfillSlice(
                dataset=dataset,
                timeframe=timeframe,
                start=cursor,
                end=next_end,
            )
        )
        cursor = next_end
    return tuple(slices)


def resume_alpaca_page(
    item: AlpacaBackfillSlice,
    *,
    next_page_token: str,
) -> AlpacaBackfillSlice:
    if not next_page_token.strip():
        raise ValueError("pagination token cannot be blank")
    return replace(item, page_token=next_page_token)


def plan_reconnect_gap_fill(
    *,
    last_event_at: datetime,
    reconnected_at: datetime,
    maximum: timedelta = timedelta(minutes=30),
) -> ReconnectGapFill:
    last_event = require_aware(last_event_at).astimezone(UTC)
    reconnected = require_aware(reconnected_at).astimezone(UTC)
    if maximum <= timedelta(0) or last_event >= reconnected:
        raise ValueError("reconnect gap must be positive and ordered")
    truncated = reconnected - last_event > maximum
    return ReconnectGapFill(
        start=max(last_event, reconnected - maximum),
        end=reconnected,
        truncated=truncated,
    )


def normalize_dispatched_record(
    engine: Engine,
    *,
    raw_id: UUID,
    normalization_version: str,
) -> bool:
    conflict = False
    with engine.begin() as connection:
        dispatch = (
            connection.execute(
                select(normalization_dispatch).where(
                    normalization_dispatch.c.raw_data_object_id == raw_id,
                    normalization_dispatch.c.normalization_version == normalization_version,
                    normalization_dispatch.c.state.in_(("PENDING", "CLAIMED", "DISPATCHED")),
                )
            )
            .mappings()
            .one()
        )
        inserted = connection.execute(
            insert(normalized_record)
            .values(
                raw_data_object_id=raw_id,
                record_type=dispatch["record_type"],
                record_key=dispatch["record_key"],
                normalization_version=normalization_version,
                payload=dispatch["normalized_payload"],
            )
            .on_conflict_do_nothing(constraint="uq_normalized_record_version")
            .returning(normalized_record.c.id)
        ).scalar_one_or_none()
        if inserted is not None:
            return True
        existing = (
            connection.execute(
                select(normalized_record).where(
                    normalized_record.c.raw_data_object_id == raw_id,
                    normalized_record.c.record_type == dispatch["record_type"],
                    normalized_record.c.record_key == dispatch["record_key"],
                    normalized_record.c.normalization_version == normalization_version,
                )
            )
            .mappings()
            .one()
        )
        if existing["payload"] != dispatch["normalized_payload"]:
            connection.execute(
                insert(normalization_rejection).values(
                    raw_data_object_id=raw_id,
                    record_key=dispatch["record_key"],
                    normalization_version=normalization_version,
                    error_class="IMMUTABLE_CONFLICT",
                    error_detail={"reason": "normalized payload differs"},
                )
            )
            conflict = True
    if conflict:
        raise ValueError("immutable normalized record conflict")
    return False


def record_normalization_failure(
    engine: Engine,
    *,
    raw_id: UUID,
    normalization_version: str,
    error: Exception,
    now: datetime,
    retry_after: timedelta = NORMALIZATION_RETRY_AFTER,
    max_attempts: int = NORMALIZATION_MAX_ATTEMPTS,
    terminal: bool = False,
) -> str:
    failed_at = require_aware(now).astimezone(UTC)
    if retry_after <= timedelta(0) or max_attempts < 1:
        raise ValueError("normalization retry delay and attempt budget must be positive")
    with engine.begin() as connection:
        row = (
            connection.execute(
                select(normalization_dispatch)
                .where(
                    normalization_dispatch.c.raw_data_object_id == raw_id,
                    normalization_dispatch.c.normalization_version == normalization_version,
                    normalization_dispatch.c.state.in_(("PENDING", "CLAIMED", "DISPATCHED")),
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        state = "FAILED" if terminal or int(row["attempt_count"]) >= max_attempts else "PENDING"
        connection.execute(
            update(normalization_dispatch)
            .where(normalization_dispatch.c.id == row["id"])
            .values(
                state=state,
                lease_token=None,
                lease_expires_at=None,
                next_attempt_at=(
                    row["next_attempt_at"] if state == "FAILED" else failed_at + retry_after
                ),
                last_error={"type": type(error).__name__},
                updated_at=failed_at,
            )
        )
    return state


def run_normalization_task(
    engine: Engine,
    *,
    raw_id: UUID,
    normalization_version: str,
    now: datetime,
) -> bool:
    try:
        return normalize_dispatched_record(
            engine,
            raw_id=raw_id,
            normalization_version=normalization_version,
        )
    except Exception as error:
        record_normalization_failure(
            engine,
            raw_id=raw_id,
            normalization_version=normalization_version,
            error=error,
            now=now,
            terminal=isinstance(error, ValueError),
        )
        return False


def dispatch_pending_normalization(
    engine: Engine,
    *,
    publish: PublishNormalization,
    now: datetime,
    lease_for: timedelta = timedelta(minutes=5),
    retry_after: timedelta = timedelta(minutes=1),
    limit: int = 100,
) -> int:
    claimed_at = require_aware(now).astimezone(UTC)
    if lease_for <= timedelta(0) or retry_after <= timedelta(0) or limit < 1:
        raise ValueError("dispatch lease, retry delay, and limit must be positive")
    claims: list[tuple[UUID, UUID, str, UUID, int]] = []
    with engine.begin() as connection:
        rows = (
            connection.execute(
                select(normalization_dispatch)
                .where(
                    or_(
                        and_(
                            normalization_dispatch.c.state == "PENDING",
                            normalization_dispatch.c.next_attempt_at <= claimed_at,
                        ),
                        and_(
                            normalization_dispatch.c.state == "CLAIMED",
                            normalization_dispatch.c.lease_expires_at <= claimed_at,
                        ),
                    )
                )
                .order_by(normalization_dispatch.c.next_attempt_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .mappings()
            .all()
        )
        for row in rows:
            token = uuid4()
            generation = int(row["lease_generation"]) + 1
            connection.execute(
                update(normalization_dispatch)
                .where(normalization_dispatch.c.id == row["id"])
                .values(
                    state="CLAIMED",
                    attempt_count=normalization_dispatch.c.attempt_count + 1,
                    lease_token=token,
                    lease_generation=generation,
                    lease_expires_at=claimed_at + lease_for,
                    updated_at=claimed_at,
                )
            )
            claims.append(
                (
                    row["id"],
                    row["raw_data_object_id"],
                    row["normalization_version"],
                    token,
                    generation,
                )
            )

    dispatched = 0
    for dispatch_id, raw_id, version, token, generation in claims:
        try:
            publish(raw_id, version)
        except Exception as error:
            with engine.begin() as connection:
                connection.execute(
                    update(normalization_dispatch)
                    .where(
                        normalization_dispatch.c.id == dispatch_id,
                        normalization_dispatch.c.state == "CLAIMED",
                        normalization_dispatch.c.lease_token == token,
                        normalization_dispatch.c.lease_generation == generation,
                    )
                    .values(
                        state="PENDING",
                        lease_token=None,
                        lease_expires_at=None,
                        next_attempt_at=claimed_at + retry_after,
                        last_error={"type": type(error).__name__},
                        updated_at=claimed_at,
                    )
                )
            continue
        with engine.begin() as connection:
            result = connection.execute(
                update(normalization_dispatch)
                .where(
                    normalization_dispatch.c.id == dispatch_id,
                    normalization_dispatch.c.state == "CLAIMED",
                    normalization_dispatch.c.lease_token == token,
                    normalization_dispatch.c.lease_generation == generation,
                )
                .values(
                    state="DISPATCHED",
                    lease_token=None,
                    lease_expires_at=None,
                    last_error=None,
                    updated_at=claimed_at,
                )
            )
            dispatched += int(result.rowcount == 1)
    return dispatched


from stock_platform.workers.celery_app import celery_app  # noqa: E402, I001


@celery_app.task(  # type: ignore[untyped-decorator]
    name="stock_platform.workers.ingestion_tasks.dispatch_normalization_outbox"
)
def dispatch_normalization_outbox() -> int:
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        return dispatch_pending_normalization(
            engine,
            publish=lambda raw_id, version: celery_app.send_task(
                "stock_platform.workers.ingestion_tasks.normalize_raw_object",
                args=[str(raw_id), version],
            ),
            now=datetime.now(UTC),
        )
    finally:
        engine.dispose()


def record_orphan_inventory(
    orphaned_keys: tuple[str, ...],
    *,
    warning: Callable[..., None] = logger.warning,
) -> int:
    count = len(orphaned_keys)
    platform_metrics.set_queue(queue="minio_orphans", depth=count)
    if count:
        warning(
            "unreferenced MinIO raw objects: count=%d sample=%s",
            count,
            orphaned_keys[:ORPHAN_LOG_SAMPLE_LIMIT],
        )
    return count


@celery_app.task(  # type: ignore[untyped-decorator]
    name="stock_platform.workers.ingestion_tasks.report_minio_orphans"
)
def report_minio_orphans() -> int:
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        inventory = MinioRawObjectStore.from_settings(settings)
        orphaned_keys = report_orphaned_raw_objects(engine, inventory)
        return record_orphan_inventory(orphaned_keys)
    finally:
        engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="stock_platform.workers.ingestion_tasks.normalize_raw_object",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=NORMALIZATION_MAX_ATTEMPTS,
)
def normalize_raw_object(raw_id: str, normalization_version: str) -> bool:
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        return run_normalization_task(
            engine,
            raw_id=UUID(raw_id),
            normalization_version=normalization_version,
            now=datetime.now(UTC),
        )
    finally:
        engine.dispose()
