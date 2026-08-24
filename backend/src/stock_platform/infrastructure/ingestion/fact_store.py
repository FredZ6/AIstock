"""Append-only persistence for normalized Alpaca domain facts."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from enum import StrEnum
from typing import cast
from uuid import UUID

from sqlalchemy import Connection, and_, select
from sqlalchemy.dialects.postgresql import insert

from stock_platform.application.ingestion.normalizers.alpaca import (
    AlpacaBar,
    AlpacaNewsArticle,
)
from stock_platform.infrastructure.db.models.tables import (
    market_bar,
    news_article,
    normalized_record,
    raw_data_object,
)


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class PostgresAlpacaFactStore:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def _lineage(self, *, raw_id: UUID, normalized_id: UUID) -> Mapping[str, object]:
        row = (
            self._connection.execute(
                select(
                    raw_data_object.c.provider,
                    raw_data_object.c.feed_type,
                    raw_data_object.c.content_hash,
                    raw_data_object.c.raw_object_key,
                    raw_data_object.c.ingested_at,
                    normalized_record.c.raw_data_object_id,
                )
                .select_from(
                    normalized_record.join(
                        raw_data_object,
                        normalized_record.c.raw_data_object_id == raw_data_object.c.id,
                    )
                )
                .where(
                    normalized_record.c.id == normalized_id,
                    raw_data_object.c.id == raw_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["raw_data_object_id"] != raw_id:
            raise ValueError("normalized fact lineage does not match raw object")
        return dict(row)

    def persist_bar(
        self,
        *,
        raw_id: UUID,
        normalized_id: UUID,
        bar: AlpacaBar,
    ) -> UUID:
        lineage = self._lineage(raw_id=raw_id, normalized_id=normalized_id)
        values = {
            "event_time": bar.event_time,
            "symbol": str(bar.symbol),
            "raw_data_object_id": raw_id,
            "normalized_record_id": normalized_id,
            "provider": lineage["provider"],
            "feed_type": lineage["feed_type"],
            "coverage": bar.coverage.value,
            "session": bar.session.value,
            "content_hash": lineage["content_hash"],
            "raw_object_key": lineage["raw_object_key"],
            "available_at": bar.available_at,
            "ingested_at": lineage["ingested_at"],
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "previous_close": None,
            "conflict": False,
            "payload": _json_safe(bar.payload),
        }
        inserted = self._connection.execute(
            insert(market_bar)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[
                    market_bar.c.provider,
                    market_bar.c.feed_type,
                    market_bar.c.content_hash,
                    market_bar.c.event_time,
                ]
            )
            .returning(market_bar.c.id)
        ).scalar_one_or_none()
        if inserted is not None:
            return cast(UUID, inserted)
        existing = (
            self._connection.execute(
                select(market_bar).where(
                    and_(
                        market_bar.c.provider == lineage["provider"],
                        market_bar.c.feed_type == lineage["feed_type"],
                        market_bar.c.content_hash == lineage["content_hash"],
                        market_bar.c.event_time == bar.event_time,
                    )
                )
            )
            .mappings()
            .one()
        )
        if any(existing[key] != value for key, value in values.items()):
            raise ValueError("immutable Alpaca market bar conflict")
        return cast(UUID, existing["id"])

    def persist_news(
        self,
        *,
        raw_id: UUID,
        normalized_id: UUID,
        article: AlpacaNewsArticle,
    ) -> UUID:
        lineage = self._lineage(raw_id=raw_id, normalized_id=normalized_id)
        values = {
            "raw_data_object_id": raw_id,
            "normalized_record_id": normalized_id,
            "provider": lineage["provider"],
            "article_id": article.article_id,
            "symbols": [str(symbol) for symbol in article.symbols],
            "headline": article.headline,
            "source": article.source,
            "summary": article.summary,
            "published_at": article.published_at,
            "observed_at": article.observed_at,
            "available_at": article.available_at,
            "ingested_at": lineage["ingested_at"],
            "pit_eligible": article.pit_eligible,
            "payload": _json_safe(article.payload),
        }
        inserted = self._connection.execute(
            insert(news_article)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_news_article_version")
            .returning(news_article.c.id)
        ).scalar_one_or_none()
        if inserted is not None:
            return cast(UUID, inserted)
        existing = (
            self._connection.execute(
                select(news_article).where(
                    news_article.c.provider == lineage["provider"],
                    news_article.c.article_id == article.article_id,
                    news_article.c.normalized_record_id == normalized_id,
                )
            )
            .mappings()
            .one()
        )
        if any(existing[key] != value for key, value in values.items()):
            raise ValueError("immutable Alpaca news article conflict")
        return cast(UUID, existing["id"])
