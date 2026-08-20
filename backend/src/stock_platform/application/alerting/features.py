"""Decimal-only point-in-time anomaly feature calculation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware

_ZERO = Decimal("0")
_ONE = Decimal("1")


def _require_decimal(name: str, value: Decimal | None) -> None:
    if value is not None and not isinstance(value, Decimal):
        raise TypeError(f"{name} must use Decimal")


@dataclass(frozen=True, slots=True)
class MinuteBar:
    symbol: Symbol
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    previous_close: Decimal | None
    provider: str
    content_hash: str
    raw_object_key: str
    raw_payload: Mapping[str, object]
    conflict: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        for field in ("event_time", "available_at", "ingested_at"):
            value = require_aware(getattr(self, field)).astimezone(UTC)
            object.__setattr__(self, field, value)
        if not self.event_time <= self.available_at <= self.ingested_at:
            raise ValueError(
                "bar timestamps must satisfy event_time <= available_at <= ingested_at"
            )
        for name in ("open", "high", "low", "close", "volume", "previous_close"):
            _require_decimal(name, getattr(self, name))
        if self.volume < _ZERO:
            raise ValueError("volume cannot be negative")
        if len(self.content_hash) != 64:
            raise ValueError("content_hash must be SHA-256")


@dataclass(frozen=True, slots=True)
class DataQuality:
    freshness: timedelta
    coverage: Decimal
    provider: str
    delay: timedelta
    conflict: bool


@dataclass(frozen=True, slots=True)
class GapContext:
    session_open: Decimal
    previous_close: Decimal

    def __post_init__(self) -> None:
        _require_decimal("session_open", self.session_open)
        _require_decimal("previous_close", self.previous_close)


@dataclass(frozen=True, slots=True)
class AnomalyFeatures:
    symbol: Symbol
    event_time: datetime
    five_minute_return: Decimal | None
    relative_volume: Decimal | None
    return_zscore: Decimal | None
    volume_zscore: Decimal | None
    volatility_zscore: Decimal | None
    gap: Decimal | None
    breakout: bool | None
    data_quality: DataQuality

    def metrics(self) -> dict[str, str | bool | None]:
        return {
            "five_minute_return": _decimal_text(self.five_minute_return),
            "relative_volume": _decimal_text(self.relative_volume),
            "return_zscore": _decimal_text(self.return_zscore),
            "volume_zscore": _decimal_text(self.volume_zscore),
            "volatility_zscore": _decimal_text(self.volatility_zscore),
            "gap": _decimal_text(self.gap),
            "breakout": self.breakout,
            "freshness_seconds": _decimal_text(
                Decimal(str(self.data_quality.freshness.total_seconds()))
            ),
            "coverage": str(self.data_quality.coverage),
            "provider": self.data_quality.provider,
            "delay_seconds": _decimal_text(Decimal(str(self.data_quality.delay.total_seconds()))),
            "conflict": self.data_quality.conflict,
        }


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.normalize()) if value != _ZERO else "0"


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, _ZERO) / Decimal(len(values))


def _zscore(value: Decimal, history: Sequence[Decimal]) -> Decimal | None:
    mean = _mean(history)
    if mean is None or len(history) < 2:
        return None
    variance = sum(((item - mean) ** 2 for item in history), _ZERO) / Decimal(len(history))
    if variance == _ZERO:
        return _ZERO
    return (value - mean) / variance.sqrt()


class FeatureCalculator:
    def __init__(self, *, lookback: int = 5) -> None:
        if lookback < 2:
            raise ValueError("lookback must be at least two")
        self.lookback = lookback

    def calculate(
        self,
        bars: Sequence[MinuteBar],
        *,
        evaluated_at: datetime,
        gap_context: GapContext | None = None,
    ) -> AnomalyFeatures:
        cutoff = require_aware(evaluated_at).astimezone(UTC)
        ordered = tuple(sorted(bars, key=lambda item: item.event_time))
        if not ordered:
            raise ValueError("at least one bar is required")
        if any(item.available_at > cutoff for item in ordered):
            raise ValueError("all bars must be available at evaluation time")
        symbol = ordered[-1].symbol
        if any(item.symbol != symbol for item in ordered):
            raise ValueError("all bars must have the same symbol")

        window = ordered[-(self.lookback + 1) :]
        latest = window[-1]
        prior = window[:-1]
        five_minute_return = (
            latest.close / window[0].close - _ONE
            if len(window) == self.lookback + 1 and window[0].close != _ZERO
            else None
        )
        prior_volume_mean = _mean([item.volume for item in prior])
        relative_volume = (
            None
            if prior_volume_mean is None or prior_volume_mean == _ZERO
            else latest.volume / prior_volume_mean
        )
        returns = [
            current.close / previous.close - _ONE
            for previous, current in zip(window, window[1:], strict=False)
            if previous.close != _ZERO
        ]
        current_return = returns[-1] if returns else None
        return_history = returns[:-1]
        return_zscore = (
            _zscore(current_return, return_history) if current_return is not None else None
        )
        volume_zscore = _zscore(latest.volume, [item.volume for item in prior])
        volatility_zscore = (
            _zscore(abs(current_return), [abs(item) for item in return_history])
            if current_return is not None
            else None
        )
        gap = (
            None
            if gap_context is None or gap_context.previous_close == _ZERO
            else gap_context.session_open / gap_context.previous_close - _ONE
        )
        breakout = None
        if prior:
            breakout = latest.close > max(item.high for item in prior) or latest.close < min(
                item.low for item in prior
            )
        values: tuple[object | None, ...] = (
            five_minute_return,
            relative_volume,
            return_zscore,
            volume_zscore,
            volatility_zscore,
            gap,
            breakout,
        )
        coverage = Decimal(sum(value is not None for value in values)) / Decimal(len(values))
        quality = DataQuality(
            freshness=cutoff - latest.available_at,
            coverage=coverage,
            provider=latest.provider,
            delay=latest.ingested_at - latest.event_time,
            conflict=any(item.conflict for item in window),
        )
        return AnomalyFeatures(
            symbol=symbol,
            event_time=latest.event_time,
            five_minute_return=five_minute_return,
            relative_volume=relative_volume,
            return_zscore=return_zscore,
            volume_zscore=volume_zscore,
            volatility_zscore=volatility_zscore,
            gap=gap,
            breakout=breakout,
            data_quality=quality,
        )
