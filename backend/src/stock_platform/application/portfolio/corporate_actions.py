from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.engine import Connection

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.portfolio.ledger import LedgerEntry, is_balanced
from stock_platform.domain.portfolio.position import Position
from stock_platform.infrastructure.db.models.tables import corporate_action

_ENTRY_NAMESPACE = UUID("66a1af77-3fe6-42bb-b62e-46f28135af31")
ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SplitAction:
    id: UUID
    symbol: Symbol
    effective_at: datetime
    available_at: datetime
    ratio: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "effective_at", require_aware(self.effective_at).astimezone(UTC))
        object.__setattr__(self, "available_at", require_aware(self.available_at).astimezone(UTC))
        if not isinstance(self.ratio, Decimal):
            raise TypeError("split ratio must use Decimal")
        if not self.ratio.is_finite() or self.ratio <= 0:
            raise ValueError("split ratio must be finite and positive")


@dataclass(frozen=True, slots=True)
class CashDividend:
    id: UUID
    symbol: Symbol
    effective_at: datetime
    available_at: datetime
    cash_per_share: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "effective_at", require_aware(self.effective_at).astimezone(UTC))
        object.__setattr__(self, "available_at", require_aware(self.available_at).astimezone(UTC))
        if not isinstance(self.cash_per_share, Decimal):
            raise TypeError("cash_per_share must use Decimal")
        if not self.cash_per_share.is_finite() or self.cash_per_share < 0:
            raise ValueError("cash_per_share must be finite and non-negative")
        object.__setattr__(self, "currency", self.currency.upper())


CorporateAction = SplitAction | CashDividend


class PostgresCorporateActionStore:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def visible(self, symbol: Symbol, *, as_of: datetime) -> tuple[CorporateAction, ...]:
        cutoff = require_aware(as_of).astimezone(UTC)
        rows = self.connection.execute(
            select(corporate_action)
            .where(
                corporate_action.c.symbol == str(symbol),
                corporate_action.c.effective_at <= cutoff,
                corporate_action.c.available_at <= cutoff,
            )
            .order_by(corporate_action.c.effective_at, corporate_action.c.available_at)
        ).mappings()
        actions: list[CorporateAction] = []
        for row in rows:
            if row["action_type"] == "SPLIT":
                actions.append(
                    SplitAction(
                        id=row["id"],
                        symbol=Symbol(row["symbol"]),
                        effective_at=row["effective_at"],
                        available_at=row["available_at"],
                        ratio=row["split_ratio"],
                    )
                )
            else:
                actions.append(
                    CashDividend(
                        id=row["id"],
                        symbol=Symbol(row["symbol"]),
                        effective_at=row["effective_at"],
                        available_at=row["available_at"],
                        cash_per_share=row["cash_per_share"],
                        currency=row["currency"],
                    )
                )
        return tuple(actions)


class CorporateActionProcessor:
    def adjust_position(self, position: Position, actions: Sequence[CorporateAction]) -> Position:
        quantity = position.quantity
        unique = {action.id: action for action in actions}
        for action in sorted(
            unique.values(), key=lambda item: (item.effective_at, item.available_at, item.id)
        ):
            if isinstance(action, SplitAction) and action.symbol == position.symbol:
                quantity *= action.ratio
        return Position(symbol=position.symbol, quantity=quantity)

    def apply_dividends(
        self,
        entries: Sequence[LedgerEntry],
        portfolio_id: UUID,
        position: Position,
        actions: Sequence[CorporateAction],
    ) -> tuple[LedgerEntry, ...]:
        result = tuple({entry.id: entry for entry in entries}.values())
        for action in {item.id: item for item in actions}.values():
            if not isinstance(action, CashDividend) or action.symbol != position.symbol:
                continue
            if any(entry.source_id == action.id for entry in result):
                continue
            amount = position.quantity * action.cash_per_share
            if amount == ZERO:
                continue
            occurred_at = max(action.effective_at, action.available_at)
            cash_key = f"dividend|{portfolio_id}|{action.id}|cash"
            income_key = f"dividend|{portfolio_id}|{action.id}|income"
            result += (
                LedgerEntry(
                    id=uuid5(_ENTRY_NAMESPACE, cash_key),
                    transaction_id=action.id,
                    portfolio_id=portfolio_id,
                    source_id=action.id,
                    account="ASSET:CASH",
                    debit=amount,
                    credit=ZERO,
                    currency=action.currency,
                    occurred_at=occurred_at,
                    idempotency_key=cash_key,
                ),
                LedgerEntry(
                    id=uuid5(_ENTRY_NAMESPACE, income_key),
                    transaction_id=action.id,
                    portfolio_id=portfolio_id,
                    source_id=action.id,
                    account=f"INCOME:DIVIDEND:{position.symbol}",
                    debit=ZERO,
                    credit=amount,
                    currency=action.currency,
                    occurred_at=occurred_at,
                    idempotency_key=income_key,
                ),
            )
        if not is_balanced(result):
            raise ValueError("corporate action ledger is not balanced")
        return result
