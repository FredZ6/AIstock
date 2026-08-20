from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.portfolio.order import OrderSide


def _decimal(name: str, value: Decimal, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must use Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class ExecutionBar:
    symbol: Symbol
    event_time: datetime
    available_at: datetime
    open: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        event_time = require_aware(self.event_time).astimezone(UTC)
        available_at = require_aware(self.available_at).astimezone(UTC)
        if available_at < event_time:
            raise ValueError("bar cannot be available before event time")
        object.__setattr__(self, "event_time", event_time)
        object.__setattr__(self, "available_at", available_at)
        _decimal("open", self.open, positive=True)
        _decimal("volume", self.volume)
        if self.volume < 0:
            raise ValueError("volume cannot be negative")


@dataclass(frozen=True, slots=True)
class PaperFill:
    id: UUID
    order_id: UUID
    portfolio_id: UUID
    symbol: Symbol
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fee: Decimal
    currency: str
    filled_at: datetime
    source_bar_time: datetime
    execution_policy_version_id: UUID
    reversal_of_id: UUID | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "side", OrderSide(self.side))
        _decimal("quantity", self.quantity, positive=True)
        _decimal("price", self.price, positive=True)
        _decimal("fee", self.fee)
        if self.fee < 0:
            raise ValueError("fee cannot be negative")
        currency = self.currency.upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        object.__setattr__(self, "currency", currency)
        filled_at = require_aware(self.filled_at).astimezone(UTC)
        source_bar_time = require_aware(self.source_bar_time).astimezone(UTC)
        if filled_at < source_bar_time:
            raise ValueError("fill cannot precede its source bar")
        object.__setattr__(self, "filled_at", filled_at)
        object.__setattr__(self, "source_bar_time", source_bar_time)
