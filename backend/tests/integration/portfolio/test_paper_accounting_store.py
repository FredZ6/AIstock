from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError
from stock_platform.application.portfolio.accounting import (
    PostgresPaperAccountingStore,
    apply_fill,
    initial_funding,
    reverse_fill,
)
from stock_platform.application.portfolio.allocation import (
    MarketContextSnapshot,
    classify_market_regime,
)
from stock_platform.application.portfolio.execution import ExecutionPolicy, PaperExecutionSimulator
from stock_platform.application.portfolio.risk import RiskDecision, RiskDecisionStatus
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.fill import ExecutionBar
from stock_platform.domain.portfolio.ledger import is_balanced
from stock_platform.domain.portfolio.nav import rebuild_nav
from stock_platform.domain.portfolio.order import OrderIntent, OrderSide
from stock_platform.infrastructure.db.models.tables import cash_ledger, paper_fill, paper_order

DECISION_TIME = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
POLICY_ID = UUID("30000000-0000-0000-0000-000000000011")
RISK_POLICY_ID = UUID("40000000-0000-0000-0000-000000000011")
MARKET_CONTEXT_ID = UUID(int=53)


def market_context() -> MarketContextSnapshot:
    return classify_market_regime(
        snapshot_id=MARKET_CONTEXT_ID,
        as_of=DECISION_TIME,
        available_at=DECISION_TIME,
        qqq_trend=Decimal("0.05"),
        qqq_volatility=Decimal("0.18"),
        soxx_relative_strength=Decimal("0.02"),
        vix=Decimal("18"),
        algorithm_version="regime-test-v1",
        source_lineage=(UUID(int=54),),
    )


def approved_risk(order: OrderIntent) -> RiskDecision:
    assert order.risk_decision_id is not None
    return RiskDecision(
        id=order.risk_decision_id,
        proposal_id=order.id,
        research_decision_id=None,
        symbol=order.symbol,
        status=RiskDecisionStatus.APPROVED,
        requested_weight=Decimal("0.10"),
        approved_weight=Decimal("0.10"),
        reason_codes=(),
        risk_policy_version_id=RISK_POLICY_ID,
        decided_at=order.decision_time,
        current_weight=Decimal("0"),
        approved_delta=Decimal("0.10"),
        reference_nav=order.quantity * Decimal("1000"),
        reference_price=Decimal("100"),
        max_order_quantity=order.quantity,
        market_context_snapshot_id=MARKET_CONTEXT_ID,
        portfolio_id=order.portfolio_id,
    )


def insert_risk_fact(
    connection: Connection,
    *,
    portfolio_id: UUID,
    approved: bool,
    quantity: Decimal,
) -> UUID:
    policy_id = uuid4()
    decision_id = uuid4()
    connection.execute(
        text("INSERT INTO risk_policy_version (id, version) VALUES (:id, :version)"),
        {"id": policy_id, "version": f"risk-test-{policy_id}"},
    )
    connection.execute(
        text(
            """
            INSERT INTO risk_decision (
                id, proposal_id, portfolio_id, symbol, status, requested_weight,
                approved_weight, current_weight, approved_delta, reference_nav,
                reference_price, max_order_quantity, reason_codes,
                risk_policy_version_id, decided_at, market_context_snapshot_id
            ) VALUES (
                :id, :proposal_id, :portfolio_id, 'NVDA', :status,
                CASE WHEN :approved THEN 1 ELSE 0 END,
                CASE WHEN :approved THEN 1 ELSE 0 END,
                0, CASE WHEN :approved THEN 1 ELSE 0 END,
                CASE WHEN :approved THEN :quantity ELSE NULL END,
                CASE WHEN :approved THEN 1 ELSE NULL END,
                CASE WHEN :approved THEN :quantity ELSE 0 END,
                CASE WHEN :approved THEN '[]'::jsonb ELSE '["DRAWDOWN_LIMIT"]'::jsonb END,
                :policy_id, :decided_at,
                '00000000-0000-0000-0000-000000000016'::uuid
            )
            """
        ),
        {
            "id": decision_id,
            "proposal_id": uuid4(),
            "portfolio_id": portfolio_id,
            "status": "APPROVED" if approved else "REJECTED",
            "approved": approved,
            "quantity": quantity,
            "policy_id": policy_id,
            "decided_at": DECISION_TIME,
        },
    )
    return decision_id


def test_incremental_fills_advance_persisted_order_status(engine: Engine) -> None:
    portfolio_id = uuid4()
    risk_decision_id = uuid4()
    order = OrderIntent(
        id=uuid4(),
        portfolio_id=portfolio_id,
        symbol=Symbol("NVDA"),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        decision_time=DECISION_TIME,
        execution_policy_version_id=POLICY_ID,
        risk_approved=True,
        risk_decision_id=risk_decision_id,
    )
    policy = ExecutionPolicy(
        id=POLICY_ID,
        version=f"execution-incremental-{uuid4()}",
        spread_bps=Decimal("4"),
        slippage_bps=Decimal("2"),
        fee_per_share=Decimal("0.01"),
        minimum_fee=Decimal("1"),
        volume_participation=Decimal("0.10"),
    )
    simulator = PaperExecutionSimulator(policy)
    risk = approved_risk(order)

    def bar(minutes: int, volume: str) -> ExecutionBar:
        event_time = DECISION_TIME + timedelta(minutes=minutes)
        return ExecutionBar(
            Symbol("NVDA"),
            event_time=event_time,
            available_at=event_time + timedelta(seconds=2),
            open=Decimal("100"),
            volume=Decimal(volume),
            content_hash=f"incremental-status-{minutes}-{volume}",
        )

    first_batch = simulator.execute(order, (bar(1, "30"),), risk_decision=risk)
    second_batch = simulator.execute(
        order,
        (bar(2, "100"),),
        prior_fills=first_batch,
        risk_decision=risk,
    )
    entries = initial_funding(portfolio_id, Decimal("2000"), "USD", DECISION_TIME)

    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            text("INSERT INTO execution_policy_version (id, version) VALUES (:id, :version)"),
            {"id": policy.id, "version": policy.version},
        )
        connection.execute(
            text("INSERT INTO risk_policy_version (id, version) VALUES (:id, :version)"),
            {"id": RISK_POLICY_ID, "version": f"risk-test-{uuid4()}"},
        )
        store = PostgresPaperAccountingStore(connection)
        entries = apply_fill(entries, first_batch[0])
        store.persist(
            order, first_batch, entries, risk_decision=risk, market_context=market_context()
        )
        assert (
            connection.execute(
                select(paper_order.c.status).where(paper_order.c.id == order.id)
            ).scalar_one()
            == "PARTIALLY_FILLED"
        )

        entries = apply_fill(entries, second_batch[0])
        store.persist(
            order, second_batch, entries, risk_decision=risk, market_context=market_context()
        )
        assert (
            connection.execute(
                select(paper_order.c.status).where(paper_order.c.id == order.id)
            ).scalar_one()
            == "FILLED"
        )
        transaction.rollback()


def test_replay_persists_one_append_only_fill_and_balanced_ledger(engine: Engine) -> None:
    portfolio_id = uuid4()
    risk_decision_id = uuid4()
    order = OrderIntent(
        id=uuid4(),
        portfolio_id=portfolio_id,
        symbol=Symbol("NVDA"),
        side=OrderSide.BUY,
        quantity=Decimal("2"),
        decision_time=DECISION_TIME,
        execution_policy_version_id=POLICY_ID,
        risk_approved=True,
        risk_decision_id=risk_decision_id,
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
    risk = approved_risk(order)
    fills = PaperExecutionSimulator(policy).execute(
        order,
        (
            ExecutionBar(
                Symbol("NVDA"),
                event_time=bar_time,
                available_at=bar_time + timedelta(seconds=2),
                open=Decimal("100"),
                volume=Decimal("100"),
                content_hash="fixture-accounting-bar",
            ),
        ),
        risk_decision=risk,
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
        connection.execute(
            text("INSERT INTO risk_policy_version (id, version) VALUES (:id, :version)"),
            {"id": RISK_POLICY_ID, "version": f"risk-test-{uuid4()}"},
        )
        store = PostgresPaperAccountingStore(connection)
        with pytest.raises(ValueError, match="balanced"):
            store.persist(
                order,
                fills,
                entries[:-1],
                risk_decision=risk,
                market_context=market_context(),
            )

        store.persist(order, fills, entries, risk_decision=risk, market_context=market_context())
        store.persist(order, fills, entries, risk_decision=risk, market_context=market_context())

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
        store.persist(
            order,
            (reversal,),
            reversed_entries,
            risk_decision=risk,
            market_context=market_context(),
        )
        assert (
            connection.execute(
                select(paper_order.c.status).where(paper_order.c.id == order.id)
            ).scalar_one()
            == "PENDING"
        )
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
        portfolio_id = uuid4()
        risk_decision_id = insert_risk_fact(
            connection, portfolio_id=portfolio_id, approved=False, quantity=Decimal("1")
        )
        connection.execute(
            text("INSERT INTO execution_policy_version (id, version) VALUES (:id, :version)"),
            {"id": policy_id, "version": f"execution-test-{policy_id}"},
        )
        connection.execute(
            text(
                """
                INSERT INTO order_intent (
                    id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved, risk_decision_id
                ) VALUES (
                    :id, :portfolio_id, 'NVDA', 'BUY', 1, :decision_time,
                    :policy_id, false, :risk_decision_id
                )
                """
            ),
            {
                "id": order_id,
                "portfolio_id": portfolio_id,
                "decision_time": DECISION_TIME,
                "policy_id": policy_id,
                "risk_decision_id": risk_decision_id,
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


def test_database_rejects_cumulative_fill_above_order_quantity(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        policy_id = uuid4()
        order_id = uuid4()
        portfolio_id = uuid4()
        risk_decision_id = insert_risk_fact(
            connection, portfolio_id=portfolio_id, approved=True, quantity=Decimal("10")
        )
        connection.execute(
            text("INSERT INTO execution_policy_version (id, version) VALUES (:id, :version)"),
            {"id": policy_id, "version": f"execution-test-{policy_id}"},
        )
        connection.execute(
            text(
                """
                INSERT INTO order_intent (
                    id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved, risk_decision_id
                ) VALUES (
                    :id, :portfolio_id, 'NVDA', 'BUY', 10, :decision_time,
                    :policy_id, true, :risk_decision_id
                )
                """
            ),
            {
                "id": order_id,
                "portfolio_id": portfolio_id,
                "decision_time": DECISION_TIME,
                "policy_id": policy_id,
                "risk_decision_id": risk_decision_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO paper_order (
                    id, order_intent_id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved, status
                ) VALUES (
                    :id, :id, :portfolio_id, 'NVDA', 'BUY', 10, :decision_time,
                    :policy_id, true, 'PENDING'
                )
                """
            ),
            {
                "id": order_id,
                "portfolio_id": portfolio_id,
                "decision_time": DECISION_TIME,
                "policy_id": policy_id,
            },
        )
        for index, quantity in enumerate((Decimal("6"), Decimal("6")), start=1):
            savepoint = connection.begin_nested()
            try:
                connection.execute(
                    text(
                        """
                        INSERT INTO paper_fill (
                            order_id, portfolio_id, symbol, side, quantity, price, fee, currency,
                            filled_at, source_bar_time, execution_policy_version_id, idempotency_key
                        ) VALUES (
                            :order_id, :portfolio_id, 'NVDA', 'BUY', :quantity, 100, 0, 'USD',
                            :filled_at, :filled_at, :policy_id, :idempotency_key
                        )
                        """
                    ),
                    {
                        "order_id": order_id,
                        "portfolio_id": portfolio_id,
                        "quantity": quantity,
                        "filled_at": DECISION_TIME + timedelta(minutes=index),
                        "policy_id": policy_id,
                        "idempotency_key": f"overfill-{order_id}-{index}",
                    },
                )
            except DBAPIError as error:
                savepoint.rollback()
                assert index == 2
                assert "exceeds order quantity" in str(error.orig)
                break
            else:
                savepoint.commit()
        else:
            raise AssertionError("database accepted cumulative fills above order quantity")
        transaction.rollback()


def test_database_rejects_paper_order_that_changes_rejected_intent(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        policy_id = uuid4()
        order_id = uuid4()
        portfolio_id = uuid4()
        risk_decision_id = insert_risk_fact(
            connection, portfolio_id=portfolio_id, approved=False, quantity=Decimal("1")
        )
        connection.execute(
            text("INSERT INTO execution_policy_version (id, version) VALUES (:id, :version)"),
            {"id": policy_id, "version": f"execution-test-{policy_id}"},
        )
        connection.execute(
            text(
                """
                INSERT INTO order_intent (
                    id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved, risk_decision_id
                ) VALUES (
                    :id, :portfolio_id, 'NVDA', 'BUY', 1, :decision_time,
                    :policy_id, false, :risk_decision_id
                )
                """
            ),
            {
                "id": order_id,
                "portfolio_id": portfolio_id,
                "decision_time": DECISION_TIME,
                "policy_id": policy_id,
                "risk_decision_id": risk_decision_id,
            },
        )

        with pytest.raises(DBAPIError, match="must match order intent"):
            connection.execute(
                text(
                    """
                    INSERT INTO paper_order (
                        id, order_intent_id, portfolio_id, symbol, side, quantity, decision_time,
                        execution_policy_version_id, risk_approved, status
                    ) VALUES (
                        :id, :id, :portfolio_id, 'NVDA', 'BUY', 1, :decision_time,
                        :policy_id, true, 'PENDING'
                    )
                    """
                ),
                {
                    "id": order_id,
                    "portfolio_id": portfolio_id,
                    "decision_time": DECISION_TIME,
                    "policy_id": policy_id,
                },
            )
        transaction.rollback()


def test_database_allows_only_one_reversal_per_fill(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        policy_id = uuid4()
        order_id = uuid4()
        portfolio_id = uuid4()
        risk_decision_id = insert_risk_fact(
            connection, portfolio_id=portfolio_id, approved=True, quantity=Decimal("10")
        )
        connection.execute(
            text("INSERT INTO execution_policy_version (id, version) VALUES (:id, :version)"),
            {"id": policy_id, "version": f"execution-test-{policy_id}"},
        )
        connection.execute(
            text(
                """
                INSERT INTO order_intent (
                    id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved, risk_decision_id
                ) VALUES (
                    :id, :portfolio_id, 'NVDA', 'BUY', 10, :decision_time,
                    :policy_id, true, :risk_decision_id
                )
                """
            ),
            {
                "id": order_id,
                "portfolio_id": portfolio_id,
                "decision_time": DECISION_TIME,
                "policy_id": policy_id,
                "risk_decision_id": risk_decision_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO paper_order (
                    id, order_intent_id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved, status
                ) VALUES (
                    :id, :id, :portfolio_id, 'NVDA', 'BUY', 10, :decision_time,
                    :policy_id, true, 'PENDING'
                )
                """
            ),
            {
                "id": order_id,
                "portfolio_id": portfolio_id,
                "decision_time": DECISION_TIME,
                "policy_id": policy_id,
            },
        )
        original_id = None
        for index in (1, 2):
            fill_id = connection.execute(
                text(
                    """
                    INSERT INTO paper_fill (
                        order_id, portfolio_id, symbol, side, quantity, price, fee, currency,
                        filled_at, source_bar_time, execution_policy_version_id, idempotency_key
                    ) VALUES (
                        :order_id, :portfolio_id, 'NVDA', 'BUY', 4, 100, 0, 'USD',
                        :filled_at, :filled_at, :policy_id, :idempotency_key
                    ) RETURNING id
                    """
                ),
                {
                    "order_id": order_id,
                    "portfolio_id": portfolio_id,
                    "filled_at": DECISION_TIME + timedelta(minutes=index),
                    "policy_id": policy_id,
                    "idempotency_key": f"reversible-fill-{order_id}-{index}",
                },
            ).scalar_one()
            original_id = original_id or fill_id

        for index in (1, 2):
            savepoint = connection.begin_nested()
            try:
                connection.execute(
                    text(
                        """
                        INSERT INTO paper_fill (
                            order_id, portfolio_id, symbol, side, quantity, price, fee, currency,
                            filled_at, source_bar_time, execution_policy_version_id,
                            idempotency_key, reversal_of_id
                        ) VALUES (
                            :order_id, :portfolio_id, 'NVDA', 'SELL', 4, 100, 0, 'USD',
                            :filled_at, :filled_at, :policy_id, :idempotency_key, :original_id
                        )
                        """
                    ),
                    {
                        "order_id": order_id,
                        "portfolio_id": portfolio_id,
                        "filled_at": DECISION_TIME + timedelta(minutes=2 + index),
                        "policy_id": policy_id,
                        "idempotency_key": f"fill-reversal-{order_id}-{index}",
                        "original_id": original_id,
                    },
                )
            except DBAPIError as error:
                savepoint.rollback()
                assert index == 2
                assert "paper_fill_one_reversal_per_fill_idx" in str(error.orig)
                break
            else:
                savepoint.commit()
        else:
            raise AssertionError("database accepted a second reversal for one fill")
        transaction.rollback()
