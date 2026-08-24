"""Point-in-time repositories that never expose data from the future."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from sqlalchemy import Connection, Engine, and_, select

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import MarketDataCoverage, MarketSession
from stock_platform.infrastructure.db.models.tables import (
    market_bar,
    news_article,
    normalized_record,
    raw_data_object,
)
from stock_platform.infrastructure.providers.base import (
    FeedType,
    ProviderRecord,
    ProviderResponse,
    ProviderStatus,
)


class PointInTimeRepository(Protocol):
    def as_of(
        self, *, symbol: str, feed_type: FeedType, decision_time: datetime
    ) -> ProviderResponse: ...


def is_visible_at(*, event_time: datetime, available_at: datetime, decision_time: datetime) -> bool:
    event = require_aware(event_time)
    available = require_aware(available_at)
    cutoff = require_aware(decision_time)
    return event <= cutoff and available <= cutoff


def select_latest_visible_revisions(
    records: Iterable[ProviderRecord],
    *,
    decision_time: datetime,
) -> tuple[ProviderRecord, ...]:
    cutoff = require_aware(decision_time)
    latest: dict[
        tuple[Symbol, FeedType, datetime, str, str | None, str | None, str | None], ProviderRecord
    ] = {}
    for record in records:
        if not is_visible_at(
            event_time=record.event_time,
            available_at=record.available_at,
            decision_time=cutoff,
        ):
            continue
        coverage = record.payload.get("coverage")
        session = record.payload.get("session")
        article_id = (
            record.payload.get("article_id") or record.payload.get("id")
            if record.feed_type is FeedType.COMPANY_NEWS
            else None
        )
        key = (
            record.symbol,
            record.feed_type,
            record.event_time,
            record.provider,
            str(coverage) if coverage is not None else None,
            str(session) if session is not None else None,
            str(article_id) if article_id is not None else None,
        )
        existing = latest.get(key)
        rank = (
            record.available_at,
            record.ingested_at,
            record.content_hash,
            record.raw_object_key,
        )
        if existing is None or rank > (
            existing.available_at,
            existing.ingested_at,
            existing.content_hash,
            existing.raw_object_key,
        ):
            latest[key] = record
    return tuple(
        sorted(
            latest.values(),
            key=lambda record: (
                record.event_time,
                record.available_at,
                record.ingested_at,
                record.content_hash,
                record.raw_object_key,
            ),
        )
    )


class PostgresMarketDataRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def as_of(
        self,
        *,
        symbol: str,
        feed_type: FeedType,
        decision_time: datetime,
        coverage: MarketDataCoverage | None = None,
        session: MarketSession = MarketSession.REGULAR,
    ) -> ProviderResponse:
        query_as_of = require_aware(decision_time)
        normalized_symbol = Symbol(symbol)
        if feed_type is FeedType.PRICE_BARS and coverage is not None:
            rows = self._connection.execute(
                select(market_bar)
                .where(
                    market_bar.c.symbol == str(normalized_symbol),
                    market_bar.c.coverage == coverage.value,
                    market_bar.c.session == session.value,
                    market_bar.c.event_time <= query_as_of,
                    market_bar.c.available_at <= query_as_of,
                )
                .order_by(
                    market_bar.c.event_time,
                    market_bar.c.available_at,
                    market_bar.c.ingested_at,
                    market_bar.c.content_hash,
                )
            ).mappings()
            records = tuple(
                ProviderRecord(
                    symbol=normalized_symbol,
                    feed_type=feed_type,
                    provider=str(row["provider"]),
                    event_time=row["event_time"],
                    available_at=row["available_at"],
                    ingested_at=row["ingested_at"],
                    content_hash=str(row["content_hash"]),
                    raw_object_key=str(row["raw_object_key"]),
                    payload={
                        "open": str(row["open"]),
                        "high": str(row["high"]),
                        "low": str(row["low"]),
                        "close": str(row["close"]),
                        "volume": str(row["volume"]),
                        "coverage": str(row["coverage"]),
                        "session": str(row["session"]),
                    },
                )
                for row in rows
            )
            visible = select_latest_visible_revisions(records, decision_time=query_as_of)
            return ProviderResponse(
                status=ProviderStatus.OK if visible else ProviderStatus.NOT_FOUND,
                provider="ALPACA",
                feed_type=feed_type,
                symbol=normalized_symbol,
                query_as_of=query_as_of,
                records=visible,
                missingness=None if visible else "MISSING",
            )
        if feed_type is FeedType.COMPANY_NEWS:
            rows = self._connection.execute(
                select(
                    news_article, raw_data_object.c.content_hash, raw_data_object.c.raw_object_key
                )
                .join(
                    raw_data_object,
                    news_article.c.raw_data_object_id == raw_data_object.c.id,
                )
                .where(
                    news_article.c.symbols.contains([str(normalized_symbol)]),
                    news_article.c.pit_eligible.is_(True),
                    news_article.c.published_at <= query_as_of,
                    news_article.c.available_at <= query_as_of,
                    raw_data_object.c.event_time <= query_as_of,
                    raw_data_object.c.available_at <= query_as_of,
                )
                .order_by(
                    news_article.c.published_at,
                    news_article.c.available_at,
                    news_article.c.ingested_at,
                    news_article.c.id,
                )
            ).mappings()
            records = tuple(
                ProviderRecord(
                    symbol=normalized_symbol,
                    feed_type=feed_type,
                    provider=str(row["provider"]),
                    event_time=row["published_at"],
                    available_at=row["available_at"],
                    ingested_at=row["ingested_at"],
                    content_hash=str(row["content_hash"]),
                    raw_object_key=str(row["raw_object_key"]),
                    payload=dict(row["payload"]),
                )
                for row in rows
            )
            visible = select_latest_visible_revisions(records, decision_time=query_as_of)
            if visible:
                return ProviderResponse(
                    status=ProviderStatus.OK,
                    provider="ALPACA",
                    feed_type=feed_type,
                    symbol=normalized_symbol,
                    query_as_of=query_as_of,
                    records=visible,
                )
        statement = (
            select(
                normalized_record.c.payload,
                raw_data_object.c.provider,
                raw_data_object.c.event_time,
                raw_data_object.c.available_at,
                raw_data_object.c.ingested_at,
                raw_data_object.c.content_hash,
                raw_data_object.c.raw_object_key,
            )
            .select_from(
                normalized_record.join(
                    raw_data_object,
                    normalized_record.c.raw_data_object_id == raw_data_object.c.id,
                )
            )
            .where(
                and_(
                    normalized_record.c.record_type == feed_type.value,
                    normalized_record.c.payload["symbol"].astext == str(normalized_symbol),
                    raw_data_object.c.event_time <= query_as_of,
                    raw_data_object.c.available_at <= query_as_of,
                    *(
                        (raw_data_object.c.provider != "ALPACA",)
                        if feed_type is FeedType.COMPANY_NEWS
                        else ()
                    ),
                )
            )
            .order_by(
                raw_data_object.c.available_at,
                raw_data_object.c.event_time,
                raw_data_object.c.content_hash,
                normalized_record.c.id,
            )
        )
        candidates = tuple(
            ProviderRecord(
                symbol=normalized_symbol,
                feed_type=feed_type,
                provider=row.provider,
                event_time=row.event_time,
                available_at=row.available_at,
                ingested_at=row.ingested_at,
                content_hash=row.content_hash,
                raw_object_key=row.raw_object_key,
                payload={key: value for key, value in row.payload.items() if key != "symbol"},
            )
            for row in self._connection.execute(statement)
        )
        records = select_latest_visible_revisions(candidates, decision_time=query_as_of)
        providers = {record.provider for record in records}
        return ProviderResponse(
            status=ProviderStatus.OK if records else ProviderStatus.NOT_FOUND,
            provider=next(iter(providers)) if len(providers) == 1 else "MULTIPLE",
            feed_type=feed_type,
            symbol=normalized_symbol,
            query_as_of=query_as_of,
            records=records,
            missingness=None if records else "MISSING",
        )


class EngineMarketDataRepository:
    """Open a short-lived connection for each MCP/application query."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def as_of(
        self, *, symbol: str, feed_type: FeedType, decision_time: datetime
    ) -> ProviderResponse:
        with self._engine.connect() as connection:
            return PostgresMarketDataRepository(connection).as_of(
                symbol=symbol,
                feed_type=feed_type,
                decision_time=decision_time,
            )
