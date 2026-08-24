"""Application-owned coordination for provider transport and durable ingestion state."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from stock_platform.application.ingestion.jobs import IngestionLease
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    FeedType,
    IngestionErrorClass,
    RetryDisposition,
    retry_disposition,
)
from stock_platform.infrastructure.providers.base import ProviderBatch, ProviderTransportError


class BatchTransport(Protocol):
    def fetch_batch(
        self,
        feed_type: FeedType,
        symbol: str,
        as_of: datetime,
    ) -> ProviderBatch: ...


class CoordinatedJobStore(Protocol):
    def complete(self, lease: IngestionLease, *, now: datetime) -> bool: ...

    def schedule_retry(
        self,
        lease: IngestionLease,
        *,
        error_class: IngestionErrorClass,
        error_detail: dict[str, object],
        next_attempt_at: datetime,
        now: datetime,
    ) -> bool: ...

    def fail(
        self,
        lease: IngestionLease,
        *,
        error_class: IngestionErrorClass,
        error_detail: dict[str, object],
        now: datetime,
    ) -> bool: ...


PersistBatch = Callable[[ProviderBatch], None]


class IngestionCoordinator:
    def __init__(
        self,
        *,
        job_store: CoordinatedJobStore,
        persist_batch: PersistBatch,
    ) -> None:
        self._job_store = job_store
        self._persist_batch = persist_batch

    def run(
        self,
        *,
        lease: IngestionLease,
        transport: BatchTransport,
        feed_type: FeedType,
        symbol: str,
        as_of: datetime,
        now: datetime,
        complete_job: bool = True,
    ) -> ProviderBatch | None:
        checked_as_of = require_aware(as_of).astimezone(UTC)
        checked_now = require_aware(now).astimezone(UTC)
        try:
            batch = transport.fetch_batch(feed_type, symbol, checked_as_of)
        except ProviderTransportError as error:
            if retry_disposition(error.error_class) is not RetryDisposition.RETRYABLE:
                if not self._job_store.fail(
                    lease,
                    error_class=error.error_class,
                    error_detail={"provider_status": error.status_code},
                    now=checked_now,
                ):
                    raise RuntimeError("ingestion failure recording rejected") from error
                return None
            retry_after = error.retry_after or timedelta(minutes=1)
            retry_seconds = int(retry_after.total_seconds())
            if not self._job_store.schedule_retry(
                lease,
                error_class=error.error_class,
                error_detail={
                    "provider_status": error.status_code,
                    "retry_after_seconds": retry_seconds,
                },
                next_attempt_at=checked_now + retry_after,
                now=checked_now,
            ):
                raise RuntimeError("ingestion retry scheduling rejected") from error
            return None
        self._persist_batch(batch)
        if complete_job and not self._job_store.complete(lease, now=checked_now):
            raise RuntimeError("ingestion job completion rejected")
        return batch
