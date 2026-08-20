from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.fill import PaperFill
from stock_platform.domain.portfolio.order import OrderSide


@dataclass(frozen=True, slots=True)
class Position:
    symbol: Symbol
    quantity: Decimal


def rebuild_positions(fills: Iterable[PaperFill]) -> dict[Symbol, Position]:
    quantities: dict[Symbol, Decimal] = {}
    for item in {fill.id: fill for fill in fills}.values():
        direction = Decimal("1") if item.side == OrderSide.BUY else Decimal("-1")
        quantities[item.symbol] = quantities.get(item.symbol, Decimal("0")) + (
            direction * item.quantity
        )
    return {
        symbol: Position(symbol=symbol, quantity=quantity)
        for symbol, quantity in quantities.items()
        if quantity != 0
    }
