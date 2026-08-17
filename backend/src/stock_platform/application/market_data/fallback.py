"""Deterministic provider fallback, freshness, conflict, and circuit policy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.providers.base import (
    FeedType,
    ProviderResponse,
    ProviderStatus,
    ResearchDataProvider,
)


@dataclass(frozen=True, slots=True)
class ProviderHealthSnapshot:
    primary: str
    fallback: str
    circuit_open: bool
    failure_count: int
    checked_at: datetime


class FallbackPolicy:
    def __init__(
        self,
        *,
        primary: ResearchDataProvider,
        fallback: ResearchDataProvider,
        max_staleness: timedelta = timedelta(days=1),
        failure_threshold: int = 2,
        reset_timeout: timedelta = timedelta(minutes=5),
        compare_on_success: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._max_staleness = max_staleness
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._compare_on_success = compare_on_success
        self._clock = clock or (lambda: datetime.now(UTC))
        self._failures = 0
        self._opened_at: datetime | None = None

    def _circuit_is_open(self, checked_at: datetime) -> bool:
        return self._opened_at is not None and checked_at - self._opened_at < self._reset_timeout

    def health(self) -> ProviderHealthSnapshot:
        checked_at = require_aware(self._clock())
        return ProviderHealthSnapshot(
            primary=self._primary.name,
            fallback=self._fallback.name,
            circuit_open=self._circuit_is_open(checked_at),
            failure_count=self._failures,
            checked_at=checked_at,
        )

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        query_as_of = require_aware(as_of)
        checked_at = require_aware(self._clock())
        circuit_open = self._circuit_is_open(checked_at)
        if circuit_open:
            return self._fallback_result(
                feed_type,
                symbol,
                query_as_of,
                warning=f"circuit_open={self._primary.name}",
            )
        if self._opened_at is not None:
            self._opened_at = None
            self._failures = 0

        primary = self._primary.fetch(feed_type, symbol, query_as_of)
        if primary.status is ProviderStatus.OK:
            if any(record.available_at > query_as_of for record in primary.records):
                self._failures += 1
                if self._failures >= self._failure_threshold:
                    self._opened_at = checked_at
                return self._fallback_result(
                    feed_type,
                    symbol,
                    query_as_of,
                    warning="future_primary_rejected",
                )
            self._failures = 0
            if self._compare_on_success:
                return self._compare(primary, feed_type, symbol, query_as_of)
            return primary
        if primary.status in {ProviderStatus.NOT_FOUND, ProviderStatus.NOT_SUPPORTED}:
            return primary

        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._opened_at = checked_at
        return self._fallback_result(
            feed_type,
            symbol,
            query_as_of,
            warning=f"fallback_from={self._primary.name}",
        )

    def _fallback_result(
        self,
        feed_type: FeedType,
        symbol: str,
        as_of: datetime,
        *,
        warning: str,
    ) -> ProviderResponse:
        fallback = self._fallback.fetch(feed_type, symbol, as_of)
        if fallback.status is ProviderStatus.OK and fallback.records:
            if any(record.available_at > as_of for record in fallback.records):
                return replace(
                    fallback,
                    status=ProviderStatus.UNAVAILABLE,
                    records=(),
                    warnings=fallback.warnings + (warning, "future_fallback_rejected"),
                    missingness="UNAVAILABLE",
                )
            freshest = max(record.available_at for record in fallback.records)
            if as_of - freshest > self._max_staleness:
                return replace(
                    fallback,
                    status=ProviderStatus.UNAVAILABLE,
                    records=(),
                    warnings=fallback.warnings + (warning, "stale_fallback_rejected"),
                    missingness="UNAVAILABLE",
                )
        return replace(fallback, warnings=fallback.warnings + (warning,))

    def _compare(
        self,
        primary: ProviderResponse,
        feed_type: FeedType,
        symbol: str,
        as_of: datetime,
    ) -> ProviderResponse:
        fallback = self._fallback.fetch(feed_type, symbol, as_of)
        if fallback.status is not ProviderStatus.OK:
            return primary
        if any(record.available_at > as_of for record in fallback.records):
            return primary
        primary_payloads = tuple(record.payload for record in primary.records)
        fallback_payloads = tuple(record.payload for record in fallback.records)
        if primary_payloads == fallback_payloads:
            return primary
        marked = tuple(
            replace(record, quality_flags=tuple(sorted({*record.quality_flags, "conflict"})))
            for record in primary.records
        )
        return replace(
            primary,
            records=marked,
            warnings=primary.warnings + (f"provider_conflict={fallback.provider}",),
        )
