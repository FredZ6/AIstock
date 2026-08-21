from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.portfolio.fill import PaperFill
from stock_platform.domain.portfolio.order import OrderSide


@dataclass(frozen=True, slots=True)
class Position:
    symbol: Symbol
    quantity: Decimal
    applied_split_ids: frozenset[UUID] = frozenset()


class SplitAdjustment(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def symbol(self) -> Symbol: ...

    @property
    def effective_at(self) -> datetime: ...

    @property
    def available_at(self) -> datetime: ...

    @property
    def ratio(self) -> Decimal: ...


def rebuild_positions(
    fills: Iterable[PaperFill],
    *,
    split_actions: Iterable[SplitAdjustment] = (),
    as_of: datetime | None = None,
) -> dict[Symbol, Position]:
    cutoff = require_aware(as_of) if as_of is not None else None
    unique_fills = {fill.id: fill for fill in fills if cutoff is None or fill.filled_at <= cutoff}
    reversed_fill_ids = {
        fill.reversal_of_id for fill in unique_fills.values() if fill.reversal_of_id is not None
    }
    events: list[tuple[datetime, int, str, Symbol, Decimal, UUID | None]] = []
    for item in unique_fills.values():
        if item.reversal_of_id is not None or item.id in reversed_fill_ids:
            continue
        direction = Decimal("1") if item.side == OrderSide.BUY else Decimal("-1")
        events.append(
            (item.filled_at, 1, str(item.id), item.symbol, direction * item.quantity, None)
        )
    unique_splits = {action.id: action for action in split_actions}
    for action in unique_splits.values():
        effective_at = require_aware(action.effective_at)
        available_at = require_aware(action.available_at)
        if cutoff is not None and (effective_at > cutoff or available_at > cutoff):
            continue
        events.append(
            (
                max(effective_at, available_at),
                0,
                str(action.id),
                action.symbol,
                action.ratio,
                action.id,
            )
        )

    quantities: dict[Symbol, Decimal] = {}
    applied_split_ids: dict[Symbol, set[UUID]] = {}
    for _, _, _, symbol, value, split_id in sorted(events):
        if split_id is None:
            quantities[symbol] = quantities.get(symbol, Decimal("0")) + value
        else:
            quantities[symbol] = quantities.get(symbol, Decimal("0")) * value
            applied_split_ids.setdefault(symbol, set()).add(split_id)
    return {
        symbol: Position(
            symbol=symbol,
            quantity=quantity,
            applied_split_ids=frozenset(applied_split_ids.get(symbol, set())),
        )
        for symbol, quantity in quantities.items()
        if quantity != 0
    }
