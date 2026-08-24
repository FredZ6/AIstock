"""Durable normalization-outbox dispatcher."""

from __future__ import annotations

import hashlib
import json
import logging
from base64 import b64decode, b64encode
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, and_, create_engine, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from stock_platform.application.ingestion.coordinator import IngestionCoordinator
from stock_platform.application.ingestion.normalizers.alpaca import AlpacaNormalizer
from stock_platform.application.ingestion.raw_writer import (
    RawObjectStoreUnavailable,
    RawWriter,
    report_orphaned_raw_objects,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    FeedType,
    IngestionErrorClass,
    MarketDataCoverage,
)
from stock_platform.infrastructure.db.models.tables import (
    ingestion_cursor,
    ingestion_job,
    normalization_dispatch,
    normalization_rejection,
    normalized_record,
    raw_data_object,
)
from stock_platform.infrastructure.ingestion.fact_store import PostgresAlpacaFactStore
from stock_platform.infrastructure.ingestion.job_store import IngestionJobStore
from stock_platform.infrastructure.observability.metrics import platform_metrics
from stock_platform.infrastructure.providers.alpaca_stream import (
    AlpacaStreamPersistenceUnavailable,
    AlpacaStreamReplayWriter,
)
from stock_platform.infrastructure.providers.base import (
    ProviderBatch,
    ProviderRateLimit,
    ProviderRecord,
    RawObjectStore,
)
from stock_platform.infrastructure.providers.object_store import MinioRawObjectStore
from stock_platform.settings import Settings
from stock_platform.workers.alpaca_stream_supervisor import replay_archived_stream_batches

PublishNormalization = Callable[[UUID, str], None]
PublishIngestion = Callable[[UUID], None]
NORMALIZATION_MAX_ATTEMPTS = 5
NORMALIZATION_RETRY_AFTER = timedelta(minutes=1)
ORPHAN_LOG_SAMPLE_LIMIT = 20
logger = logging.getLogger(__name__)
ALPACA_LEASE = timedelta(minutes=10)


class AlpacaLeaseLost(RuntimeError):
    pass


class AlpacaWindowTransport(Protocol):
    def fetch_window(
        self,
        feed_type: FeedType,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        timeframe: str | None,
        coverage: str,
        page_token: str | None = None,
    ) -> ProviderBatch: ...


class RawObjectArchive(RawObjectStore, Protocol):
    def get(self, object_key: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class BoundWindowTransport:
    transport: AlpacaWindowTransport
    start: datetime
    end: datetime
    timeframe: str | None
    coverage: str
    page_token: str | None

    def fetch_batch(
        self,
        feed_type: FeedType,
        symbol: str,
        as_of: datetime,
    ) -> ProviderBatch:
        return self.transport.fetch_window(
            feed_type,
            symbol,
            start=self.start,
            end=self.end,
            timeframe=self.timeframe,
            coverage=self.coverage,
            page_token=self.page_token,
        )


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


def _raw_record(
    batch: ProviderBatch,
    *,
    ingested_at: datetime,
    raw_content: bytes,
) -> ProviderRecord:
    try:
        decoded = json.loads(batch.body, parse_float=str, parse_int=str)
    except (json.JSONDecodeError, UnicodeDecodeError):
        decoded = None
    payload = decoded if isinstance(decoded, dict) else {}
    event_times: list[datetime] = []
    for collection_name, time_key in (("bars", "t"), ("news", "created_at")):
        collection = payload.get(collection_name)
        if isinstance(collection, list):
            for item in collection:
                if isinstance(item, dict) and item.get(time_key) is not None:
                    try:
                        event_times.append(
                            require_aware(
                                datetime.fromisoformat(str(item[time_key]).replace("Z", "+00:00"))
                            ).astimezone(UTC)
                        )
                    except (TypeError, ValueError):
                        # Raw preservation must not depend on semantic schema validity.
                        continue
    content_hash = hashlib.sha256(raw_content).hexdigest()
    checked_ingested_at = max(
        require_aware(ingested_at).astimezone(UTC),
        batch.observed_at,
    )
    return ProviderRecord(
        symbol=batch.symbol,
        feed_type=batch.feed_type,
        provider=batch.provider,
        event_time=min(event_times, default=min(batch.query_as_of, batch.observed_at)),
        available_at=batch.observed_at,
        ingested_at=checked_ingested_at,
        content_hash=content_hash,
        raw_object_key=(f"live/{batch.provider}/{batch.feed_type.value}/{content_hash}.json"),
        payload=cast(dict[str, object], payload),
    )


def _persist_alpaca_batch(
    *,
    engine: Engine,
    raw_store: RawObjectStore,
    job_id: UUID,
    batch: ProviderBatch,
    coverage: MarketDataCoverage | None,
    timeframe: str | None,
    request_identity: str,
    now: datetime,
) -> None:
    if batch.feed_type is FeedType.PRICE_BARS and coverage is None:
        raise ValueError("Alpaca bars require verified entitlement coverage")
    verified_batch = (
        ProviderBatch(
            provider=batch.provider,
            feed_type=batch.feed_type,
            symbol=batch.symbol,
            query_as_of=batch.query_as_of,
            observed_at=batch.observed_at,
            body=batch.body,
            headers={
                key: value
                for key, value in batch.headers.items()
                if key.lower() != "x-alpaca-data-feed"
            }
            | ({"X-AIStock-Verified-Coverage": coverage.value} if coverage is not None else {})
            | ({"X-AIStock-Timeframe": timeframe} if timeframe is not None else {}),
            next_page_token=batch.next_page_token,
            rate_limit=batch.rate_limit,
        )
        if batch.feed_type is FeedType.PRICE_BARS
        else batch
    )
    normalization_version = (
        "alpaca-bars-v1" if batch.feed_type is FeedType.PRICE_BARS else "alpaca-news-v1"
    )
    raw_envelope = json.dumps(
        {
            "provider": batch.provider,
            "feed_type": batch.feed_type.value,
            "symbol": str(batch.symbol),
            "coverage": coverage.value if coverage is not None else None,
            "timeframe": timeframe,
            "request_identity": request_identity,
            "body_sha256": hashlib.sha256(batch.body).hexdigest(),
            "body_base64": b64encode(batch.body).decode("ascii"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    record = _raw_record(verified_batch, ingested_at=now, raw_content=raw_envelope)
    raw_id = RawWriter(engine=engine, raw_store=raw_store).write(
        job_id=job_id,
        record=record,
        raw_content=raw_envelope,
        normalization_version=normalization_version,
    )
    try:
        normalize_dispatched_record(
            engine,
            raw_id=raw_id,
            normalization_version=normalization_version,
            raw_store=cast(RawObjectArchive, raw_store),
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
        raise


def _job_cursor(
    engine: Engine,
    *,
    provider: str,
    dataset: FeedType,
    scope_key: str,
) -> tuple[int, str | None]:
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    ingestion_cursor.c.generation,
                    ingestion_cursor.c.cursor_payload,
                ).where(
                    ingestion_cursor.c.provider == provider,
                    ingestion_cursor.c.dataset == dataset.value,
                    ingestion_cursor.c.scope_key == scope_key,
                )
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return 0, None
    token = row["cursor_payload"].get("next_page_token")
    return int(row["generation"]), str(token) if token is not None else None


def execute_alpaca_ingestion_job(
    *,
    engine: Engine,
    raw_store: RawObjectStore,
    transport: AlpacaWindowTransport,
    job_id: UUID,
    now: datetime,
    worker_id: str,
    clock: Callable[[], datetime] | None = None,
) -> bool:
    checked_now = require_aware(now).astimezone(UTC)
    current_time: Callable[[], datetime] = (
        (lambda: require_aware(clock()).astimezone(UTC))
        if clock is not None
        else (lambda: checked_now)
    )
    store = IngestionJobStore(engine)
    lease = store.claim(
        job_id,
        worker_id=worker_id,
        now=checked_now,
        lease_for=ALPACA_LEASE,
    )
    if lease is None:
        return False
    with engine.connect() as connection:
        row = (
            connection.execute(select(ingestion_job).where(ingestion_job.c.id == job_id))
            .mappings()
            .one()
        )
    if row["provider"] != "ALPACA":
        store.fail(
            lease,
            error_class=IngestionErrorClass.UNSUPPORTED_DATASET,
            error_detail={"provider": row["provider"]},
            now=checked_now,
        )
        return False
    dataset = FeedType(row["dataset"])
    request = row["request_payload"]["request"]
    selected = request.get("coverage")
    coverage = MarketDataCoverage(selected) if selected is not None else None
    entitlement = request.get("entitlement", {})
    entitled_coverage = set(entitlement.get("coverage", ()))
    if coverage is not None and coverage.value not in entitled_coverage:
        store.fail(
            lease,
            error_class=IngestionErrorClass.INVALID_AUTH,
            error_detail={"reason": "coverage_not_in_entitlement_snapshot"},
            now=checked_now,
        )
        return False
    symbol = str(request["symbol"])
    timeframe = request.get("timeframe")
    scope_key = str(job_id)
    generation, page_token = _job_cursor(
        engine,
        provider="ALPACA",
        dataset=dataset,
        scope_key=scope_key,
    )
    while True:

        def persist_with_lease(fetched: ProviderBatch) -> None:
            persisted_at = current_time()
            if not store.heartbeat(
                lease,
                now=persisted_at,
                lease_for=ALPACA_LEASE,
            ):
                raise AlpacaLeaseLost("Alpaca ingestion lease was lost before persistence")
            _persist_alpaca_batch(
                engine=engine,
                raw_store=raw_store,
                job_id=job_id,
                batch=fetched,
                coverage=coverage,
                timeframe=str(timeframe) if timeframe is not None else None,
                request_identity=str(row["request_hash"]),
                now=max(persisted_at, fetched.observed_at),
            )

        coordinator = IngestionCoordinator(
            job_store=store,
            persist_batch=persist_with_lease,
        )
        attempt_now = current_time()
        try:
            batch = coordinator.run(
                lease=lease,
                transport=BoundWindowTransport(
                    transport=transport,
                    start=row["window_start"],
                    end=row["window_end"],
                    timeframe=str(timeframe) if timeframe is not None else None,
                    coverage=coverage.value if coverage is not None else "IEX",
                    page_token=page_token,
                ),
                feed_type=dataset,
                symbol=symbol,
                as_of=row["window_end"],
                now=attempt_now,
                complete_job=False,
            )
            if batch is None:
                return False
        except SQLAlchemyError:
            failed_at = current_time()
            store.schedule_retry(
                lease,
                error_class=IngestionErrorClass.TEMPORARY_DATABASE,
                error_detail={"reason": "database_write_failed"},
                next_attempt_at=failed_at + timedelta(minutes=1),
                now=failed_at,
            )
            return False
        except RawObjectStoreUnavailable:
            failed_at = current_time()
            store.schedule_retry(
                lease,
                error_class=IngestionErrorClass.TEMPORARY_OBJECT_STORE,
                error_detail={"reason": "object_store_write_failed"},
                next_attempt_at=failed_at + timedelta(minutes=1),
                now=failed_at,
            )
            return False
        except AlpacaLeaseLost:
            return False
        except ValueError as error:
            failed_at = current_time()
            store.dead_letter(
                lease,
                error_class=IngestionErrorClass.SCHEMA_DRIFT,
                error_detail={"error_type": type(error).__name__},
                now=failed_at,
            )
            return False
        next_token = batch.next_page_token
        if not store.advance_cursor(
            provider="ALPACA",
            dataset=dataset,
            scope_key=scope_key,
            expected_generation=generation,
            cursor={"next_page_token": next_token},
            watermark=batch.query_as_of,
            now=max(current_time(), batch.observed_at),
            lease=lease,
        ):
            return False
        generation += 1
        page_token = next_token
        if page_token is None:
            break
    with_gaps = request.get("gap_kind") is not None
    if not store.complete(lease, now=current_time(), with_gaps=with_gaps):
        raise RuntimeError("Alpaca ingestion completion rejected")
    return True


def dispatch_queued_alpaca_jobs(
    engine: Engine,
    *,
    publish: PublishIngestion,
    now: datetime,
    limit: int = 50,
) -> int:
    checked_now = require_aware(now).astimezone(UTC)
    if limit < 1:
        raise ValueError("Alpaca dispatch limit must be positive")
    store = IngestionJobStore(engine)
    store.requeue_due(now=checked_now)
    store.recover_expired(now=checked_now)
    with engine.connect() as connection:
        job_ids = tuple(
            connection.execute(
                select(ingestion_job.c.id)
                .where(
                    ingestion_job.c.provider == "ALPACA",
                    ingestion_job.c.state == "QUEUED",
                )
                .order_by(ingestion_job.c.created_at, ingestion_job.c.id)
                .limit(limit)
            ).scalars()
        )
    dispatched = 0
    for queued_job_id in job_ids:
        publish(cast(UUID, queued_job_id))
        dispatched += 1
    return dispatched


def normalize_dispatched_record(
    engine: Engine,
    *,
    raw_id: UUID,
    normalization_version: str,
    raw_store: RawObjectArchive | None = None,
) -> bool:
    if normalization_version in {"alpaca-bars-v1", "alpaca-news-v1"}:
        if raw_store is None:
            raise ValueError("Alpaca normalization requires the immutable raw archive")
        return _normalize_alpaca_dispatched_record(
            engine,
            raw_id=raw_id,
            normalization_version=normalization_version,
            raw_store=raw_store,
        )
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


def _normalize_alpaca_dispatched_record(
    engine: Engine,
    *,
    raw_id: UUID,
    normalization_version: str,
    raw_store: RawObjectArchive,
) -> bool:
    with engine.connect() as connection:
        source = (
            connection.execute(
                select(raw_data_object, normalization_dispatch)
                .join(
                    normalization_dispatch,
                    normalization_dispatch.c.raw_data_object_id == raw_data_object.c.id,
                )
                .where(
                    raw_data_object.c.id == raw_id,
                    normalization_dispatch.c.normalization_version == normalization_version,
                )
            )
            .mappings()
            .one()
        )
    envelope_bytes = raw_store.get(str(source["raw_object_key"]))
    if hashlib.sha256(envelope_bytes).hexdigest() != source["content_hash"]:
        raise ValueError("Alpaca raw envelope content hash mismatch")
    envelope = json.loads(envelope_bytes)
    if not isinstance(envelope, dict):
        raise ValueError("Alpaca raw envelope must be an object")
    try:
        body = b64decode(str(envelope["body_base64"]), validate=True)
        feed_type = FeedType(str(envelope["feed_type"]))
        symbol = Symbol(str(envelope["symbol"]))
        provider = str(envelope["provider"])
        body_sha256 = str(envelope["body_sha256"])
    except (KeyError, ValueError) as error:
        raise ValueError("Alpaca raw envelope identity is invalid") from error
    if hashlib.sha256(body).hexdigest() != body_sha256:
        raise ValueError("Alpaca raw body content hash mismatch")
    expected_symbol = str(source["normalized_payload"].get("symbol"))
    if (
        provider != source["provider"]
        or feed_type.value != source["feed_type"]
        or str(symbol) != expected_symbol
    ):
        raise ValueError("Alpaca raw envelope identity mismatch")
    coverage = envelope.get("coverage")
    timeframe = envelope.get("timeframe")
    headers = ({"X-AIStock-Verified-Coverage": str(coverage)} if coverage is not None else {}) | (
        {"X-AIStock-Timeframe": str(timeframe)} if timeframe is not None else {}
    )
    batch = ProviderBatch(
        provider=provider,
        feed_type=feed_type,
        symbol=symbol,
        query_as_of=source["event_time"],
        observed_at=source["available_at"],
        body=body,
        headers=headers,
        next_page_token=None,
        rate_limit=ProviderRateLimit(),
    )
    facts = AlpacaNormalizer().normalize_batch(batch)
    with engine.begin() as connection:
        inserted = connection.execute(
            insert(normalized_record)
            .values(
                raw_data_object_id=raw_id,
                record_type=source["record_type"],
                record_key=source["record_key"],
                normalization_version=normalization_version,
                payload=source["normalized_payload"],
            )
            .on_conflict_do_nothing(constraint="uq_normalized_record_version")
            .returning(normalized_record.c.id)
        ).scalar_one_or_none()
        normalized_id = inserted
        if normalized_id is None:
            existing = (
                connection.execute(
                    select(normalized_record).where(
                        normalized_record.c.raw_data_object_id == raw_id,
                        normalized_record.c.record_type == source["record_type"],
                        normalized_record.c.record_key == source["record_key"],
                        normalized_record.c.normalization_version == normalization_version,
                    )
                )
                .mappings()
                .one()
            )
            if existing["payload"] != source["normalized_payload"]:
                raise ValueError("immutable normalized record conflict")
            normalized_id = existing["id"]
        fact_store = PostgresAlpacaFactStore(connection)
        if feed_type is FeedType.PRICE_BARS:
            for bar in facts:
                fact_store.persist_bar(
                    raw_id=raw_id,
                    normalized_id=cast(UUID, normalized_id),
                    bar=bar,  # type: ignore[arg-type]
                )
        else:
            for article in facts:
                fact_store.persist_news(
                    raw_id=raw_id,
                    normalized_id=cast(UUID, normalized_id),
                    article=article,  # type: ignore[arg-type]
                )
        connection.execute(
            update(normalization_dispatch)
            .where(
                normalization_dispatch.c.raw_data_object_id == raw_id,
                normalization_dispatch.c.normalization_version == normalization_version,
            )
            .values(state="DISPATCHED", updated_at=datetime.now(UTC))
        )
    return inserted is not None


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
        if terminal:
            existing_rejection = connection.execute(
                select(normalization_rejection.c.id).where(
                    normalization_rejection.c.raw_data_object_id == raw_id,
                    normalization_rejection.c.normalization_version == normalization_version,
                )
            ).scalar_one_or_none()
            if existing_rejection is None:
                connection.execute(
                    insert(normalization_rejection).values(
                        raw_data_object_id=raw_id,
                        record_key=row["record_key"],
                        normalization_version=normalization_version,
                        error_class="SCHEMA_DRIFT",
                        error_detail={"type": type(error).__name__, "message": str(error)},
                    )
                )
    return state


def run_normalization_task(
    engine: Engine,
    *,
    raw_id: UUID,
    normalization_version: str,
    now: datetime,
    raw_store: RawObjectArchive | None = None,
) -> bool:
    try:
        return normalize_dispatched_record(
            engine,
            raw_id=raw_id,
            normalization_version=normalization_version,
            raw_store=raw_store,
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
            raw_store=MinioRawObjectStore.from_settings(settings),
        )
    finally:
        engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="stock_platform.workers.ingestion_tasks.dispatch_alpaca_ingestion_jobs"
)
def dispatch_alpaca_ingestion_jobs() -> int:
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        return dispatch_queued_alpaca_jobs(
            engine,
            publish=lambda job_id: celery_app.send_task(
                "stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job",
                args=[str(job_id)],
                queue="ingestion-low",
            ),
            now=datetime.now(UTC),
        )
    finally:
        engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job"
)
def run_alpaca_ingestion_job(job_id: str) -> bool:
    from stock_platform.infrastructure.providers.alpaca import AlpacaProvider

    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        return execute_alpaca_ingestion_job(
            engine=engine,
            raw_store=MinioRawObjectStore.from_settings(settings),
            transport=AlpacaProvider(
                data_key=settings.alpaca_data_key,
                data_secret=settings.alpaca_data_secret,
            ),
            job_id=UUID(job_id),
            now=datetime.now(UTC),
            worker_id="celery-alpaca-ingestion",
            clock=lambda: datetime.now(UTC),
        )
    finally:
        engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="stock_platform.workers.ingestion_tasks.persist_alpaca_stream_event",
    autoretry_for=(SQLAlchemyError, AlpacaStreamPersistenceUnavailable),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def persist_alpaca_stream_event(raw: str, received_at: str, coverage: str) -> list[str]:
    """Operational raw-first sink for a decoded Alpaca WebSocket envelope."""
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        raw_ids = AlpacaStreamReplayWriter(
            engine=engine,
            raw_store=MinioRawObjectStore.from_settings(settings),
        ).persist_batch(
            raw.encode("utf-8"),
            received_at=require_aware(datetime.fromisoformat(received_at)).astimezone(UTC),
            coverage=MarketDataCoverage(coverage),
        )
        return [str(raw_id) for raw_id in raw_ids]
    finally:
        engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="stock_platform.workers.ingestion_tasks.reconcile_alpaca_stream_archive"
)
def reconcile_alpaca_stream_archive(after_key: str | None = None) -> dict[str, object]:
    """Publish one bounded page of MinIO recovery envelopes that lack PostgreSQL lineage."""
    settings = Settings()
    engine = create_engine(settings.database_url)
    archive = MinioRawObjectStore.from_settings(settings)
    try:

        def publish(task: str, args: list[str]) -> None:
            celery_app.send_task(task, args=args, queue="ingestion-low")

        with engine.connect() as connection:
            result = replay_archived_stream_batches(
                archive,
                publish=publish,
                is_referenced=lambda key: (
                    connection.execute(
                        select(raw_data_object.c.id).where(raw_data_object.c.raw_object_key == key)
                    ).scalar_one_or_none()
                    is not None
                ),
                after_key=after_key,
                limit=100,
            )
        if result.next_cursor is not None:
            celery_app.send_task(
                "stock_platform.workers.ingestion_tasks.reconcile_alpaca_stream_archive",
                args=[result.next_cursor],
                queue="ingestion-low",
            )
        return {"replayed": result.replayed, "next_cursor": result.next_cursor}
    finally:
        engine.dispose()
