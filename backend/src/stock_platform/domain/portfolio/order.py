from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True, slots=True)
class OrderIntent:
    id: UUID
    portfolio_id: UUID
    symbol: Symbol
    side: OrderSide
    quantity: Decimal
    decision_time: datetime
    execution_policy_version_id: UUID
    risk_approved: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "side", OrderSide(self.side))
        if not isinstance(self.quantity, Decimal):
            raise TypeError("quantity must use Decimal")
        if not self.quantity.is_finite() or self.quantity <= 0:
            raise ValueError("quantity must be finite and positive")
        decision_time = require_aware(self.decision_time).astimezone(UTC)
        object.__setattr__(self, "decision_time", decision_time)
