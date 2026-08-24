"""Deterministic Alpaca REST normalization without persistence side effects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from zoneinfo import ZoneInfo

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    FeedType,
    MarketDataCoverage,
    MarketSession,
)
from stock_platform.infrastructure.providers.base import ProviderBatch

NEW_YORK = ZoneInfo("America/New_York")


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return require_aware(parsed).astimezone(UTC)


def _decimal(payload: dict[str, object], key: str) -> Decimal:
    try:
        value = Decimal(str(payload[key]))
    except (InvalidOperation, KeyError, TypeError) as error:
        raise ValueError(f"Alpaca field {key} is invalid") from error
    if not value.is_finite():
        raise ValueError(f"Alpaca field {key} must be finite")
    return value


def market_session_for(event_time: datetime) -> MarketSession:
    local_time = event_time.astimezone(NEW_YORK).time()
    if time(4) <= local_time < time(9, 30):
        return MarketSession.PRE_MARKET
    if time(9, 30) <= local_time < time(16):
        return MarketSession.REGULAR
    if time(16) <= local_time < time(20):
        return MarketSession.AFTER_HOURS
    return MarketSession.OVERNIGHT


@dataclass(frozen=True, slots=True)
class AlpacaBar:
    symbol: Symbol
    event_time: datetime
    available_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    coverage: MarketDataCoverage
    session: MarketSession
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class AlpacaNewsArticle:
    article_id: str
    symbols: tuple[Symbol, ...]
    headline: str
    published_at: datetime
    available_at: datetime
    observed_at: datetime | None
    pit_eligible: bool
    source: str
    summary: str
    payload: dict[str, object]


class AlpacaNormalizer:
    def normalize_batch(
        self,
        batch: ProviderBatch,
    ) -> tuple[AlpacaBar, ...] | tuple[AlpacaNewsArticle, ...]:
        try:
            document = json.loads(batch.body, parse_float=Decimal, parse_int=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Alpaca REST payload is invalid JSON") from error
        if not isinstance(document, dict):
            raise ValueError("Alpaca REST payload must be an object")
        if batch.feed_type is FeedType.PRICE_BARS:
            return self._bars(batch, cast(dict[str, object], document))
        if batch.feed_type is FeedType.COMPANY_NEWS:
            return self._news(batch, cast(dict[str, object], document))
        raise ValueError(f"unsupported Alpaca normalization feed: {batch.feed_type}")

    def _bars(
        self,
        batch: ProviderBatch,
        document: dict[str, object],
    ) -> tuple[AlpacaBar, ...]:
        grouped = document.get("bars")
        if not isinstance(grouped, dict):
            raise ValueError("Alpaca bars payload is missing bars")
        raw_bars = grouped.get(str(batch.symbol), ())
        if not isinstance(raw_bars, list):
            raise ValueError("Alpaca symbol bars must be a list")
        coverage_value = batch.headers.get("X-Alpaca-Data-Feed", "IEX").upper()
        coverage = MarketDataCoverage(coverage_value)
        bars: list[AlpacaBar] = []
        for raw_bar in raw_bars:
            if not isinstance(raw_bar, dict):
                raise ValueError("Alpaca bar must be an object")
            payload = cast(dict[str, object], raw_bar)
            event_time = _timestamp(payload["t"])
            bars.append(
                AlpacaBar(
                    symbol=batch.symbol,
                    event_time=event_time,
                    available_at=require_aware(batch.observed_at).astimezone(UTC),
                    open=_decimal(payload, "o"),
                    high=_decimal(payload, "h"),
                    low=_decimal(payload, "l"),
                    close=_decimal(payload, "c"),
                    volume=_decimal(payload, "v"),
                    coverage=coverage,
                    session=market_session_for(event_time),
                    payload=payload,
                )
            )
        return tuple(bars)

    def _news(
        self,
        batch: ProviderBatch,
        document: dict[str, object],
    ) -> tuple[AlpacaNewsArticle, ...]:
        raw_news = document.get("news")
        if not isinstance(raw_news, list):
            raise ValueError("Alpaca news payload is missing news")
        articles: list[AlpacaNewsArticle] = []
        for raw_article in raw_news:
            if not isinstance(raw_article, dict):
                raise ValueError("Alpaca news article must be an object")
            payload = cast(dict[str, Any], raw_article)
            raw_symbols = payload.get("symbols", ())
            if not isinstance(raw_symbols, list):
                raise ValueError("Alpaca news symbols must be a list")
            published_at = _timestamp(payload["created_at"])
            provider_observed_at = (
                _timestamp(payload["observed_at"])
                if payload.get("observed_at") is not None
                else None
            )
            available_at = require_aware(batch.observed_at).astimezone(UTC)
            if provider_observed_at is not None and not (
                published_at <= provider_observed_at <= available_at
            ):
                raise ValueError("Alpaca news observation time is inconsistent")
            articles.append(
                AlpacaNewsArticle(
                    article_id=str(payload["id"]),
                    symbols=tuple(Symbol(str(symbol)) for symbol in raw_symbols),
                    headline=str(payload["headline"]),
                    published_at=published_at,
                    available_at=available_at,
                    observed_at=provider_observed_at,
                    pit_eligible=provider_observed_at is not None,
                    source=str(payload.get("source", "")),
                    summary=str(payload.get("summary", "")),
                    payload=payload,
                )
            )
        return tuple(articles)
