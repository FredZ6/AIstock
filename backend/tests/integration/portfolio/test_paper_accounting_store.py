from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from stock_platform.application.portfolio.accounting import (
    PostgresPaperAccountingStore,
    apply_fill,
    initial_funding,
    reverse_fill,
)
from stock_platform.application.portfolio.execution import ExecutionPolicy, PaperExecutionSimulator
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.fill import ExecutionBar
from stock_platform.domain.portfolio.ledger import is_balanced
from stock_platform.domain.portfolio.nav import rebuild_nav
from stock_platform.domain.portfolio.order import OrderIntent, OrderSide
from stock_platform.infrastructure.db.models.tables import cash_ledger, paper_fill

DECISION_TIME = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
POLICY_ID = UUID("30000000-0000-0000-0000-000000000011")


def test_replay_persists_one_append_only_fill_and_balanced_ledger(engine: Engine) -> None:
    portfolio_id = uuid4()
    order = OrderIntent(
        id=uuid4(),
        portfolio_id=portfolio_id,
        symbol=Symbol("NVDA"),
        side=OrderSide.BUY,
        quantity=Decimal("2"),
        decision_time=DECISION_TIME,
        execution_policy_version_id=POLICY_ID,
        risk_approved=True,
    )
    policy = ExecutionPolicy(
        id=POLICY_ID,
        version=f"execution-test-{uuid4()}",
        spread_bps=Decimal("4"),
        slippage_bps=Decimal("2"),
        fee_per_share=Decimal("0.01"),
        minimum_fee=Decimal("1"),
        volume_participation=Decimal("0.25"),
    )
    bar_time = DECISION_TIME + timedelta(minutes=1)
    fills = PaperExecutionSimulator(policy).execute(
        order,
        (
            ExecutionBar(
                Symbol("NVDA"),
                event_time=bar_time,
                available_at=bar_time + timedelta(seconds=2),
                open=Decimal("100"),
                volume=Decimal("100"),
            ),
        ),
    )
    entries = initial_funding(portfolio_id, Decimal("1000"), "USD", DECISION_TIME)
    for item in fills:
        entries = apply_fill(entries, item)

    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            text(
                "INSERT INTO execution_policy_version (id, version, policy) "
                "VALUES (:id, :version, CAST(:policy AS jsonb))"
            ),
            {
                "id": policy.id,
                "version": policy.version,
                "policy": (
                    '{"spread_bps":"4","slippage_bps":"2","fee_per_share":"0.01",'
                    '"minimum_fee":"1","volume_participation":"0.25",'
                    '"fill_timing":"NEXT_ELIGIBLE_BAR"}'
                ),
            },
        )
        store = PostgresPaperAccountingStore(connection)

        with pytest.raises(ValueError, match="balanced"):
            store.persist(order, fills, entries[:-1])

        store.persist(order, fills, entries)
        store.persist(order, fills, entries)

        assert connection.execute(
            select(func.count()).select_from(paper_fill).where(paper_fill.c.order_id == order.id)
        ).scalar_one() == len(fills)
        assert connection.execute(
            select(func.count())
            .select_from(cash_ledger)
            .where(cash_ledger.c.portfolio_id == portfolio_id)
        ).scalar_one() == len(entries)

        loaded_fills = store.load_fills(portfolio_id, as_of=bar_time + timedelta(minutes=1))
        loaded_entries = store.load_ledger(portfolio_id, as_of=bar_time + timedelta(minutes=1))
        nav = rebuild_nav(
            loaded_entries,
            loaded_fills,
            prices={Symbol("NVDA"): Decimal("100")},
            as_of=bar_time + timedelta(minutes=1),
        )
        assert loaded_fills == fills
        assert is_balanced(loaded_entries)
        assert nav.total == Decimal("998.92")

        correction_time = bar_time + timedelta(minutes=30)
        reversal, reversed_entries = reverse_fill(entries, fills[0], occurred_at=correction_time)
        store.persist(order, (reversal,), reversed_entries)
        corrected_fills = store.load_fills(
            portfolio_id, as_of=correction_time + timedelta(seconds=1)
        )
        corrected_entries = store.load_ledger(
            portfolio_id, as_of=correction_time + timedelta(seconds=1)
        )
        corrected_nav = rebuild_nav(
            corrected_entries,
            corrected_fills,
            prices={Symbol("NVDA"): Decimal("100")},
            as_of=correction_time + timedelta(seconds=1),
        )
        assert len(corrected_fills) == 2
        assert reversal.reversal_of_id == fills[0].id
        assert is_balanced(corrected_entries)
        assert corrected_nav.total == Decimal("1000")

        for table_name in ("paper_fill", "cash_ledger"):
            savepoint = connection.begin_nested()
            try:
                connection.execute(text(f"UPDATE {table_name} SET created_at = created_at"))
            except DBAPIError as error:
                savepoint.rollback()
                assert "append-only" in str(error.orig)
            else:
                savepoint.rollback()
                raise AssertionError(f"database allowed UPDATE on {table_name}")
        transaction.rollback()


def test_database_rejects_rejected_or_early_fill(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        policy_id = uuid4()
        order_id = uuid4()
        connection.execute(
            text("INSERT INTO execution_policy_version (id, version) VALUES (:id, :version)"),
            {"id": policy_id, "version": f"execution-test-{policy_id}"},
        )
        connection.execute(
            text(
                """
                INSERT INTO order_intent (
                    id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved
                ) VALUES (:id, :portfolio_id, 'NVDA', 'BUY', 1, :decision_time, :policy_id, false)
                """
            ),
            {
                "id": order_id,
                "portfolio_id": uuid4(),
                "decision_time": DECISION_TIME,
                "policy_id": policy_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO paper_order (
                    id, order_intent_id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved, status
                )
                SELECT id, id, portfolio_id, symbol, side, quantity, decision_time,
                       execution_policy_version_id, risk_approved, 'REJECTED'
                FROM order_intent WHERE id = :id
                """
            ),
            {"id": order_id},
        )
        savepoint = connection.begin_nested()
        try:
            connection.execute(
                text(
                    """
                    INSERT INTO paper_fill (
                        order_id, portfolio_id, symbol, side, quantity, price, fee, currency,
                        filled_at, source_bar_time, execution_policy_version_id, idempotency_key
                    ) VALUES (
                        :order_id, :portfolio_id, 'NVDA', 'BUY', 1, 100, 1, 'USD',
                        :filled_at, :filled_at, :policy_id, :idempotency_key
                    )
                    """
                ),
                {
                    "order_id": order_id,
                    "portfolio_id": uuid4(),
                    "filled_at": DECISION_TIME,
                    "policy_id": policy_id,
                    "idempotency_key": f"rejected-{order_id}",
                },
            )
        except DBAPIError as error:
            savepoint.rollback()
            assert "risk-approved" in str(error.orig) or "decision time" in str(error.orig)
        else:
            savepoint.rollback()
            raise AssertionError("database accepted a rejected or non-future fill")
        transaction.rollback()
