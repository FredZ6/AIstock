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
from stock_platform.application.ingestion.normalizers.sec import SecFiling
from stock_platform.infrastructure.db.models.tables import (
    market_bar,
    news_article,
    normalized_record,
    raw_data_object,
    sec_filing,
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
                    market_bar.c.symbol,
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
                        market_bar.c.symbol == str(bar.symbol),
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


class PostgresSecFactStore:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def _lineage(
        self,
        *,
        raw_id: UUID,
        normalized_id: UUID,
        document_raw_id: UUID,
    ) -> Mapping[str, object]:
        row = (
            self._connection.execute(
                select(
                    raw_data_object.c.provider,
                    normalized_record.c.raw_data_object_id,
                )
                .select_from(
                    normalized_record.join(
                        raw_data_object,
                        normalized_record.c.raw_data_object_id == raw_data_object.c.id,
                    )
                )
                .where(normalized_record.c.id == normalized_id, raw_data_object.c.id == raw_id)
            )
            .mappings()
            .one_or_none()
        )
        document_provider = self._connection.execute(
            select(raw_data_object.c.provider).where(raw_data_object.c.id == document_raw_id)
        ).scalar_one_or_none()
        if (
            row is None
            or row["raw_data_object_id"] != raw_id
            or row["provider"] != "SEC"
            or document_provider != "SEC"
        ):
            raise ValueError("SEC filing lineage does not match raw objects")
        return dict(row)

    def persist_filing(
        self,
        *,
        security_id: UUID,
        raw_id: UUID,
        normalized_id: UUID,
        document_raw_id: UUID,
        filing: SecFiling,
    ) -> UUID:
        lineage = self._lineage(
            raw_id=raw_id,
            normalized_id=normalized_id,
            document_raw_id=document_raw_id,
        )
        supersedes_id = None
        if filing.is_amendment:
            supersedes_id = self._connection.execute(
                select(sec_filing.c.id)
                .where(
                    sec_filing.c.security_id == security_id,
                    sec_filing.c.base_form == filing.base_form,
                    sec_filing.c.report_date == filing.report_date,
                    sec_filing.c.accepted_at < filing.accepted_at,
                )
                .order_by(sec_filing.c.accepted_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        values = {
            "security_id": security_id,
            "raw_data_object_id": raw_id,
            "normalized_record_id": normalized_id,
            "document_raw_data_object_id": document_raw_id,
            "provider": lineage["provider"],
            "cik": filing.cik,
            "accession_number": filing.accession_number,
            "form": filing.form,
            "base_form": filing.base_form,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "accepted_at": filing.accepted_at,
            "available_at": filing.available_at,
            "primary_document": filing.primary_document,
            "description": filing.description,
            "is_amendment": filing.is_amendment,
            "supersedes_id": supersedes_id,
            "payload": _json_safe(filing.payload),
        }
        inserted = self._connection.execute(
            insert(sec_filing)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_sec_filing_accession")
            .returning(sec_filing.c.id)
        ).scalar_one_or_none()
        if inserted is not None:
            return cast(UUID, inserted)
        existing = (
            self._connection.execute(
                select(sec_filing).where(
                    sec_filing.c.provider == lineage["provider"],
                    sec_filing.c.accession_number == filing.accession_number,
                )
            )
            .mappings()
            .one()
        )
        if any(existing[key] != value for key, value in values.items()):
            raise ValueError("immutable SEC filing conflict")
        return cast(UUID, existing["id"])
