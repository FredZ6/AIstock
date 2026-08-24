"""Strict Alpaca minute-bar normalization without a brokerage surface."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import cast

from stock_platform.application.alerting.features import MinuteBar
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
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
