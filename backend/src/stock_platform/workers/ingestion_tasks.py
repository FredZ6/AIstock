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
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, and_, create_engine, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from stock_platform.application.ingestion.concept_mapping import ConceptMappingRegistry
from stock_platform.application.ingestion.coordinator import IngestionCoordinator
from stock_platform.application.ingestion.jobs import IngestionJobSpec
from stock_platform.application.ingestion.normalizers.alpaca import AlpacaNormalizer
from stock_platform.application.ingestion.normalizers.alpha_vantage import AlphaVantageNormalizer
from stock_platform.application.ingestion.normalizers.sec import SecNormalizer
from stock_platform.application.ingestion.raw_writer import (
    RawObjectStoreUnavailable,
    RawWriter,
    report_orphaned_raw_objects,
)
from stock_platform.application.market_data.quality import QualityPolicy, evaluate_freshness
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    FeedType,
    IngestionErrorClass,
    IngestionRequest,
    MarketDataCoverage,
)
from stock_platform.domain.market_data.concepts import FinancialFactInput
from stock_platform.infrastructure.db.models.tables import (
    ingestion_cursor,
    ingestion_job,
    ingestion_raw_link,
    normalization_dispatch,
    normalization_rejection,
    normalized_record,
    raw_data_object,
    sec_filing,
)
from stock_platform.infrastructure.ingestion.fact_store import (
    PostgresAlpacaFactStore,
    PostgresEarningsEventStore,
    PostgresFinancialFactStore,
    PostgresQualityFactStore,
    PostgresSecFactStore,
)
from stock_platform.infrastructure.ingestion.job_store import IngestionJobStore
from stock_platform.infrastructure.observability.metrics import platform_metrics
from stock_platform.infrastructure.providers.alpaca_stream import (
    AlpacaStreamPersistenceUnavailable,
    AlpacaStreamReplayWriter,
)
from stock_platform.infrastructure.providers.alpha_vantage import PostgresAlphaSymbolResolver
from stock_platform.infrastructure.providers.base import (
    ProviderBatch,
    ProviderRateLimit,
    ProviderRecord,
    ProviderTransportError,
    RawObjectStore,
)
from stock_platform.infrastructure.providers.object_store import MinioRawObjectStore
from stock_platform.infrastructure.providers.persistence import persist_raw_object
from stock_platform.infrastructure.providers.sec import PostgresSecIdentityResolver
from stock_platform.settings import Settings
from stock_platform.workers.alpaca_stream_supervisor import replay_archived_stream_batches

PublishNormalization = Callable[[UUID, str], None]
PublishIngestion = Callable[[UUID], None]
NORMALIZATION_MAX_ATTEMPTS = 5
NORMALIZATION_RETRY_AFTER = timedelta(minutes=1)
ORPHAN_LOG_SAMPLE_LIMIT = 20
logger = logging.getLogger(__name__)
ALPACA_LEASE = timedelta(minutes=10)
ALPHA_LEASE = timedelta(minutes=10)
SEC_LEASE = timedelta(minutes=15)


class AlpacaLeaseLost(RuntimeError):
    pass


class SecFilingDependencyUnavailable(RuntimeError):
    pass


class SecLeaseLost(RuntimeError):
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


class AlphaCalendarTransport(Protocol):
    def fetch_batch(
        self,
        feed_type: FeedType,
        symbol: str,
        as_of: datetime,
    ) -> ProviderBatch: ...


class SecIngestionTransport(Protocol):
    def fetch_batch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderBatch: ...

    def fetch_historical_submissions(
        self, symbol: str, *, file_name: str, as_of: datetime
    ) -> ProviderBatch: ...

    def fetch_filing_document(
        self,
        symbol: str,
        *,
        accession_number: str,
        primary_document: str,
        as_of: datetime,
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
    declared_delay: timedelta = timedelta(0),
) -> None:
    if batch.feed_type is FeedType.PRICE_BARS and coverage is None:
        raise ValueError("Alpaca bars require verified entitlement coverage")
    quality_coverage = coverage if batch.feed_type is FeedType.PRICE_BARS else None
    quality_delay = declared_delay if batch.feed_type is FeedType.PRICE_BARS else timedelta(0)
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
            "coverage": quality_coverage.value if quality_coverage is not None else None,
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
    _persist_alpaca_quality(
        engine=engine,
        raw_id=raw_id,
        batch=verified_batch,
        coverage=quality_coverage,
        observed_at=now,
        declared_delay=quality_delay,
    )


def _persist_alpaca_quality(
    *,
    engine: Engine,
    raw_id: UUID,
    batch: ProviderBatch,
    coverage: MarketDataCoverage | None,
    observed_at: datetime,
    declared_delay: timedelta,
) -> None:
    """Persist versioned quality before the caller is allowed to advance its cursor."""
    with engine.begin() as connection:
        _persist_freshness_quality(
            connection=connection,
            raw_id=raw_id,
            provider=batch.provider,
            dataset=batch.feed_type.value,
            observed_at=observed_at,
            latest_available_at=batch.observed_at,
            coverage=coverage,
            declared_delay=declared_delay,
        )


def _persist_freshness_quality(
    *,
    connection: Connection,
    raw_id: UUID,
    provider: str,
    dataset: str,
    observed_at: datetime,
    latest_available_at: datetime,
    coverage: MarketDataCoverage | None = None,
    declared_delay: timedelta = timedelta(0),
    require_normalized: bool = True,
) -> int:
    """Attach one immutable freshness fact to every normalized record for a raw object."""
    policy = QualityPolicy.load(Path(__file__).parents[3] / "config" / "data_quality_v1.yaml")
    assessment = evaluate_freshness(
        provider=provider,
        dataset=dataset,
        observed_at=observed_at,
        latest_available_at=latest_available_at,
        coverage=coverage,
        declared_delay=declared_delay,
        policy=policy,
    )
    normalized_ids = tuple(
        connection.execute(
            select(normalized_record.c.id).where(normalized_record.c.raw_data_object_id == raw_id)
        ).scalars()
    )
    if not normalized_ids and require_normalized:
        raise ValueError("quality persistence requires normalized lineage")
    quality = PostgresQualityFactStore(connection)
    for normalized_id in normalized_ids:
        quality.persist(
            raw_id=raw_id,
            normalized_id=cast(UUID, normalized_id),
            assessment=assessment,
        )
    return len(normalized_ids)


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
    raw_sip_delay = entitlement.get("sip_delay_seconds")
    if coverage is MarketDataCoverage.SIP:
        if (
            not isinstance(raw_sip_delay, int)
            or isinstance(raw_sip_delay, bool)
            or raw_sip_delay < 0
        ):
            store.fail(
                lease,
                error_class=IngestionErrorClass.INVALID_AUTH,
                error_detail={"reason": "invalid_sip_delay_snapshot"},
                now=checked_now,
            )
            return False
        declared_delay = timedelta(seconds=raw_sip_delay)
    else:
        declared_delay = timedelta(0)
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
                declared_delay=declared_delay,
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


def _archive_sec_batch(
    *,
    engine: Engine,
    raw_store: RawObjectStore,
    job_id: UUID,
    batch: ProviderBatch,
    ingested_at: datetime,
    scope: str,
    heartbeat: Callable[[], None],
    transaction_guard: Callable[[Connection], None],
) -> UUID:
    heartbeat()
    persisted_at = max(require_aware(ingested_at), batch.observed_at)
    envelope = json.dumps(
        {
            "provider": batch.provider,
            "feed_type": batch.feed_type.value,
            "symbol": str(batch.symbol),
            "scope": scope,
            "observed_at": batch.observed_at.isoformat(),
            "body_sha256": hashlib.sha256(batch.body).hexdigest(),
            "body_base64": b64encode(batch.body).decode("ascii"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    content_hash = hashlib.sha256(envelope).hexdigest()
    record = ProviderRecord(
        symbol=batch.symbol,
        feed_type=batch.feed_type,
        provider="SEC",
        event_time=batch.observed_at,
        available_at=batch.observed_at,
        ingested_at=persisted_at,
        content_hash=content_hash,
        raw_object_key=f"live/SEC/{batch.feed_type.value}/{content_hash}.json",
        payload={"scope": scope, "body_sha256": hashlib.sha256(batch.body).hexdigest()},
    )
    raw_id = RawWriter(engine=engine, raw_store=raw_store).write_artifact(
        record=record,
        raw_content=envelope,
        content_type="application/json",
        job_id=job_id,
        transaction_guard=transaction_guard,
    )
    return raw_id


def _archive_sec_document(
    *,
    engine: Engine,
    raw_store: RawObjectStore,
    job_id: UUID,
    batch: ProviderBatch,
    ingested_at: datetime,
    heartbeat: Callable[[], None],
    transaction_guard: Callable[[Connection], None],
) -> UUID:
    heartbeat()
    content_hash = hashlib.sha256(batch.body).hexdigest()
    mime_type = next(
        (
            value.split(";", 1)[0].strip().lower()
            for key, value in batch.headers.items()
            if key.lower() == "content-type"
        ),
        "text/html",
    )
    is_text = mime_type == "text/plain" or batch.body.lstrip().startswith(b"<SEC-DOCUMENT>")
    extension = "txt" if is_text else "html"
    record = ProviderRecord(
        symbol=batch.symbol,
        feed_type=FeedType.FILING_SECTIONS,
        provider="SEC",
        event_time=batch.observed_at,
        available_at=batch.observed_at,
        ingested_at=max(require_aware(ingested_at), batch.observed_at),
        content_hash=content_hash,
        raw_object_key=f"live/SEC/filing_sections/{content_hash}.{extension}",
        payload={},
    )
    raw_id = RawWriter(engine=engine, raw_store=raw_store).write_artifact(
        record=record,
        raw_content=batch.body,
        content_type="text/plain" if is_text else "text/html",
        job_id=job_id,
        transaction_guard=transaction_guard,
    )
    return raw_id


def _persist_sec_filings(
    *,
    engine: Engine,
    raw_store: RawObjectStore,
    transport: SecIngestionTransport,
    job_id: UUID,
    symbol: str,
    cutoff: datetime,
    ingested_at: datetime,
    heartbeat: Callable[[], None],
    transaction_guard: Callable[[Connection], None],
) -> None:
    heartbeat()
    with engine.connect() as connection:
        identity = PostgresSecIdentityResolver(connection).resolve(Symbol(symbol), cutoff)
    if identity is None:
        raise ValueError("SEC Security identity is unavailable at the job cutoff")
    normalizer = SecNormalizer()
    submissions = transport.fetch_batch(FeedType.FILINGS, symbol, cutoff)
    heartbeat()
    submissions_raw_id = _archive_sec_batch(
        engine=engine,
        raw_store=raw_store,
        job_id=job_id,
        batch=submissions,
        ingested_at=ingested_at,
        scope="RECENT_SUBMISSIONS",
        heartbeat=heartbeat,
        transaction_guard=transaction_guard,
    )
    result = normalizer.normalize_submissions(submissions, identity=identity)
    pages = [(submissions_raw_id, submissions, result.filings)]
    for file_name in result.historical_submission_files:
        historical = transport.fetch_historical_submissions(
            symbol, file_name=file_name, as_of=cutoff
        )
        heartbeat()
        historical_raw_id = _archive_sec_batch(
            engine=engine,
            raw_store=raw_store,
            job_id=job_id,
            batch=historical,
            ingested_at=ingested_at,
            scope=file_name,
            heartbeat=heartbeat,
            transaction_guard=transaction_guard,
        )
        pages.append(
            (
                historical_raw_id,
                historical,
                normalizer.normalize_historical_submissions(historical, identity=identity),
            )
        )
    if identity.security_id is None:
        raise ValueError("SEC Security identity is missing its PIT security_id")
    for raw_id, batch, filings in pages:
        for filing in filings:
            normalized_values = {
                "raw_data_object_id": raw_id,
                "record_type": "sec_filing",
                "record_key": filing.accession_number,
                "normalization_version": "sec-filings-v1",
                "payload": filing.payload | {"symbol": symbol},
            }
            with engine.begin() as connection:
                transaction_guard(connection)
                normalized_id = connection.execute(
                    insert(normalized_record)
                    .values(**normalized_values)
                    .on_conflict_do_nothing(constraint="uq_normalized_record_version")
                    .returning(normalized_record.c.id)
                ).scalar_one_or_none()
                if normalized_id is None:
                    normalized_id = connection.execute(
                        select(normalized_record.c.id).where(
                            normalized_record.c.raw_data_object_id == raw_id,
                            normalized_record.c.record_type == "sec_filing",
                            normalized_record.c.record_key == filing.accession_number,
                            normalized_record.c.normalization_version == "sec-filings-v1",
                        )
                    ).scalar_one()
            with engine.connect() as connection:
                existing_filing = connection.execute(
                    select(sec_filing.c.id).where(
                        sec_filing.c.provider == "SEC",
                        sec_filing.c.accession_number == filing.accession_number,
                    )
                ).scalar_one_or_none()
            if existing_filing is not None:
                continue
            heartbeat()
            document = transport.fetch_filing_document(
                symbol,
                accession_number=filing.accession_number,
                primary_document=filing.primary_document,
                as_of=cutoff,
            )
            heartbeat()
            document_raw_id = _archive_sec_document(
                engine=engine,
                raw_store=raw_store,
                job_id=job_id,
                batch=document,
                ingested_at=ingested_at,
                heartbeat=heartbeat,
                transaction_guard=transaction_guard,
            )
            with engine.begin() as connection:
                transaction_guard(connection)
                PostgresSecFactStore(connection).persist_filing(
                    security_id=identity.security_id,
                    raw_id=raw_id,
                    normalized_id=cast(UUID, normalized_id),
                    document_raw_id=document_raw_id,
                    filing=filing,
                )
        with engine.begin() as connection:
            transaction_guard(connection)
            _persist_freshness_quality(
                connection=connection,
                raw_id=raw_id,
                provider="SEC",
                dataset=FeedType.FILINGS.value,
                observed_at=max(require_aware(ingested_at), batch.observed_at),
                latest_available_at=batch.observed_at,
            )


def _persist_sec_company_facts(
    *,
    engine: Engine,
    raw_store: RawObjectStore,
    transport: SecIngestionTransport,
    job_id: UUID,
    symbol: str,
    cutoff: datetime,
    ingested_at: datetime,
    heartbeat: Callable[[], None],
    transaction_guard: Callable[[Connection], None],
) -> None:
    heartbeat()
    with engine.connect() as connection:
        identity = PostgresSecIdentityResolver(connection).resolve(Symbol(symbol), cutoff)
    if identity is None:
        raise ValueError("SEC Security identity is unavailable at the job cutoff")
    if identity.security_id is None:
        raise ValueError("SEC Security identity is missing its PIT security_id")
    batch = transport.fetch_batch(FeedType.COMPANY_FACTS, symbol, cutoff)
    heartbeat()
    raw_id = _archive_sec_batch(
        engine=engine,
        raw_store=raw_store,
        job_id=job_id,
        batch=batch,
        ingested_at=ingested_at,
        scope="COMPANY_FACTS",
        heartbeat=heartbeat,
        transaction_guard=transaction_guard,
    )
    facts = SecNormalizer().normalize_company_facts(batch, identity=identity)
    registry = ConceptMappingRegistry.load(
        Path(__file__).resolve().parents[3] / "config" / "financial_concepts_v1.yaml"
    )
    required_accessions = {fact.accession_number for fact in facts}
    with engine.connect() as connection:
        available_accessions = set(
            connection.execute(
                select(sec_filing.c.accession_number).where(
                    sec_filing.c.security_id == identity.security_id,
                    sec_filing.c.accession_number.in_(required_accessions),
                )
            ).scalars()
        )
    if available_accessions != required_accessions:
        raise SecFilingDependencyUnavailable("SEC filing lineage has not been ingested yet")
    normalized_by_source: dict[tuple[object, ...], UUID] = {}
    for fact in facts:
        normalized_values = {
            "raw_data_object_id": raw_id,
            "record_type": "financial_fact",
            "record_key": (
                f"{symbol}:{fact.taxonomy}:{fact.concept}:{fact.accession_number}:"
                f"{fact.period_start.isoformat()}:{fact.period_end.isoformat()}:{fact.unit}"
            ),
            "normalization_version": "sec-company-facts-v1",
            "payload": {
                "symbol": symbol,
                "taxonomy": fact.taxonomy,
                "concept": fact.concept,
                "value": str(fact.value),
                "unit": fact.unit,
                "currency": fact.currency,
                "period_start": fact.period_start.isoformat(),
                "period_end": fact.period_end.isoformat(),
                "accession_number": fact.accession_number,
            },
        }
        with engine.begin() as connection:
            transaction_guard(connection)
            normalized_id = connection.execute(
                insert(normalized_record)
                .values(**normalized_values)
                .on_conflict_do_nothing(constraint="uq_normalized_record_version")
                .returning(normalized_record.c.id)
            ).scalar_one_or_none()
            if normalized_id is None:
                normalized_id = connection.execute(
                    select(normalized_record.c.id).where(
                        normalized_record.c.raw_data_object_id == raw_id,
                        normalized_record.c.record_type == "financial_fact",
                        normalized_record.c.record_key == normalized_values["record_key"],
                        normalized_record.c.normalization_version == "sec-company-facts-v1",
                    )
                ).scalar_one()
            PostgresFinancialFactStore(connection).persist_fact(
                security_id=identity.security_id,
                raw_id=raw_id,
                normalized_id=cast(UUID, normalized_id),
                available_at=batch.observed_at,
                result=registry.map_fact(fact),
            )
        normalized_by_source[
            (
                fact.taxonomy,
                fact.concept,
                fact.accession_number,
                fact.unit,
                fact.currency,
                fact.period_start,
                fact.period_end,
            )
        ] = cast(UUID, normalized_id)
    groups: dict[tuple[object, ...], list[FinancialFactInput]] = {}
    for fact in facts:
        key = (
            fact.accession_number,
            fact.unit,
            fact.currency,
            fact.period_start,
            fact.period_end,
        )
        groups.setdefault(key, []).append(fact)
    for grouped in groups.values():
        for result in registry.derive_available(tuple(grouped)):
            first = result.source_facts[0]
            with engine.begin() as connection:
                transaction_guard(connection)
                PostgresFinancialFactStore(connection).persist_fact(
                    security_id=identity.security_id,
                    raw_id=raw_id,
                    normalized_id=normalized_by_source[
                        (
                            first.taxonomy,
                            first.concept,
                            first.accession_number,
                            first.unit,
                            first.currency,
                            first.period_start,
                            first.period_end,
                        )
                    ],
                    available_at=batch.observed_at,
                    result=result,
                )
    with engine.begin() as connection:
        transaction_guard(connection)
        _persist_freshness_quality(
            connection=connection,
            raw_id=raw_id,
            provider="SEC",
            dataset=FeedType.COMPANY_FACTS.value,
            observed_at=max(require_aware(ingested_at), batch.observed_at),
            latest_available_at=batch.observed_at,
        )


def _enqueue_sec_company_facts(
    engine: Engine,
    *,
    symbol: str,
    cutoff: datetime,
    now: datetime,
) -> UUID:
    checked_cutoff = require_aware(cutoff).astimezone(UTC)
    return IngestionJobStore(engine).enqueue(
        IngestionJobSpec(
            request=IngestionRequest(
                {
                    "symbol": symbol,
                    "snapshot_date": checked_cutoff.date().isoformat(),
                }
            ),
            provider="SEC",
            dataset=FeedType.COMPANY_FACTS,
            window_start=checked_cutoff,
            window_end=checked_cutoff,
            purpose=DataPurpose.RESEARCH,
            policy_version="sec-edgar-v1",
            max_attempts=3,
        ),
        now=require_aware(now),
    )


def execute_sec_ingestion_job(
    *,
    engine: Engine,
    raw_store: RawObjectStore,
    transport: SecIngestionTransport,
    job_id: UUID,
    now: datetime,
    worker_id: str,
    clock: Callable[[], datetime] | None = None,
) -> bool:
    checked_now = require_aware(now).astimezone(UTC)
    store = IngestionJobStore(engine)
    lease = store.claim(job_id, worker_id=worker_id, now=checked_now, lease_for=SEC_LEASE)
    if lease is None:
        return False
    time_source = clock or (lambda: datetime.now(UTC))

    def current_time() -> datetime:
        return max(checked_now, require_aware(time_source()).astimezone(UTC))

    def heartbeat() -> None:
        if not store.heartbeat(lease, now=current_time(), lease_for=SEC_LEASE):
            raise SecLeaseLost("SEC ingestion lease is no longer current")

    def transaction_guard(connection: Connection) -> None:
        guarded_at = current_time()
        current_job = connection.execute(
            select(ingestion_job.c.id)
            .where(
                ingestion_job.c.id == lease.job_id,
                ingestion_job.c.state == "RUNNING",
                ingestion_job.c.lease_token == lease.token,
                ingestion_job.c.lease_generation == lease.generation,
                ingestion_job.c.lease_expires_at > guarded_at,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if current_job is None:
            raise SecLeaseLost("SEC ingestion lease is no longer current")
        connection.execute(
            update(ingestion_job)
            .where(ingestion_job.c.id == lease.job_id)
            .values(
                lease_expires_at=guarded_at + SEC_LEASE,
                updated_at=guarded_at,
            )
        )

    with engine.connect() as connection:
        row = (
            connection.execute(select(ingestion_job).where(ingestion_job.c.id == job_id))
            .mappings()
            .one()
        )
    if row["provider"] != "SEC" or row["dataset"] not in {
        FeedType.FILINGS.value,
        FeedType.COMPANY_FACTS.value,
    }:
        store.fail(
            lease,
            error_class=IngestionErrorClass.UNSUPPORTED_DATASET,
            error_detail={"provider": row["provider"], "dataset": row["dataset"]},
            now=checked_now,
        )
        return False
    request = cast(dict[str, object], row["request_payload"])["request"]
    symbol = str(cast(dict[str, object], request)["symbol"])
    try:
        if row["dataset"] == FeedType.FILINGS.value:
            _persist_sec_filings(
                engine=engine,
                raw_store=raw_store,
                transport=transport,
                job_id=job_id,
                symbol=symbol,
                cutoff=row["window_end"],
                ingested_at=checked_now,
                heartbeat=heartbeat,
                transaction_guard=transaction_guard,
            )
            heartbeat()
            _enqueue_sec_company_facts(
                engine,
                symbol=symbol,
                cutoff=row["window_end"],
                now=current_time(),
            )
        else:
            _persist_sec_company_facts(
                engine=engine,
                raw_store=raw_store,
                transport=transport,
                job_id=job_id,
                symbol=symbol,
                cutoff=row["window_end"],
                ingested_at=checked_now,
                heartbeat=heartbeat,
                transaction_guard=transaction_guard,
            )
    except ProviderTransportError as error:
        if error.error_class in {
            IngestionErrorClass.TIMEOUT,
            IngestionErrorClass.NETWORK,
            IngestionErrorClass.RATE_LIMIT,
            IngestionErrorClass.PROVIDER_5XX,
        }:
            store.schedule_retry(
                lease,
                error_class=error.error_class,
                error_detail={"status_code": error.status_code},
                next_attempt_at=current_time() + (error.retry_after or timedelta(minutes=1)),
                now=current_time(),
            )
        else:
            store.dead_letter(
                lease,
                error_class=error.error_class,
                error_detail={"status_code": error.status_code},
                now=current_time(),
            )
        return False
    except RawObjectStoreUnavailable:
        store.schedule_retry(
            lease,
            error_class=IngestionErrorClass.TEMPORARY_OBJECT_STORE,
            error_detail={"reason": "object_store_write_failed"},
            next_attempt_at=current_time() + timedelta(minutes=1),
            now=current_time(),
        )
        return False
    except SecFilingDependencyUnavailable:
        store.schedule_retry(
            lease,
            error_class=IngestionErrorClass.TEMPORARY_DATABASE,
            error_detail={"reason": "sec_filing_lineage_pending"},
            next_attempt_at=current_time() + timedelta(minutes=1),
            now=current_time(),
        )
        return False
    except SQLAlchemyError:
        store.schedule_retry(
            lease,
            error_class=IngestionErrorClass.TEMPORARY_DATABASE,
            error_detail={"reason": "database_write_failed"},
            next_attempt_at=current_time() + timedelta(minutes=1),
            now=current_time(),
        )
        return False
    except ValueError as error:
        store.dead_letter(
            lease,
            error_class=IngestionErrorClass.SCHEMA_DRIFT,
            error_detail={"error_type": type(error).__name__},
            now=current_time(),
        )
        return False
    except SecLeaseLost:
        return False
    try:
        heartbeat()
    except SecLeaseLost:
        return False
    if not store.complete(lease, now=current_time()):
        raise RuntimeError("SEC ingestion completion rejected")
    return True


def dispatch_queued_sec_jobs(
    engine: Engine,
    *,
    publish: PublishIngestion,
    now: datetime,
    limit: int = 25,
) -> int:
    checked_now = require_aware(now).astimezone(UTC)
    if limit < 1:
        raise ValueError("SEC dispatch limit must be positive")
    store = IngestionJobStore(engine)
    store.requeue_due(now=checked_now)
    store.recover_expired(now=checked_now)
    with engine.connect() as connection:
        job_ids = tuple(
            connection.execute(
                select(ingestion_job.c.id)
                .where(ingestion_job.c.provider == "SEC", ingestion_job.c.state == "QUEUED")
                .order_by(ingestion_job.c.created_at, ingestion_job.c.id)
                .limit(limit)
            ).scalars()
        )
    for queued_job_id in job_ids:
        publish(cast(UUID, queued_job_id))
    return len(job_ids)


def execute_alpha_earnings_ingestion_job(
    *,
    engine: Engine,
    raw_store: RawObjectStore,
    transport: AlphaCalendarTransport,
    job_id: UUID,
    now: datetime,
    worker_id: str,
) -> bool:
    """Persist one full Alpha CSV snapshot before its filtered typed events."""
    checked_now = require_aware(now).astimezone(UTC)
    store = IngestionJobStore(engine)
    lease = store.claim(
        job_id,
        worker_id=worker_id,
        now=checked_now,
        lease_for=ALPHA_LEASE,
    )
    if lease is None:
        return False
    with engine.connect() as connection:
        row = (
            connection.execute(select(ingestion_job).where(ingestion_job.c.id == job_id))
            .mappings()
            .one()
        )
    if row["provider"] != "ALPHA_VANTAGE" or row["dataset"] != FeedType.EARNINGS_CALENDAR.value:
        store.fail(
            lease,
            error_class=IngestionErrorClass.UNSUPPORTED_DATASET,
            error_detail={"provider": row["provider"], "dataset": row["dataset"]},
            now=checked_now,
        )
        return False
    try:
        batch = transport.fetch_batch(
            FeedType.EARNINGS_CALENDAR,
            "NVDA",
            row["window_end"],
        )
        persisted_at = max(checked_now, batch.observed_at)
        body_hash = hashlib.sha256(batch.body).hexdigest()
        raw_envelope = json.dumps(
            {
                "provider": batch.provider,
                "feed_type": batch.feed_type.value,
                "scope": "FULL_MARKET",
                "observed_at": batch.observed_at.isoformat(),
                "body_sha256": body_hash,
                "body_base64": b64encode(batch.body).decode("ascii"),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        content_hash = hashlib.sha256(raw_envelope).hexdigest()
        object_key = f"live/ALPHA_VANTAGE/earnings_calendar/{content_hash}.json"
        try:
            raw_store.put(object_key, raw_envelope, "application/json")
        except Exception as error:
            raise RawObjectStoreUnavailable("raw object store write failed") from error
        record = ProviderRecord(
            symbol=Symbol("NVDA"),
            feed_type=FeedType.EARNINGS_CALENDAR,
            provider="ALPHA_VANTAGE",
            event_time=batch.observed_at,
            available_at=batch.observed_at,
            ingested_at=persisted_at,
            content_hash=content_hash,
            raw_object_key=object_key,
            payload={"scope": "FULL_MARKET", "body_sha256": body_hash},
        )
        with engine.begin() as connection:
            raw_id = persist_raw_object(connection, record)
            connection.execute(
                insert(ingestion_raw_link)
                .values(job_id=job_id, raw_data_object_id=raw_id)
                .on_conflict_do_nothing(
                    index_elements=[
                        ingestion_raw_link.c.job_id,
                        ingestion_raw_link.c.raw_data_object_id,
                    ]
                )
            )
            identities = PostgresAlphaSymbolResolver(connection).identities(batch.observed_at)
            events = AlphaVantageNormalizer().normalize_calendar(
                batch,
                provider_to_canonical={
                    provider_symbol: str(identity.symbol)
                    for provider_symbol, identity in identities.items()
                },
            )
            fact_store = PostgresEarningsEventStore(connection)
            for event in events:
                normalized_values = {
                    "raw_data_object_id": raw_id,
                    "record_type": "earnings_event",
                    "record_key": (f"{event.provider_symbol}:{event.fiscal_date_end.isoformat()}"),
                    "normalization_version": "alpha-earnings-v1",
                    "payload": {
                        **event.payload,
                        "symbol": str(event.symbol),
                        "estimate": str(event.estimate) if event.estimate is not None else None,
                    },
                }
                normalized_id = connection.execute(
                    insert(normalized_record)
                    .values(**normalized_values)
                    .on_conflict_do_nothing(constraint="uq_normalized_record_version")
                    .returning(normalized_record.c.id)
                ).scalar_one_or_none()
                if normalized_id is None:
                    normalized_id = connection.execute(
                        select(normalized_record.c.id).where(
                            normalized_record.c.raw_data_object_id == raw_id,
                            normalized_record.c.record_type == "earnings_event",
                            normalized_record.c.record_key == normalized_values["record_key"],
                            normalized_record.c.normalization_version == "alpha-earnings-v1",
                        )
                    ).scalar_one()
                identity = identities[event.provider_symbol]
                fact_store.persist_event(
                    security_id=identity.security_id,
                    raw_id=raw_id,
                    normalized_id=cast(UUID, normalized_id),
                    event=event,
                )
            _persist_freshness_quality(
                connection=connection,
                raw_id=raw_id,
                provider="ALPHA_VANTAGE",
                dataset=FeedType.EARNINGS_CALENDAR.value,
                observed_at=persisted_at,
                latest_available_at=batch.observed_at,
            )
    except ProviderTransportError as error:
        if error.error_class in {
            IngestionErrorClass.TIMEOUT,
            IngestionErrorClass.NETWORK,
            IngestionErrorClass.RATE_LIMIT,
            IngestionErrorClass.PROVIDER_5XX,
        }:
            store.schedule_retry(
                lease,
                error_class=error.error_class,
                error_detail={"status_code": error.status_code},
                next_attempt_at=checked_now + (error.retry_after or timedelta(minutes=1)),
                now=checked_now,
            )
        else:
            store.dead_letter(
                lease,
                error_class=error.error_class,
                error_detail={"status_code": error.status_code},
                now=checked_now,
            )
        return False
    except SQLAlchemyError:
        store.schedule_retry(
            lease,
            error_class=IngestionErrorClass.TEMPORARY_DATABASE,
            error_detail={"reason": "database_write_failed"},
            next_attempt_at=checked_now + timedelta(minutes=1),
            now=checked_now,
        )
        return False
    except RawObjectStoreUnavailable:
        store.schedule_retry(
            lease,
            error_class=IngestionErrorClass.TEMPORARY_OBJECT_STORE,
            error_detail={"reason": "object_store_write_failed"},
            next_attempt_at=checked_now + timedelta(minutes=1),
            now=checked_now,
        )
        return False
    except ValueError as error:
        store.dead_letter(
            lease,
            error_class=IngestionErrorClass.SCHEMA_DRIFT,
            error_detail={"error_type": type(error).__name__},
            now=checked_now,
        )
        return False
    if not store.complete(lease, now=max(checked_now, batch.observed_at)):
        raise RuntimeError("Alpha earnings ingestion completion rejected")
    return True


def dispatch_queued_alpha_jobs(
    engine: Engine,
    *,
    publish: PublishIngestion,
    now: datetime,
    limit: int = 10,
) -> int:
    checked_now = require_aware(now).astimezone(UTC)
    if limit < 1:
        raise ValueError("Alpha dispatch limit must be positive")
    store = IngestionJobStore(engine)
    store.requeue_due(now=checked_now)
    store.recover_expired(now=checked_now)
    with engine.connect() as connection:
        job_ids = tuple(
            connection.execute(
                select(ingestion_job.c.id)
                .where(
                    ingestion_job.c.provider == "ALPHA_VANTAGE",
                    ingestion_job.c.state == "QUEUED",
                )
                .order_by(ingestion_job.c.created_at, ingestion_job.c.id)
                .limit(limit)
            ).scalars()
        )
    for queued_job_id in job_ids:
        publish(cast(UUID, queued_job_id))
    return len(job_ids)


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
        orphaned_keys = report_orphaned_raw_objects(
            engine,
            inventory,
            excluded_prefixes=("live/ALPACA/stream-recovery/",),
        )
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
    name="stock_platform.workers.ingestion_tasks.dispatch_alpha_ingestion_jobs"
)
def dispatch_alpha_ingestion_jobs() -> int:
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        return dispatch_queued_alpha_jobs(
            engine,
            publish=lambda job_id: celery_app.send_task(
                "stock_platform.workers.ingestion_tasks.run_alpha_earnings_ingestion_job",
                args=[str(job_id)],
                queue="ingestion-low",
            ),
            now=datetime.now(UTC),
        )
    finally:
        engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="stock_platform.workers.ingestion_tasks.run_alpha_earnings_ingestion_job"
)
def run_alpha_earnings_ingestion_job(job_id: str) -> bool:
    from stock_platform.infrastructure.providers.alpha_vantage import AlphaVantageProvider

    settings = Settings()
    engine = create_engine(settings.database_url)
    api_key = (
        settings.alpha_vantage_api_key.get_secret_value()
        if settings.alpha_vantage_api_key is not None
        else None
    )
    try:
        return execute_alpha_earnings_ingestion_job(
            engine=engine,
            raw_store=MinioRawObjectStore.from_settings(settings),
            transport=AlphaVantageProvider(api_key=api_key),
            job_id=UUID(job_id),
            now=datetime.now(UTC),
            worker_id="celery-alpha-earnings",
        )
    finally:
        engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="stock_platform.workers.ingestion_tasks.dispatch_sec_ingestion_jobs"
)
def dispatch_sec_ingestion_jobs() -> int:
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        return dispatch_queued_sec_jobs(
            engine,
            publish=lambda job_id: celery_app.send_task(
                "stock_platform.workers.ingestion_tasks.run_sec_ingestion_job",
                args=[str(job_id)],
                queue="ingestion-low",
            ),
            now=datetime.now(UTC),
        )
    finally:
        engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="stock_platform.workers.ingestion_tasks.run_sec_ingestion_job"
)
def run_sec_ingestion_job(job_id: str) -> bool:
    from stock_platform.infrastructure.providers.sec import SecProvider

    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            resolver = PostgresSecIdentityResolver(connection)
            return execute_sec_ingestion_job(
                engine=engine,
                raw_store=MinioRawObjectStore.from_settings(settings),
                transport=SecProvider(
                    user_agent=settings.sec_user_agent,
                    identity_resolver=resolver,
                ),
                job_id=UUID(job_id),
                now=datetime.now(UTC),
                worker_id="celery-sec-ingestion",
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
