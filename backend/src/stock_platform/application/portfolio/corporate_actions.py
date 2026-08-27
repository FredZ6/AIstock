from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
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


def _revision_chain(direct: UUID | None, chain: frozenset[UUID]) -> frozenset[UUID]:
    return chain | ({direct} if direct is not None else set())


@dataclass(frozen=True, slots=True)
class SplitAction:
    id: UUID
    symbol: Symbol
    effective_at: datetime
    available_at: datetime
    ratio: Decimal
    supersedes_id: UUID | None = None
    supersedes_chain: frozenset[UUID] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "effective_at", require_aware(self.effective_at).astimezone(UTC))
        object.__setattr__(self, "available_at", require_aware(self.available_at).astimezone(UTC))
        if not isinstance(self.ratio, Decimal):
            raise TypeError("split ratio must use Decimal")
        if not self.ratio.is_finite() or self.ratio <= 0:
            raise ValueError("split ratio must be finite and positive")
        object.__setattr__(
            self, "supersedes_chain", _revision_chain(self.supersedes_id, self.supersedes_chain)
        )


@dataclass(frozen=True, slots=True)
class CashDividend:
    id: UUID
    symbol: Symbol
    effective_at: datetime
    available_at: datetime
    cash_per_share: Decimal
    currency: str
    supersedes_id: UUID | None = None
    supersedes_chain: frozenset[UUID] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "effective_at", require_aware(self.effective_at).astimezone(UTC))
        object.__setattr__(self, "available_at", require_aware(self.available_at).astimezone(UTC))
        if not isinstance(self.cash_per_share, Decimal):
            raise TypeError("cash_per_share must use Decimal")
        if not self.cash_per_share.is_finite() or self.cash_per_share < 0:
            raise ValueError("cash_per_share must be finite and non-negative")
        object.__setattr__(self, "currency", self.currency.upper())
        object.__setattr__(
            self, "supersedes_chain", _revision_chain(self.supersedes_id, self.supersedes_chain)
        )


@dataclass(frozen=True, slots=True)
class StockDividend:
    id: UUID
    symbol: Symbol
    effective_at: datetime
    available_at: datetime
    ratio: Decimal
    supersedes_id: UUID | None = None
    supersedes_chain: frozenset[UUID] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "effective_at", require_aware(self.effective_at).astimezone(UTC))
        object.__setattr__(self, "available_at", require_aware(self.available_at).astimezone(UTC))
        if not isinstance(self.ratio, Decimal):
            raise TypeError("stock dividend ratio must use Decimal")
        if not self.ratio.is_finite() or self.ratio <= 0:
            raise ValueError("stock dividend ratio must be finite and positive")
        object.__setattr__(
            self, "supersedes_chain", _revision_chain(self.supersedes_id, self.supersedes_chain)
        )


@dataclass(frozen=True, slots=True)
class AdrRatioChange:
    id: UUID
    symbol: Symbol
    effective_at: datetime
    available_at: datetime
    old_ratio: Decimal
    new_ratio: Decimal
    supersedes_id: UUID | None = None
    supersedes_chain: frozenset[UUID] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "effective_at", require_aware(self.effective_at).astimezone(UTC))
        object.__setattr__(self, "available_at", require_aware(self.available_at).astimezone(UTC))
        for name, ratio in (("old_ratio", self.old_ratio), ("new_ratio", self.new_ratio)):
            if not isinstance(ratio, Decimal):
                raise TypeError(f"{name} must use Decimal")
            if not ratio.is_finite() or ratio <= 0:
                raise ValueError(f"{name} must be finite and positive")
        object.__setattr__(
            self, "supersedes_chain", _revision_chain(self.supersedes_id, self.supersedes_chain)
        )


ReferenceActionType = Literal["SPIN_OFF", "SYMBOL_CHANGE", "MERGER_ACQUISITION"]


@dataclass(frozen=True, slots=True)
class ReferenceAction:
    id: UUID
    symbol: Symbol
    effective_at: datetime
    available_at: datetime
    action_type: ReferenceActionType
    details: dict[str, Any]
    supersedes_id: UUID | None = None
    supersedes_chain: frozenset[UUID] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "effective_at", require_aware(self.effective_at).astimezone(UTC))
        object.__setattr__(self, "available_at", require_aware(self.available_at).astimezone(UTC))
        if self.action_type not in {"SPIN_OFF", "SYMBOL_CHANGE", "MERGER_ACQUISITION"}:
            raise ValueError("unsupported reference action type")
        object.__setattr__(
            self, "supersedes_chain", _revision_chain(self.supersedes_id, self.supersedes_chain)
        )


CorporateAction = SplitAction | CashDividend | StockDividend | AdrRatioChange | ReferenceAction


@dataclass(frozen=True, slots=True)
class CorporateActionGap:
    action_id: UUID
    reason: str


@dataclass(frozen=True, slots=True)
class PositionAdjustment:
    position: Position
    gaps: tuple[CorporateActionGap, ...]


class PostgresCorporateActionStore:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def visible(self, symbol: Symbol, *, as_of: datetime) -> tuple[CorporateAction, ...]:
        cutoff = require_aware(as_of).astimezone(UTC)
        rows = tuple(
            self.connection.execute(
                select(corporate_action)
                .where(
                    corporate_action.c.symbol == str(symbol),
                    corporate_action.c.available_at <= cutoff,
                )
                .order_by(corporate_action.c.available_at, corporate_action.c.created_at)
            ).mappings()
        )
        rows_by_id = {row["id"]: row for row in rows}

        def supersedes_chain(row: Any) -> frozenset[UUID]:
            result: set[UUID] = set()
            current = row.get("supersedes_id")
            while current is not None and current not in result:
                result.add(current)
                parent = rows_by_id.get(current)
                current = parent.get("supersedes_id") if parent is not None else None
            return frozenset(result)

        latest: dict[tuple[str, str], Any] = {}
        for row in rows:
            if row["effective_at"] > cutoff:
                continue
            latest[(row["provider"], row.get("provider_action_id") or str(row["id"]))] = row
        actions: list[CorporateAction] = []
        for row in latest.values():
            if row["action_type"] == "SPLIT":
                actions.append(
                    SplitAction(
                        id=row["id"],
                        symbol=Symbol(row["symbol"]),
                        effective_at=row["effective_at"],
                        available_at=row["available_at"],
                        ratio=row["split_ratio"],
                        supersedes_id=row["supersedes_id"],
                        supersedes_chain=supersedes_chain(row),
                    )
                )
            elif row["action_type"] == "CASH_DIVIDEND":
                actions.append(
                    CashDividend(
                        id=row["id"],
                        symbol=Symbol(row["symbol"]),
                        effective_at=row["effective_at"],
                        available_at=row["available_at"],
                        cash_per_share=row["cash_per_share"],
                        currency=row["currency"],
                        supersedes_id=row["supersedes_id"],
                        supersedes_chain=supersedes_chain(row),
                    )
                )
            elif row["action_type"] == "STOCK_DIVIDEND":
                actions.append(
                    StockDividend(
                        row["id"],
                        Symbol(row["symbol"]),
                        row["effective_at"],
                        row["available_at"],
                        row["stock_ratio"],
                        row["supersedes_id"],
                        supersedes_chain(row),
                    )
                )
            elif row["action_type"] == "ADR_RATIO_CHANGE":
                actions.append(
                    AdrRatioChange(
                        row["id"],
                        Symbol(row["symbol"]),
                        row["effective_at"],
                        row["available_at"],
                        row["old_adr_ratio"],
                        row["new_adr_ratio"],
                        row["supersedes_id"],
                        supersedes_chain(row),
                    )
                )
            else:
                actions.append(
                    ReferenceAction(
                        row["id"],
                        Symbol(row["symbol"]),
                        row["effective_at"],
                        row["available_at"],
                        row["action_type"],
                        dict(row["details"]),
                        row["supersedes_id"],
                        supersedes_chain(row),
                    )
                )
        return tuple(actions)


class CorporateActionProcessor:
    def adjust_position_with_gaps(
        self, position: Position, actions: Sequence[CorporateAction]
    ) -> PositionAdjustment:
        quantity = position.quantity
        applied_ids = set(position.applied_split_ids)
        gaps: list[CorporateActionGap] = []
        for action in sorted(
            {item.id: item for item in actions}.values(),
            key=lambda item: (item.effective_at, item.available_at, item.id),
        ):
            if action.symbol != position.symbol or action.id in applied_ids:
                continue
            if action.supersedes_chain & applied_ids:
                gaps.append(
                    CorporateActionGap(action.id, "REVISED_CORPORATE_ACTION_REQUIRES_REPLAY")
                )
                continue
            if isinstance(action, SplitAction):
                quantity *= action.ratio
                applied_ids.add(action.id)
            elif isinstance(action, StockDividend):
                quantity *= Decimal("1") + action.ratio
                applied_ids.add(action.id)
            elif isinstance(action, AdrRatioChange):
                quantity *= action.new_ratio / action.old_ratio
                applied_ids.add(action.id)
            elif isinstance(action, ReferenceAction):
                gaps.append(CorporateActionGap(action.id, "UNSUPPORTED_CORPORATE_ACTION"))
        return PositionAdjustment(
            Position(position.symbol, quantity, frozenset(applied_ids)), tuple(gaps)
        )

    def adjust_position(self, position: Position, actions: Sequence[CorporateAction]) -> Position:
        return self.adjust_position_with_gaps(position, actions).position

    def apply_dividends(
        self,
        entries: Sequence[LedgerEntry],
        portfolio_id: UUID,
        position: Position,
        actions: Sequence[CorporateAction],
        *,
        cash_currency: str | None = None,
    ) -> tuple[LedgerEntry, ...]:
        result = tuple({entry.id: entry for entry in entries}.values())
        for action in {item.id: item for item in actions}.values():
            if not isinstance(action, CashDividend) or action.symbol != position.symbol:
                continue
            if any(entry.source_id == action.id for entry in result):
                continue
            if action.supersedes_chain & {entry.source_id for entry in result}:
                raise ValueError("revised cash dividend requires explicit ledger reversal")
            if cash_currency is not None and action.currency != cash_currency.upper():
                raise ValueError("implicit FX conversion is forbidden for cash dividends")
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
