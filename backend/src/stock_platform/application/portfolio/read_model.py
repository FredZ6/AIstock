from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class PositionFill:
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    price: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioPosition:
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    market_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    price_available_at: datetime | None


def build_positions(
    fills: tuple[PositionFill, ...],
    *,
    prices: dict[str, tuple[Decimal, datetime]],
) -> tuple[PortfolioPosition, ...]:
    state: dict[str, tuple[Decimal, Decimal]] = {}
    for fill in fills:
        quantity, cost = state.get(fill.symbol, (Decimal("0"), Decimal("0")))
        if fill.side == "BUY":
            quantity += fill.quantity
            cost += fill.quantity * fill.price
        else:
            if fill.quantity > quantity:
                raise ValueError("a paper position cannot be reduced below zero")
            average_cost = cost / quantity
            quantity -= fill.quantity
            cost -= average_cost * fill.quantity
        state[fill.symbol] = (quantity, cost)

    result: list[PortfolioPosition] = []
    for symbol, (quantity, cost) in sorted(state.items()):
        if quantity == 0:
            continue
        average_cost = cost / quantity
        quote = prices.get(symbol)
        market_price, available_at = quote if quote else (None, None)
        market_value = market_price * quantity if market_price is not None else None
        unrealized_pnl = (
            (market_price - average_cost) * quantity if market_price is not None else None
        )
        result.append(
            PortfolioPosition(
                symbol=symbol,
                quantity=quantity,
                average_cost=average_cost,
                market_price=market_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                price_available_at=available_at,
            )
        )
    return tuple(result)
