"""Stable alert identities and cooldown buckets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware

_ALERT_NAMESPACE = UUID("40e69fd7-7373-4245-a55d-9293f52c2a17")


@dataclass(frozen=True, slots=True)
class AlertIdentity:
    id: UUID
    key: str
    bucket_start: datetime

    @classmethod
    def for_trigger(
        cls,
        *,
        symbol: str,
        rule_id: str,
        event_time: datetime,
        cooldown: timedelta,
    ) -> AlertIdentity:
        aware = require_aware(event_time).astimezone(UTC)
        seconds = int(cooldown.total_seconds())
        if seconds <= 0:
            raise ValueError("cooldown must be positive")
        bucket_epoch = int(aware.timestamp()) // seconds * seconds
        bucket_start = datetime.fromtimestamp(bucket_epoch, tz=UTC)
        bucket_text = bucket_start.isoformat().replace("+00:00", "Z")
        key = f"{Symbol(symbol)}:{rule_id}:{bucket_text}"
        return cls(id=uuid5(_ALERT_NAMESPACE, key), key=key, bucket_start=bucket_start)
