"""Point-in-time repositories that never expose data from the future."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, and_, select

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.db.models.tables import normalized_record, raw_data_object
from stock_platform.infrastructure.providers.base import (
    FeedType,
    ProviderRecord,
    ProviderResponse,
    ProviderStatus,
)


class PostgresMarketDataRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def as_of(
        self, *, symbol: str, feed_type: FeedType, decision_time: datetime
    ) -> ProviderResponse:
        query_as_of = require_aware(decision_time)
        normalized_symbol = Symbol(symbol)
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
                    raw_data_object.c.available_at <= query_as_of,
                )
            )
            .order_by(
                raw_data_object.c.available_at,
                raw_data_object.c.event_time,
                raw_data_object.c.content_hash,
            )
        )
        records = tuple(
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
        return ProviderResponse(
            status=ProviderStatus.OK if records else ProviderStatus.NOT_FOUND,
            provider=records[0].provider if records else "NONE",
            feed_type=feed_type,
            symbol=normalized_symbol,
            query_as_of=query_as_of,
            records=records,
            missingness=None if records else "MISSING",
        )
