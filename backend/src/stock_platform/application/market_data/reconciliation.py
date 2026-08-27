"""Deterministic, coverage-scoped market-bar reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import MarketDataCoverage, MarketSession


class ReconciliationKind(StrEnum):
    MISSING_INTERVAL = "MISSING_INTERVAL"
    DUPLICATE = "DUPLICATE"
    REVISION = "REVISION"
    OHLC_INVALID = "OHLC_INVALID"
    VOLUME_INVALID = "VOLUME_INVALID"
    VOLUME_MISMATCH = "VOLUME_MISMATCH"


@dataclass(frozen=True, slots=True)
class BarObservation:
    normalized_record_id: UUID
    symbol: str
    event_time: datetime
    available_at: datetime
    coverage: MarketDataCoverage
    session: MarketSession
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("bar symbol is required")
        event = require_aware(self.event_time).astimezone(UTC)
        available = require_aware(self.available_at).astimezone(UTC)
        if available < event:
            raise ValueError("bar availability cannot precede event time")
        if any(isinstance(value, float) for value in self._values()):
            raise TypeError("bar numeric values must use Decimal")
        if any(not value.is_finite() for value in self._values()):
            raise ValueError("bar numeric values must be finite")
        object.__setattr__(self, "event_time", event)
        object.__setattr__(self, "available_at", available)

    def _values(self) -> tuple[Decimal, ...]:
        return self.open, self.high, self.low, self.close, self.volume

    def signature(self) -> tuple[Decimal, ...]:
        return self._values()


@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    kind: ReconciliationKind
    symbol: str
    coverage: MarketDataCoverage
    session: MarketSession
    event_time: datetime
    details: dict[str, object]


def _finding(
    kind: ReconciliationKind,
    bar: BarObservation,
    **details: object,
) -> ReconciliationFinding:
    return ReconciliationFinding(
        kind=kind,
        symbol=bar.symbol,
        coverage=bar.coverage,
        session=bar.session,
        event_time=bar.event_time,
        details=dict(details),
    )


def reconcile_bars(
    bars: tuple[BarObservation, ...],
    *,
    expected_interval: timedelta,
) -> tuple[ReconciliationFinding, ...]:
    if expected_interval <= timedelta(0):
        raise ValueError("expected interval must be positive")
    findings: list[ReconciliationFinding] = []
    grouped: dict[tuple[str, MarketDataCoverage, MarketSession], list[BarObservation]] = {}
    for bar in bars:
        grouped.setdefault((bar.symbol, bar.coverage, bar.session), []).append(bar)
        if (
            bar.high < max(bar.open, bar.close)
            or bar.low > min(bar.open, bar.close)
            or bar.low > bar.high
        ):
            findings.append(_finding(ReconciliationKind.OHLC_INVALID, bar))
        if bar.volume < 0:
            findings.append(_finding(ReconciliationKind.VOLUME_INVALID, bar))

    for stream in grouped.values():
        by_time: dict[datetime, list[BarObservation]] = {}
        for bar in stream:
            by_time.setdefault(bar.event_time, []).append(bar)
        ordered_times = sorted(by_time)
        for previous, current in zip(ordered_times, ordered_times[1:], strict=False):
            missing = int((current - previous) / expected_interval) - 1
            if missing > 0:
                findings.append(
                    _finding(
                        ReconciliationKind.MISSING_INTERVAL,
                        by_time[previous][0],
                        missing_count=missing,
                        next_event_time=current.isoformat(),
                    )
                )
        for versions in by_time.values():
            signatures: dict[tuple[Decimal, ...], int] = {}
            for version in versions:
                signatures[version.signature()] = signatures.get(version.signature(), 0) + 1
            if any(count > 1 for count in signatures.values()):
                findings.append(_finding(ReconciliationKind.DUPLICATE, versions[0]))
            if len(signatures) > 1:
                latest = max(
                    versions, key=lambda item: (item.available_at, item.normalized_record_id)
                )
                findings.append(
                    _finding(
                        ReconciliationKind.REVISION,
                        latest,
                        version_count=len(signatures),
                    )
                )
    return tuple(
        sorted(
            findings,
            key=lambda item: (
                item.symbol,
                item.coverage.value,
                item.session.value,
                item.event_time,
                item.kind.value,
            ),
        )
    )


def reconcile_minute_to_daily(
    minutes: tuple[BarObservation, ...],
    daily: BarObservation,
) -> tuple[ReconciliationFinding, ...]:
    matching = tuple(
        minute
        for minute in minutes
        if (minute.symbol, minute.coverage, minute.session)
        == (daily.symbol, daily.coverage, daily.session)
    )
    if not matching:
        return ()
    minute_volume = sum((minute.volume for minute in matching), start=Decimal(0))
    if minute_volume == daily.volume:
        return ()
    return (
        _finding(
            ReconciliationKind.VOLUME_MISMATCH,
            daily,
            minute_volume=str(minute_volume),
            daily_volume=str(daily.volume),
        ),
    )
