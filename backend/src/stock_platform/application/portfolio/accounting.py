from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from stock_platform.application.portfolio.allocation import MarketContextSnapshot
from stock_platform.application.portfolio.risk import RiskDecision
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.portfolio.fill import PaperFill
from stock_platform.domain.portfolio.ledger import LedgerEntry, cash_balance, is_balanced
from stock_platform.domain.portfolio.order import OrderIntent, OrderSide
from stock_platform.infrastructure.db.models.tables import (
    cash_ledger,
    market_context_snapshot,
    order_intent,
    paper_fill,
    paper_order,
)
from stock_platform.infrastructure.db.models.tables import risk_decision as risk_decision_table

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
    original_entry_ids = {entry.id for entry in original}
    if any(entry.reversal_of_id in original_entry_ids for entry in existing):
        raise ValueError("fill is already reversed")
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
        *,
        risk_decision: RiskDecision | None = None,
        market_context: MarketContextSnapshot | None = None,
    ) -> None:
        if not isinstance(order, OrderIntent):
            raise TypeError("order must be an OrderIntent")
        if not is_balanced(entries):
            raise ValueError("ledger entries must be balanced before persistence")
        if risk_decision is None or order.risk_decision_id != risk_decision.id:
            raise ValueError("order must point to its deterministic risk decision")
        if market_context is None or risk_decision.market_context_snapshot_id != market_context.id:
            raise ValueError("risk decision must point to its frozen market context")
        if order.symbol != risk_decision.symbol:
            raise ValueError("order and risk decision identity do not match")
        if order.portfolio_id != risk_decision.portfolio_id:
            raise ValueError("order and risk decision portfolio do not match")
        if order.risk_approved != risk_decision.approved:
            raise ValueError("order approval must match deterministic risk decision")
        if order.quantity != risk_decision.max_order_quantity or (
            (order.side is OrderSide.BUY) != (risk_decision.approved_delta > ZERO)
        ):
            raise ValueError("order exceeds deterministic risk authorization")
        context_values = {
            "id": market_context.id,
            "as_of": market_context.as_of,
            "available_at": market_context.available_at,
            "qqq_trend": market_context.qqq_trend,
            "qqq_volatility": market_context.qqq_volatility,
            "soxx_relative_strength": market_context.soxx_relative_strength,
            "vix": market_context.vix,
            "regime_label": market_context.regime.value,
            "algorithm_version": market_context.algorithm_version,
            "source_lineage": [str(item) for item in market_context.source_lineage],
        }
        self.connection.execute(
            insert(market_context_snapshot)
            .values(**context_values)
            .on_conflict_do_nothing(index_elements=[market_context_snapshot.c.id])
        )
        persisted_context = (
            self.connection.execute(
                select(market_context_snapshot).where(
                    market_context_snapshot.c.id == market_context.id
                )
            )
            .mappings()
            .one()
        )
        if any(persisted_context[key] != value for key, value in context_values.items()):
            raise ValueError("market context identity was reused with different facts")
        risk_values = {
            "id": risk_decision.id,
            "proposal_id": risk_decision.proposal_id,
            "research_decision_id": risk_decision.research_decision_id,
            "portfolio_id": risk_decision.portfolio_id,
            "symbol": str(risk_decision.symbol),
            "status": risk_decision.status.value,
            "requested_weight": risk_decision.requested_weight,
            "approved_weight": risk_decision.approved_weight,
            "current_weight": risk_decision.current_weight,
            "approved_delta": risk_decision.approved_delta,
            "reference_nav": risk_decision.reference_nav,
            "reference_price": risk_decision.reference_price,
            "max_order_quantity": risk_decision.max_order_quantity,
            "authorization_source": "DETERMINISTIC",
            "authorized_side": (
                order.side.value if risk_decision.max_order_quantity > ZERO else None
            ),
            "market_context_snapshot_id": risk_decision.market_context_snapshot_id,
            "reason_codes": [reason.value for reason in risk_decision.reason_codes],
            "risk_policy_version_id": risk_decision.risk_policy_version_id,
            "decided_at": risk_decision.decided_at,
        }
        self.connection.execute(
            insert(risk_decision_table)
            .values(**risk_values)
            .on_conflict_do_nothing(index_elements=[risk_decision_table.c.id])
        )
        persisted_risk = (
            self.connection.execute(
                select(risk_decision_table).where(risk_decision_table.c.id == risk_decision.id)
            )
            .mappings()
            .one()
        )
        if any(persisted_risk[key] != value for key, value in risk_values.items()):
            raise ValueError("risk decision identity was reused with different facts")
        self.connection.execute(
            insert(order_intent)
            .values(
                id=order.id,
                portfolio_id=order.portfolio_id,
                symbol=str(order.symbol),
                side=order.side.value,
                quantity=order.quantity,
                decision_time=order.decision_time,
                risk_decision_id=order.risk_decision_id,
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
        persisted_quantity = self.connection.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (paper_fill.c.reversal_of_id.is_(None), paper_fill.c.quantity),
                            else_=-paper_fill.c.quantity,
                        )
                    ),
                    ZERO,
                )
            ).where(paper_fill.c.order_id == order.id)
        ).scalar_one()
        persisted_status = (
            "REJECTED"
            if not order.risk_approved
            else "FILLED"
            if persisted_quantity == order.quantity
            else "PARTIALLY_FILLED"
            if persisted_quantity > ZERO
            else "PENDING"
        )
        self.connection.execute(
            update(paper_order).where(paper_order.c.id == order.id).values(status=persisted_status)
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
