"""Redis Streams adapter for normalized minute bars."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import cast

from redis import Redis
from redis.exceptions import ResponseError

from stock_platform.application.alerting.features import MinuteBar
from stock_platform.domain.common.ids import Symbol


@dataclass(frozen=True, slots=True)
class StreamMessage:
    id: str
    bar: MinuteBar


def _encode_bar(item: MinuteBar) -> str:
    payload = {
        "symbol": str(item.symbol),
        "event_time": item.event_time.isoformat(),
        "available_at": item.available_at.isoformat(),
        "ingested_at": item.ingested_at.isoformat(),
        "open": str(item.open),
        "high": str(item.high),
        "low": str(item.low),
        "close": str(item.close),
        "volume": str(item.volume),
        "previous_close": str(item.previous_close) if item.previous_close is not None else None,
        "provider": item.provider,
        "content_hash": item.content_hash,
        "raw_object_key": item.raw_object_key,
        "raw_payload": _json_safe(item.raw_payload),
        "conflict": item.conflict,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _decode_bar(value: str) -> MinuteBar:
    payload = cast(dict[str, object], json.loads(value))
    previous_close = payload.get("previous_close")
    return MinuteBar(
        symbol=Symbol(cast(str, payload["symbol"])),
        event_time=datetime.fromisoformat(cast(str, payload["event_time"])),
        available_at=datetime.fromisoformat(cast(str, payload["available_at"])),
        ingested_at=datetime.fromisoformat(cast(str, payload["ingested_at"])),
        open=Decimal(cast(str, payload["open"])),
        high=Decimal(cast(str, payload["high"])),
        low=Decimal(cast(str, payload["low"])),
        close=Decimal(cast(str, payload["close"])),
        volume=Decimal(cast(str, payload["volume"])),
        previous_close=Decimal(cast(str, previous_close)) if previous_close is not None else None,
        provider=cast(str, payload["provider"]),
        content_hash=cast(str, payload["content_hash"]),
        raw_object_key=cast(str, payload["raw_object_key"]),
        raw_payload=cast(dict[str, object], payload["raw_payload"]),
        conflict=cast(bool, payload["conflict"]),
    )


class RedisMarketStream:
    def __init__(self, *, url: str, stream_name: str = "market-bars") -> None:
        self._client: Redis = Redis.from_url(url, decode_responses=True)
        self.stream_name = stream_name

    def create_consumer_group(self, group: str) -> None:
        try:
            self._client.xgroup_create(self.stream_name, group, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    def publish(self, item: MinuteBar) -> str:
        return cast(str, self._client.xadd(self.stream_name, {"bar": _encode_bar(item)}))

    def read(
        self,
        *,
        group: str,
        consumer: str,
        count: int = 10,
        block_ms: int = 1000,
    ) -> tuple[StreamMessage, ...]:
        response = cast(
            list[tuple[str, list[tuple[str, dict[str, str]]]]],
            self._client.xreadgroup(
                group,
                consumer,
                {self.stream_name: ">"},
                count=count,
                block=block_ms,
            ),
        )
        messages: list[StreamMessage] = []
        for _stream, entries in response:
            for message_id, fields in entries:
                messages.append(StreamMessage(message_id, _decode_bar(fields["bar"])))
        return tuple(messages)

    def acknowledge(self, *, group: str, message_id: str) -> None:
        self._client.xack(self.stream_name, group, message_id)

    def pending_count(self, *, group: str) -> int:
        summary = cast(dict[str, int], self._client.xpending(self.stream_name, group))
        return summary["pending"]

    def delete(self) -> None:
        self._client.delete(self.stream_name)

    def close(self) -> None:
        self._client.close()
