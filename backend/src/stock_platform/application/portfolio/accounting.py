from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.portfolio.fill import PaperFill
from stock_platform.domain.portfolio.ledger import LedgerEntry, cash_balance, is_balanced
from stock_platform.domain.portfolio.order import OrderIntent, OrderSide
from stock_platform.infrastructure.db.models.tables import (
    cash_ledger,
    order_intent,
    paper_fill,
    paper_order,
)

_LEDGER_NAMESPACE = UUID("1f77598e-274a-4966-8d99-b5fd3fb4af6c")
_FILL_NAMESPACE = UUID("9d1ac474-0f57-45d9-a942-1f2b1b8743cb")
ZERO = Decimal("0")


def _entry(
    *,
    transaction_id: UUID,
    portfolio_id: UUID,
    source_id: UUID,
    account: str,
    debit: Decimal = ZERO,
    credit: Decimal = ZERO,
    currency: str,
    occurred_at: datetime,
    suffix: str,
    reversal_of_id: UUID | None = None,
) -> LedgerEntry:
    key = f"{transaction_id}|{suffix}"
    return LedgerEntry(
        id=uuid5(_LEDGER_NAMESPACE, key),
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        source_id=source_id,
        account=account,
        debit=debit,
        credit=credit,
        currency=currency,
        occurred_at=occurred_at,
        idempotency_key=key,
        reversal_of_id=reversal_of_id,
    )


def initial_funding(
    portfolio_id: UUID, amount: Decimal, currency: str, occurred_at: datetime
) -> tuple[LedgerEntry, ...]:
    if not isinstance(amount, Decimal):
        raise TypeError("funding amount must use Decimal")
    if not amount.is_finite() or amount <= 0:
        raise ValueError("funding amount must be finite and positive")
    timestamp = require_aware(occurred_at)
    transaction_id = uuid5(
        _LEDGER_NAMESPACE, f"funding|{portfolio_id}|{currency}|{timestamp.isoformat()}"
    )
    return (
        _entry(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            source_id=transaction_id,
            account="ASSET:CASH",
            debit=amount,
            currency=currency,
            occurred_at=timestamp,
            suffix="cash",
        ),
        _entry(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            source_id=transaction_id,
            account="EQUITY:OPENING_BALANCE",
            credit=amount,
            currency=currency,
            occurred_at=timestamp,
            suffix="equity",
        ),
    )


def _fill_entries(item: PaperFill) -> tuple[LedgerEntry, ...]:
    transaction_id = item.id
    gross = item.quantity * item.price
    if item.side == OrderSide.BUY:
        entries = [
            _entry(
                transaction_id=transaction_id,
                portfolio_id=item.portfolio_id,
                source_id=item.id,
                account=f"ASSET:SECURITY:{item.symbol}",
                debit=gross,
                currency=item.currency,
                occurred_at=item.filled_at,
                suffix="security",
            ),
            _entry(
                transaction_id=transaction_id,
                portfolio_id=item.portfolio_id,
                source_id=item.id,
                account="ASSET:CASH",
                credit=gross + item.fee,
                currency=item.currency,
                occurred_at=item.filled_at,
                suffix="cash",
            ),
        ]
    else:
        entries = [
            _entry(
                transaction_id=transaction_id,
                portfolio_id=item.portfolio_id,
                source_id=item.id,
                account="ASSET:CASH",
                debit=gross - item.fee,
                currency=item.currency,
                occurred_at=item.filled_at,
                suffix="cash",
            ),
            _entry(
                transaction_id=transaction_id,
                portfolio_id=item.portfolio_id,
                source_id=item.id,
                account=f"ASSET:SECURITY:{item.symbol}",
                credit=gross,
                currency=item.currency,
                occurred_at=item.filled_at,
                suffix="security",
            ),
        ]
    if item.fee > ZERO:
        entries.append(
            _entry(
                transaction_id=transaction_id,
                portfolio_id=item.portfolio_id,
                source_id=item.id,
                account="EXPENSE:EXECUTION_FEE",
                debit=item.fee,
                currency=item.currency,
                occurred_at=item.filled_at,
                suffix="fee",
            )
        )
    return tuple(entries)


def apply_fill(entries: Sequence[LedgerEntry], item: PaperFill) -> tuple[LedgerEntry, ...]:
    existing = tuple({entry.id: entry for entry in entries}.values())
    if any(entry.source_id == item.id for entry in existing):
        return existing
    appended = existing + _fill_entries(item)
    if not is_balanced(appended):
        raise ValueError("ledger transaction is not balanced")
    if cash_balance(appended, item.portfolio_id, item.currency) < ZERO:
        raise ValueError("fill would create negative cash")
    return appended


def reverse_fill(
    entries: Sequence[LedgerEntry], item: PaperFill, *, occurred_at: datetime
) -> tuple[PaperFill, tuple[LedgerEntry, ...]]:
    timestamp = require_aware(occurred_at)
    reversal_id = uuid5(_FILL_NAMESPACE, f"reverse|{item.id}|{timestamp.isoformat()}")
    reversal = PaperFill(
        id=reversal_id,
        order_id=item.order_id,
        portfolio_id=item.portfolio_id,
        symbol=item.symbol,
        side=OrderSide.SELL if item.side == OrderSide.BUY else OrderSide.BUY,
        quantity=item.quantity,
        price=item.price,
        fee=ZERO,
        currency=item.currency,
        filled_at=timestamp,
        source_bar_time=timestamp,
        execution_policy_version_id=item.execution_policy_version_id,
        reversal_of_id=item.id,
    )
    existing = tuple({entry.id: entry for entry in entries}.values())
    if any(entry.source_id == reversal.id for entry in existing):
        return reversal, existing
    original = tuple(entry for entry in existing if entry.source_id == item.id)
    if not original:
        raise ValueError("fill has no ledger entries to reverse")
    reversal_entries = tuple(
        _entry(
            transaction_id=reversal.id,
            portfolio_id=entry.portfolio_id,
            source_id=reversal.id,
            account=entry.account,
            debit=entry.credit,
            credit=entry.debit,
            currency=entry.currency,
            occurred_at=timestamp,
            suffix=str(entry.id),
            reversal_of_id=entry.id,
        )
        for entry in original
    )
    result = existing + reversal_entries
    if not is_balanced(result):
        raise ValueError("reversal is not balanced")
    return reversal, result


class PostgresPaperAccountingStore:
    """Persist immutable fills and ledger entries with idempotent inserts."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def persist(
        self,
        order: OrderIntent,
        fills: Sequence[PaperFill],
        entries: Sequence[LedgerEntry],
    ) -> None:
        if not isinstance(order, OrderIntent):
            raise TypeError("order must be an OrderIntent")
        if not is_balanced(entries):
            raise ValueError("ledger entries must be balanced before persistence")
        self.connection.execute(
            insert(order_intent)
            .values(
                id=order.id,
                portfolio_id=order.portfolio_id,
                symbol=str(order.symbol),
                side=order.side.value,
                quantity=order.quantity,
                decision_time=order.decision_time,
                execution_policy_version_id=order.execution_policy_version_id,
                risk_approved=order.risk_approved,
            )
            .on_conflict_do_nothing(index_elements=[order_intent.c.id])
        )
        filled_quantity = sum((item.quantity for item in fills), ZERO)
        status = (
            "REJECTED"
            if not order.risk_approved
            else "FILLED"
            if filled_quantity == order.quantity
            else "PARTIALLY_FILLED"
            if filled_quantity > ZERO
            else "PENDING"
        )
        self.connection.execute(
            insert(paper_order)
            .values(
                id=order.id,
                order_intent_id=order.id,
                portfolio_id=order.portfolio_id,
                symbol=str(order.symbol),
                side=order.side.value,
                quantity=order.quantity,
                decision_time=order.decision_time,
                execution_policy_version_id=order.execution_policy_version_id,
                risk_approved=order.risk_approved,
                status=status,
            )
            .on_conflict_do_nothing(index_elements=[paper_order.c.id])
        )
        for item in fills:
            self.connection.execute(
                insert(paper_fill)
                .values(
                    id=item.id,
                    order_id=item.order_id,
                    portfolio_id=item.portfolio_id,
                    symbol=str(item.symbol),
                    side=item.side.value,
                    quantity=item.quantity,
                    price=item.price,
                    fee=item.fee,
                    currency=item.currency,
                    filled_at=item.filled_at,
                    source_bar_time=item.source_bar_time,
                    execution_policy_version_id=item.execution_policy_version_id,
                    idempotency_key=f"fill:{item.id}",
                    reversal_of_id=item.reversal_of_id,
                )
                .on_conflict_do_nothing(index_elements=[paper_fill.c.idempotency_key])
            )
        for entry in entries:
            self.connection.execute(
                insert(cash_ledger)
                .values(
                    id=entry.id,
                    portfolio_id=entry.portfolio_id,
                    amount=entry.debit - entry.credit,
                    currency=entry.currency,
                    entry_type=entry.account,
                    occurred_at=entry.occurred_at,
                    transaction_id=entry.transaction_id,
                    source_id=entry.source_id,
                    account=entry.account,
                    debit=entry.debit,
                    credit=entry.credit,
                    idempotency_key=entry.idempotency_key,
                    reversal_of_id=entry.reversal_of_id,
                )
                .on_conflict_do_nothing(index_elements=[cash_ledger.c.idempotency_key])
            )

    def load_fills(self, portfolio_id: UUID, *, as_of: datetime) -> tuple[PaperFill, ...]:
        cutoff = require_aware(as_of)
        rows = self.connection.execute(
            select(paper_fill)
            .where(
                paper_fill.c.portfolio_id == portfolio_id,
                paper_fill.c.filled_at <= cutoff,
            )
            .order_by(paper_fill.c.filled_at, paper_fill.c.id)
        ).mappings()
        return tuple(
            PaperFill(
                id=row["id"],
                order_id=row["order_id"],
                portfolio_id=row["portfolio_id"],
                symbol=row["symbol"],
                side=OrderSide(row["side"]),
                quantity=row["quantity"],
                price=row["price"],
                fee=row["fee"],
                currency=row["currency"],
                filled_at=row["filled_at"],
                source_bar_time=row["source_bar_time"],
                execution_policy_version_id=row["execution_policy_version_id"],
                reversal_of_id=row["reversal_of_id"],
            )
            for row in rows
        )

    def load_ledger(self, portfolio_id: UUID, *, as_of: datetime) -> tuple[LedgerEntry, ...]:
        cutoff = require_aware(as_of)
        rows = self.connection.execute(
            select(cash_ledger)
            .where(
                cash_ledger.c.portfolio_id == portfolio_id,
                cash_ledger.c.occurred_at <= cutoff,
            )
            .order_by(cash_ledger.c.occurred_at, cash_ledger.c.id)
        ).mappings()
        return tuple(
            LedgerEntry(
                id=row["id"],
                transaction_id=row["transaction_id"],
                portfolio_id=row["portfolio_id"],
                source_id=row["source_id"],
                account=row["account"],
                debit=row["debit"],
                credit=row["credit"],
                currency=row["currency"],
                occurred_at=row["occurred_at"],
                idempotency_key=row["idempotency_key"],
                reversal_of_id=row["reversal_of_id"],
            )
            for row in rows
        )
