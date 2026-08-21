from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.portfolio.fill import ExecutionBar


def visible_bar_prices(
    bars: Sequence[ExecutionBar],
    *,
    event_cutoff: datetime,
    available_cutoff: datetime,
) -> dict[Symbol, Decimal]:
    event_time = require_aware(event_cutoff)
    available_at = require_aware(available_cutoff)
    revisions: dict[tuple[Symbol, datetime], ExecutionBar] = {}
    for bar in bars:
        if bar.event_time > event_time or bar.available_at > available_at:
            continue
        key = (bar.symbol, bar.event_time)
        current = revisions.get(key)
        if (
            current is not None
            and (bar.available_at, bar.content_hash) == (current.available_at, current.content_hash)
            and (bar.open, bar.volume) != (current.open, current.volume)
        ):
            raise ValueError("conflicting bars share a revision identity")
        if current is None or (bar.available_at, bar.content_hash) > (
            current.available_at,
            current.content_hash,
        ):
            revisions[key] = bar
    latest: dict[Symbol, ExecutionBar] = {}
    for bar in revisions.values():
        current = latest.get(bar.symbol)
        if current is None or (bar.event_time, bar.available_at, bar.content_hash) > (
            current.event_time,
            current.available_at,
            current.content_hash,
        ):
            latest[bar.symbol] = bar
    return {symbol: bar.open for symbol, bar in latest.items()}
