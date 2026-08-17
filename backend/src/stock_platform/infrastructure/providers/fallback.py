"""Deterministic provider fallback, freshness, conflict, and circuit policy."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from stock_platform.infrastructure.providers.base import (
    FeedType,
    ProviderResponse,
    ProviderStatus,
    ResearchDataProvider,
)


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
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._max_staleness = max_staleness
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._compare_on_success = compare_on_success
        self._failures = 0
        self._opened_at: datetime | None = None

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        circuit_open = self._opened_at is not None and as_of - self._opened_at < self._reset_timeout
        if circuit_open:
            return self._fallback_result(
                feed_type,
                symbol,
                as_of,
                warning=f"circuit_open={self._primary.name}",
            )
        if self._opened_at is not None:
            self._opened_at = None
            self._failures = 0

        primary = self._primary.fetch(feed_type, symbol, as_of)
        if primary.status is ProviderStatus.OK:
            self._failures = 0
            if self._compare_on_success:
                return self._compare(primary, feed_type, symbol, as_of)
            return primary
        if primary.status in {ProviderStatus.NOT_FOUND, ProviderStatus.NOT_SUPPORTED}:
            return primary

        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._opened_at = as_of
        return self._fallback_result(
            feed_type,
            symbol,
            as_of,
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
