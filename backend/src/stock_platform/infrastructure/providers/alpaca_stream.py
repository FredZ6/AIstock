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


def _decimal(payload: dict[str, object], key: str) -> Decimal:
    try:
        return Decimal(str(payload[key]))
    except (InvalidOperation, KeyError, TypeError) as error:
        raise ValueError(f"Alpaca minute bar field {key} is invalid") from error


class AlpacaStreamNormalizer:
    def normalize(self, raw: bytes, *, received_at: datetime) -> MinuteBar:
        received = require_aware(received_at).astimezone(UTC)
        try:
            decoded = json.loads(raw, parse_float=Decimal, parse_int=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Alpaca stream payload is invalid JSON") from error
        if not isinstance(decoded, dict) or decoded.get("T") != "b":
            raise ValueError("Alpaca stream payload must be a minute bar")
        payload = cast(dict[str, object], decoded)
        try:
            event_time = datetime.fromisoformat(str(payload["t"]).replace("Z", "+00:00"))
            symbol = str(payload["S"])
        except (KeyError, ValueError) as error:
            raise ValueError("Alpaca minute bar identity is invalid") from error
        event_time = require_aware(event_time).astimezone(UTC)
        if event_time > received:
            raise ValueError("Alpaca event_time cannot be in the future")
        content_hash = hashlib.sha256(raw).hexdigest()
        date_path = event_time.strftime("%Y/%m/%d")
        object_key = f"alpaca-stream/{symbol.lower()}/{date_path}/{content_hash}.json"
        previous_close = _decimal(payload, "pc") if "pc" in payload else None
        return MinuteBar(
            symbol=Symbol(symbol),
            event_time=event_time,
            available_at=received,
            ingested_at=received,
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
