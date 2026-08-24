from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from stock_platform.application.ingestion.jobs import IngestionLease
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.ingestion.models import FeedType, IngestionErrorClass
from stock_platform.infrastructure.providers.base import (
    ProviderBatch,
    ProviderRateLimit,
    ProviderTransportError,
)

NOW = datetime(2026, 8, 24, 6, tzinfo=UTC)


class StaticTransport:
    def __init__(self, batch: ProviderBatch) -> None:
        self.batch = batch
        self.calls: list[tuple[FeedType, str, datetime]] = []

    def fetch_batch(
        self,
        feed_type: FeedType,
        symbol: str,
        as_of: datetime,
    ) -> ProviderBatch:
        self.calls.append((feed_type, symbol, as_of))
        return self.batch


class RecordingJobStore:
    def __init__(self) -> None:
        self.completed: list[tuple[IngestionLease, datetime]] = []

    def complete(self, lease: IngestionLease, *, now: datetime) -> bool:
        self.completed.append((lease, now))
        return True


class RecordingRetryJobStore(RecordingJobStore):
    def __init__(self) -> None:
        super().__init__()
        self.retries: list[dict[str, object]] = []

    def schedule_retry(
        self,
        lease: IngestionLease,
        *,
        error_class: IngestionErrorClass,
        error_detail: dict[str, object],
        next_attempt_at: datetime,
        now: datetime,
    ) -> bool:
        self.retries.append(
            {
                "lease": lease,
                "error_class": error_class,
                "error_detail": error_detail,
                "next_attempt_at": next_attempt_at,
                "now": now,
            }
        )
        return True


class RateLimitedTransport:
    def fetch_batch(
        self,
        feed_type: FeedType,
        symbol: str,
        as_of: datetime,
    ) -> ProviderBatch:
        raise ProviderTransportError(
            error_class=IngestionErrorClass.RATE_LIMIT,
            status_code=429,
            retry_after=timedelta(seconds=120),
        )


class InvalidAuthTransport:
    def fetch_batch(
        self,
        feed_type: FeedType,
        symbol: str,
        as_of: datetime,
    ) -> ProviderBatch:
        raise ProviderTransportError(
            error_class=IngestionErrorClass.INVALID_AUTH,
            status_code=401,
        )


class RecordingFailureJobStore(RecordingRetryJobStore):
    def __init__(self) -> None:
        super().__init__()
        self.failures: list[dict[str, object]] = []

    def fail(
        self,
        lease: IngestionLease,
        *,
        error_class: IngestionErrorClass,
        error_detail: dict[str, object],
        now: datetime,
    ) -> bool:
        self.failures.append(
            {
                "lease": lease,
                "error_class": error_class,
                "error_detail": error_detail,
                "now": now,
            }
        )
        return True


def _batch() -> ProviderBatch:
    return ProviderBatch(
        provider="ALPACA",
        feed_type=FeedType.PRICE_BARS,
        symbol=Symbol("NVDA"),
        query_as_of=NOW,
        observed_at=NOW,
        body=b'{"bars":[],"symbol":"NVDA"}',
        headers={},
        next_page_token=None,
        rate_limit=ProviderRateLimit(),
    )


def _lease() -> IngestionLease:
    return IngestionLease(
        job_id=uuid4(),
        token=uuid4(),
        generation=1,
        expires_at=NOW + timedelta(minutes=5),
    )


def test_coordinator_persists_transport_batch_then_completes_job() -> None:
    module_name = "stock_platform.application.ingestion.coordinator"
    assert importlib.util.find_spec(module_name) is not None, "ingestion coordinator is missing"
    module = importlib.import_module(module_name)
    coordinator_type = getattr(module, "IngestionCoordinator", None)
    assert coordinator_type is not None
    batch = _batch()
    transport = StaticTransport(batch)
    store = RecordingJobStore()
    persisted: list[ProviderBatch] = []
    lease = _lease()
    coordinator = coordinator_type(
        job_store=store,
        persist_batch=persisted.append,
    )

    result = coordinator.run(
        lease=lease,
        transport=transport,
        feed_type=FeedType.PRICE_BARS,
        symbol="NVDA",
        as_of=NOW,
        now=NOW,
    )

    assert result == batch
    assert transport.calls == [(FeedType.PRICE_BARS, "NVDA", NOW)]
    assert persisted == [batch]
    assert store.completed == [(lease, NOW)]


def test_coordinator_can_defer_completion_for_paginated_work() -> None:
    module = importlib.import_module("stock_platform.application.ingestion.coordinator")
    batch = _batch()
    store = RecordingJobStore()
    coordinator = module.IngestionCoordinator(
        job_store=store,
        persist_batch=lambda _: None,
    )

    assert (
        coordinator.run(
            lease=_lease(),
            transport=StaticTransport(batch),
            feed_type=FeedType.PRICE_BARS,
            symbol="NVDA",
            as_of=NOW,
            now=NOW,
            complete_job=False,
        )
        == batch
    )
    assert store.completed == []


def test_provider_batch_and_coordinator_canonicalize_aware_times_to_utc() -> None:
    offset = datetime.fromisoformat("2026-08-24T14:00:00+08:00")
    batch = ProviderBatch(
        provider="ALPACA",
        feed_type=FeedType.PRICE_BARS,
        symbol=Symbol("NVDA"),
        query_as_of=offset,
        observed_at=offset,
        body=b'{"bars":[],"symbol":"NVDA"}',
        headers={},
        next_page_token=None,
        rate_limit=ProviderRateLimit(),
    )
    transport = StaticTransport(batch)
    store = RecordingJobStore()
    coordinator = importlib.import_module(
        "stock_platform.application.ingestion.coordinator"
    ).IngestionCoordinator(job_store=store, persist_batch=lambda _: None)

    coordinator.run(
        lease=_lease(),
        transport=transport,
        feed_type=FeedType.PRICE_BARS,
        symbol="NVDA",
        as_of=offset,
        now=offset,
    )

    assert batch.query_as_of == NOW
    assert batch.observed_at == NOW
    assert transport.calls == [(FeedType.PRICE_BARS, "NVDA", NOW)]
    assert store.completed[0][1] == NOW


def test_coordinator_schedules_retry_after_without_blocking_or_persisting() -> None:
    module = importlib.import_module("stock_platform.application.ingestion.coordinator")
    store = RecordingRetryJobStore()
    persisted: list[ProviderBatch] = []
    lease = _lease()
    coordinator = module.IngestionCoordinator(
        job_store=store,
        persist_batch=persisted.append,
    )

    result = coordinator.run(
        lease=lease,
        transport=RateLimitedTransport(),
        feed_type=FeedType.PRICE_BARS,
        symbol="NVDA",
        as_of=NOW,
        now=NOW,
    )

    assert result is None
    assert persisted == []
    assert store.completed == []
    assert store.retries == [
        {
            "lease": lease,
            "error_class": IngestionErrorClass.RATE_LIMIT,
            "error_detail": {"provider_status": 429, "retry_after_seconds": 120},
            "next_attempt_at": NOW + timedelta(seconds=120),
            "now": NOW,
        }
    ]


def test_coordinator_fails_non_retryable_transport_error() -> None:
    module = importlib.import_module("stock_platform.application.ingestion.coordinator")
    store = RecordingFailureJobStore()
    coordinator = module.IngestionCoordinator(job_store=store, persist_batch=lambda _: None)
    lease = _lease()

    result = coordinator.run(
        lease=lease,
        transport=InvalidAuthTransport(),
        feed_type=FeedType.PRICE_BARS,
        symbol="NVDA",
        as_of=NOW,
        now=NOW,
    )

    assert result is None
    assert store.retries == []
    assert store.completed == []
    assert store.failures == [
        {
            "lease": lease,
            "error_class": IngestionErrorClass.INVALID_AUTH,
            "error_detail": {"provider_status": 401},
            "now": NOW,
        }
    ]
