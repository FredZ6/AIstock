"""Strict Alpaca minute-bar normalization without a brokerage surface."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, and_, select
from sqlalchemy.dialects.postgresql import insert

from stock_platform.application.alerting.features import MinuteBar
from stock_platform.application.ingestion.normalizers.alpaca import AlpacaBar, market_session_for
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import MarketDataCoverage
from stock_platform.infrastructure.db.models.tables import (
    normalization_rejection,
    normalized_record,
    raw_data_object,
)
from stock_platform.infrastructure.ingestion.fact_store import PostgresAlpacaFactStore
from stock_platform.infrastructure.providers.base import (
    ProviderEvent,
    ProviderEventFeed,
    RawObjectStore,
)


def _decimal(payload: dict[str, object], key: str) -> Decimal:
    try:
        return Decimal(str(payload[key]))
    except (InvalidOperation, KeyError, TypeError) as error:
        raise ValueError(f"Alpaca minute bar field {key} is invalid") from error


class AlpacaStreamDecoder:
    def decode_batch(self, raw: bytes, *, received_at: datetime) -> tuple[ProviderEvent, ...]:
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Alpaca stream payload is invalid JSON") from error
        items = decoded if isinstance(decoded, list) else [decoded]
        supported: list[object] = []
        for item in items:
            message_type = item.get("T") if isinstance(item, dict) else None
            if message_type in {"success", "subscription"}:
                continue
            if message_type not in {"b", "u", "t", "q", "s"}:
                raise ValueError("Alpaca stream payload must be a supported event")
            supported.append(item)
        return tuple(
            self.decode(
                json.dumps(item, sort_keys=True, separators=(",", ":")).encode(),
                received_at=received_at,
            )
            for item in supported
        )

    def decode(self, raw: bytes, *, received_at: datetime) -> ProviderEvent:
        observed_at = require_aware(received_at).astimezone(UTC)
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Alpaca stream payload is invalid JSON") from error
        event_types = {
            "b": (ProviderEventFeed.PRICE_BARS, "bar"),
            "u": (ProviderEventFeed.PRICE_BARS, "updated_bar"),
            "t": (ProviderEventFeed.TRADES, "trade"),
            "q": (ProviderEventFeed.QUOTES, "quote"),
            "s": (ProviderEventFeed.MARKET_STATUS, "status"),
        }
        if not isinstance(decoded, dict) or decoded.get("T") not in event_types:
            raise ValueError("Alpaca stream payload must be a supported event")
        try:
            event_time = datetime.fromisoformat(str(decoded["t"]).replace("Z", "+00:00"))
            symbol = Symbol(str(decoded["S"]))
        except (KeyError, ValueError) as error:
            raise ValueError("Alpaca minute bar identity is invalid") from error
        event_time = require_aware(event_time).astimezone(UTC)
        if event_time > observed_at:
            raise ValueError("Alpaca event_time cannot be in the future")
        feed_type, event_kind = event_types[str(decoded["T"])]
        return ProviderEvent(
            provider="ALPACA",
            feed_type=feed_type,
            symbol=symbol,
            event_kind=event_kind,
            event_time=event_time,
            observed_at=observed_at,
            body=raw,
        )


class AlpacaStreamReplayWriter:
    """Persist every supported source event raw-first, even without a typed fact consumer."""

    def __init__(self, *, engine: Engine, raw_store: RawObjectStore) -> None:
        self._engine = engine
        self._raw_store = raw_store
        self._decoder = AlpacaStreamDecoder()

    def persist(
        self,
        raw: bytes,
        *,
        received_at: datetime,
        coverage: MarketDataCoverage,
    ) -> UUID:
        return self.persist_batch(raw, received_at=received_at, coverage=coverage)[0]

    def persist_batch(
        self,
        raw: bytes,
        *,
        received_at: datetime,
        coverage: MarketDataCoverage,
    ) -> tuple[UUID, ...]:
        observed_at = require_aware(received_at).astimezone(UTC)
        content_hash = hashlib.sha256(raw).hexdigest()
        feed_type = f"alpaca_stream_batch_{coverage.value.lower()}"
        object_key = alpaca_stream_object_key(raw, coverage=coverage)
        try:
            self._raw_store.put(object_key, raw, "application/json")
        except Exception as error:
            raise AlpacaStreamPersistenceUnavailable("Alpaca stream object write failed") from error
        try:
            events = self._decoder.decode_batch(raw, received_at=observed_at)
        except ValueError as error:
            with self._engine.begin() as connection:
                raw_id = connection.execute(
                    insert(raw_data_object)
                    .values(
                        provider="ALPACA",
                        feed_type=feed_type,
                        event_time=observed_at,
                        available_at=observed_at,
                        ingested_at=observed_at,
                        content_hash=content_hash,
                        raw_object_key=object_key,
                    )
                    .on_conflict_do_nothing(constraint="uq_raw_data_provider_content")
                    .returning(raw_data_object.c.id)
                ).scalar_one_or_none()
                if raw_id is None:
                    raw_id = connection.execute(
                        select(raw_data_object.c.id).where(
                            raw_data_object.c.provider == "ALPACA",
                            raw_data_object.c.feed_type == feed_type,
                            raw_data_object.c.content_hash == content_hash,
                        )
                    ).scalar_one()
                existing_rejection = connection.execute(
                    select(normalization_rejection.c.id).where(
                        normalization_rejection.c.raw_data_object_id == raw_id,
                        normalization_rejection.c.normalization_version == "alpaca-stream-v2",
                    )
                ).scalar_one_or_none()
                if existing_rejection is None:
                    connection.execute(
                        insert(normalization_rejection).values(
                            raw_data_object_id=raw_id,
                            record_key=f"stream:{coverage.value}",
                            normalization_version="alpaca-stream-v2",
                            error_class="SCHEMA_DRIFT",
                            error_detail={"type": type(error).__name__, "message": str(error)},
                        )
                    )
            raise
        if not events:
            return ()
        try:
            document = json.loads(raw, parse_float=str, parse_int=str)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Alpaca stream payload is invalid JSON") from error
        items = document if isinstance(document, list) else [document]
        payloads = [
            item
            for item in items
            if isinstance(item, dict) and item.get("T") in {"b", "u", "t", "q", "s"}
        ]
        if len(payloads) != len(events):
            raise ValueError("Alpaca stream batch does not match decoded events")
        raw_values = {
            "provider": "ALPACA",
            "feed_type": feed_type,
            "event_time": min(event.event_time for event in events),
            "available_at": observed_at,
            "ingested_at": observed_at,
            "content_hash": content_hash,
            "raw_object_key": object_key,
        }
        with self._engine.begin() as connection:
            artifact_observed_at = observed_at
            raw_id = connection.execute(
                insert(raw_data_object)
                .values(**raw_values)
                .on_conflict_do_nothing(constraint="uq_raw_data_provider_content")
                .returning(raw_data_object.c.id)
            ).scalar_one_or_none()
            if raw_id is None:
                existing = (
                    connection.execute(
                        select(raw_data_object).where(
                            and_(
                                raw_data_object.c.provider == "ALPACA",
                                raw_data_object.c.feed_type == feed_type,
                                raw_data_object.c.content_hash == content_hash,
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                immutable_keys = (
                    "provider",
                    "feed_type",
                    "event_time",
                    "content_hash",
                    "raw_object_key",
                )
                if any(existing[key] != raw_values[key] for key in immutable_keys):
                    raise ValueError("immutable Alpaca stream raw-object conflict")
                raw_id = existing["id"]
                artifact_observed_at = existing["available_at"]
            fact_store = PostgresAlpacaFactStore(connection)
            for event, payload in zip(events, payloads, strict=True):
                record_type = "market_bar" if event.event_kind == "bar" else event.event_kind
                normalized_values = {
                    "raw_data_object_id": raw_id,
                    "record_type": record_type,
                    "record_key": (
                        f"{event.symbol}:{event.event_time.isoformat()}:{event.event_kind}:"
                        f"{coverage.value}"
                    ),
                    "normalization_version": "alpaca-stream-v2",
                    "payload": {**payload, "coverage": coverage.value},
                }
                normalized_id = connection.execute(
                    insert(normalized_record)
                    .values(**normalized_values)
                    .on_conflict_do_nothing(constraint="uq_normalized_record_version")
                    .returning(normalized_record.c.id)
                ).scalar_one_or_none()
                if normalized_id is None:
                    existing_normalized = (
                        connection.execute(
                            select(normalized_record).where(
                                normalized_record.c.raw_data_object_id == raw_id,
                                normalized_record.c.record_type == record_type,
                                normalized_record.c.record_key == normalized_values["record_key"],
                                normalized_record.c.normalization_version == "alpaca-stream-v2",
                            )
                        )
                        .mappings()
                        .one()
                    )
                    if existing_normalized["payload"] != normalized_values["payload"]:
                        raise ValueError("immutable Alpaca stream normalized-record conflict")
                    normalized_id = existing_normalized["id"]
                if event.event_kind == "bar":
                    session = market_session_for(event.event_time)
                    if session is None:
                        raise ValueError("Alpaca bar falls outside the configured market calendar")
                    fact_store.persist_bar(
                        raw_id=cast(UUID, raw_id),
                        normalized_id=cast(UUID, normalized_id),
                        bar=AlpacaBar(
                            symbol=event.symbol,
                            event_time=event.event_time,
                            available_at=artifact_observed_at,
                            open=_decimal(payload, "o"),
                            high=_decimal(payload, "h"),
                            low=_decimal(payload, "l"),
                            close=_decimal(payload, "c"),
                            volume=_decimal(payload, "v"),
                            coverage=coverage,
                            session=session,
                            payload={**payload, "coverage": coverage.value, "timeframe": "1Min"},
                        ),
                    )
            return (cast(UUID, raw_id),)


def alpaca_stream_object_key(raw: bytes, *, coverage: MarketDataCoverage) -> str:
    content_hash = hashlib.sha256(raw).hexdigest()
    return f"live/ALPACA/stream/{coverage.value.lower()}/{content_hash}.json"


class AlpacaStreamPersistenceUnavailable(RuntimeError):
    pass


class AlpacaStreamNormalizer:
    def __init__(self, *, raw_store: RawObjectStore) -> None:
        self._raw_store = raw_store
        self._decoder = AlpacaStreamDecoder()

    def normalize(self, raw: bytes, *, received_at: datetime) -> MinuteBar:
        event = self._decoder.decode(raw, received_at=received_at)
        if event.feed_type is not ProviderEventFeed.PRICE_BARS:
            raise ValueError("Alpaca stream payload must be a minute bar")
        try:
            decoded = json.loads(raw, parse_float=Decimal, parse_int=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Alpaca stream payload is invalid JSON") from error
        payload = cast(dict[str, object], decoded)
        content_hash = hashlib.sha256(raw).hexdigest()
        date_path = event.event_time.strftime("%Y/%m/%d")
        object_key = f"alpaca-stream/{str(event.symbol).lower()}/{date_path}/{content_hash}.json"
        self._raw_store.put(object_key, raw, "application/json")
        previous_close = _decimal(payload, "pc") if "pc" in payload else None
        return MinuteBar(
            symbol=event.symbol,
            event_time=event.event_time,
            available_at=event.observed_at,
            ingested_at=event.observed_at,
            open=_decimal(payload, "o"),
            high=_decimal(payload, "h"),
            low=_decimal(payload, "l"),
            close=_decimal(payload, "c"),
            volume=_decimal(payload, "v"),
            previous_close=previous_close,
            provider="ALPACA",
            content_hash=content_hash,
            raw_object_key=object_key,
            raw_payload=payload,
        )
