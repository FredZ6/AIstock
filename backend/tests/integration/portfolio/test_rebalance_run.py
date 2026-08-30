from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.portfolio.graph import PortfolioDecisionGraph
from stock_platform.agents.portfolio.state import FrozenResearchDecision
from stock_platform.application.portfolio.accounting import (
    PostgresPaperAccountingStore,
    apply_fill,
    initial_funding,
)
from stock_platform.application.portfolio.allocation import (
    MarketContextSnapshot,
    classify_market_regime,
)
from stock_platform.application.portfolio.benchmarks import PriceFrame
from stock_platform.application.portfolio.execution import ExecutionPolicy
from stock_platform.application.portfolio.risk import (
    RiskDecisionStatus,
    RiskPolicy,
    RiskReason,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.fill import ExecutionBar, PaperFill
from stock_platform.domain.portfolio.order import OrderSide
from stock_platform.domain.research.claims import ResearchOpinionValue
from stock_platform.infrastructure.db.models.tables import order_intent, risk_decision

DECISION_TIME = datetime(2026, 8, 21, 20, 0, tzinfo=UTC)
PORTFOLIO_ID = UUID("10000000-0000-0000-0000-000000000012")
RISK_POLICY_ID = UUID("40000000-0000-0000-0000-000000000012")
EXECUTION_POLICY_ID = UUID("30000000-0000-0000-0000-000000000012")
MARKET_CONTEXT_ID = UUID("50000000-0000-0000-0000-000000000012")


def specification() -> TaskSpecification:
    return TaskSpecification(
        objective="rebalance paper portfolio",
        symbols=("NVDA",),
        decision_time=DECISION_TIME,
        data_cutoff=DECISION_TIME,
        allowed_tools=frozenset(),
        budgets=BudgetLimits(
            llm_calls=3,
            tool_calls=0,
            tokens=5000,
            reflections=0,
            wall_time=timedelta(seconds=60),
        ),
        output_schema="PortfolioDecision",
        completion_rules=frozenset({"risk_decision_for_every_order"}),
        policy_versions=PolicyVersions(
            research_scoring="research-v1",
            risk="risk-v1",
            execution="execution-v1",
            confidence="confidence-v1",
            prompt="portfolio-prompt-v1",
            model="fixture-proposer-v1",
        ),
    )


def graph(
    *,
    spread_bps: str = "0",
    slippage_bps: str = "0",
    fee_per_share: str = "0",
    minimum_fee: str = "0",
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> PortfolioDecisionGraph:
    return PortfolioDecisionGraph(
        risk_policy=RiskPolicy(
            id=RISK_POLICY_ID,
            version="risk-v1",
            max_position_weight=Decimal("0.20"),
            max_gross_exposure=Decimal("1"),
            min_cash_reserve=Decimal("0.05"),
            max_daily_turnover=Decimal("0.25"),
            max_drawdown=Decimal("0.20"),
            max_research_age=timedelta(days=2),
            earnings_blackout=timedelta(days=1),
        ),
        execution_policy=ExecutionPolicy(
            id=EXECUTION_POLICY_ID,
            version="execution-v1",
            spread_bps=Decimal(spread_bps),
            slippage_bps=Decimal(slippage_bps),
            fee_per_share=Decimal(fee_per_share),
            minimum_fee=Decimal(minimum_fee),
            volume_participation=Decimal("1"),
        ),
        checkpointer=checkpointer,
    )


def research(*, available_at: datetime = DECISION_TIME) -> FrozenResearchDecision:
    return FrozenResearchDecision(
        decision_id=UUID(int=101),
        thesis_id=UUID(int=102),
        symbol=Symbol("NVDA"),
        opinion=ResearchOpinionValue.BULLISH,
        as_of=DECISION_TIME - timedelta(hours=1),
        available_at=available_at,
        evidence_complete=True,
        proposed_weight=Decimal("0.50"),
        rationale="fixture model target",
        policy_versions=specification().policy_versions,
        data_cutoff=DECISION_TIME,
    )


def market_context() -> MarketContextSnapshot:
    return classify_market_regime(
        snapshot_id=MARKET_CONTEXT_ID,
        as_of=DECISION_TIME,
        available_at=DECISION_TIME,
        qqq_trend=Decimal("0.05"),
        qqq_volatility=Decimal("0.18"),
        soxx_relative_strength=Decimal("0.02"),
        vix=Decimal("18"),
        algorithm_version="regime-v1",
        source_lineage=(UUID(int=301), UUID(int=302), UUID(int=303)),
    )


def decision_bar() -> ExecutionBar:
    return ExecutionBar(
        Symbol("NVDA"),
        event_time=DECISION_TIME - timedelta(minutes=1),
        available_at=DECISION_TIME - timedelta(seconds=30),
        open=Decimal("100"),
        volume=Decimal("100"),
        content_hash="decision-mark-nvda",
    )


def test_overweight_model_proposal_is_clipped_before_next_bar_fill() -> None:
    next_bar_time = DECISION_TIME + timedelta(minutes=1)
    result = graph().run(
        run_id="portfolio-run-1",
        portfolio_id=PORTFOLIO_ID,
        specification=specification(),
        market_context=market_context(),
        research=(research(),),
        bars=(
            decision_bar(),
            ExecutionBar(
                Symbol("NVDA"),
                event_time=next_bar_time,
                available_at=next_bar_time + timedelta(seconds=2),
                open=Decimal("100"),
                volume=Decimal("100"),
                content_hash="rebalance-next-bar",
            ),
        ),
        ledger=initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", DECISION_TIME),
    )

    assert result.route == (
        "load_frozen_research",
        "generate_candidates",
        "build_target_weights",
        "risk_gateway",
        "create_pending_orders",
        "next_eligible_bar_fill",
        "update_ledger_nav",
    )
    assert result.external_tool_calls == 0
    assert result.market_context.id == MARKET_CONTEXT_ID
    assert len(result.risk_decisions) == len(result.order_intents) == 1
    assert result.risk_decisions[0].status is RiskDecisionStatus.CLIPPED
    assert result.risk_decisions[0].approved_weight == Decimal("0.20")
    assert result.order_intents[0].risk_decision_id == result.risk_decisions[0].id
    assert result.order_intents[0].quantity == Decimal("2.0")
    assert result.fills[0].filled_at > DECISION_TIME
    assert result.nav.total == Decimal("1000.0")
    assert result.benchmarks.cash == ()


def test_portfolio_graph_persists_native_checkpoint_by_run_id() -> None:
    saver = InMemorySaver()
    run_id = "portfolio-checkpoint-run"

    result = graph(checkpointer=saver).run(
        run_id=run_id,
        portfolio_id=PORTFOLIO_ID,
        specification=specification(),
        market_context=market_context(),
        research=(research(),),
        bars=(decision_bar(),),
        ledger=initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", DECISION_TIME),
    )

    assert result.nav.total == Decimal("1000")
    assert saver.get({"configurable": {"thread_id": run_id}}) is not None


def test_future_or_stale_research_cannot_create_order_or_fill() -> None:
    result = graph().run(
        run_id="portfolio-run-2",
        portfolio_id=PORTFOLIO_ID,
        specification=specification(),
        market_context=market_context(),
        research=(research(available_at=DECISION_TIME + timedelta(seconds=1)),),
        bars=(decision_bar(),),
        ledger=initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", DECISION_TIME),
    )

    assert result.order_intents == ()
    assert result.fills == ()


def test_portfolio_accepts_visible_research_with_its_own_prompt_model_and_earlier_cutoff() -> None:
    earlier = DECISION_TIME - timedelta(minutes=15)
    frozen = replace(
        research(available_at=earlier),
        data_cutoff=earlier,
        policy_versions=PolicyVersions(
            research_scoring="research-v1",
            risk="risk-v1",
            execution="execution-v1",
            confidence="confidence-v1",
            prompt="research-prompt-v1",
            model="research-model-v1",
        ),
    )

    result = graph().run(
        run_id="portfolio-run-cross-task-policy-pins",
        portfolio_id=PORTFOLIO_ID,
        specification=specification(),
        market_context=market_context(),
        research=(frozen,),
        bars=(decision_bar(),),
        ledger=initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", DECISION_TIME),
    )

    assert result.actions


def test_post_fill_nav_uses_the_fill_price_at_the_nav_timestamp() -> None:
    next_bar_time = DECISION_TIME + timedelta(minutes=1)
    result = graph().run(
        run_id="portfolio-run-fill-mark",
        portfolio_id=PORTFOLIO_ID,
        specification=specification(),
        market_context=market_context(),
        research=(research(),),
        bars=(
            decision_bar(),
            ExecutionBar(
                Symbol("NVDA"),
                event_time=next_bar_time,
                available_at=next_bar_time + timedelta(seconds=2),
                open=Decimal("110"),
                volume=Decimal("100"),
                content_hash="rebalance-fill-mark",
            ),
        ),
        ledger=initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", DECISION_TIME),
    )

    assert result.fills[0].price == Decimal("110")
    assert result.nav.total == Decimal("1000.0")


def test_post_fill_nav_preserves_execution_cost_against_the_market_mark() -> None:
    next_bar_time = DECISION_TIME + timedelta(minutes=1)
    result = graph(spread_bps="4", slippage_bps="2").run(
        run_id="portfolio-run-cost-mark",
        portfolio_id=PORTFOLIO_ID,
        specification=specification(),
        market_context=market_context(),
        research=(research(),),
        bars=(
            decision_bar(),
            ExecutionBar(
                Symbol("NVDA"),
                event_time=next_bar_time,
                available_at=next_bar_time + timedelta(seconds=2),
                open=Decimal("100"),
                volume=Decimal("100"),
                content_hash="rebalance-cost-mark",
            ),
        ),
        ledger=initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", DECISION_TIME),
    )

    assert result.fills[0].price == Decimal("100.0400")
    assert result.nav.total == Decimal("999.9200")


def test_fully_invested_portfolio_uses_reconstructed_nav_without_division_by_zero() -> None:
    prior_fill = PaperFill(
        id=UUID(int=401),
        order_id=UUID(int=402),
        portfolio_id=PORTFOLIO_ID,
        symbol=Symbol("NVDA"),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("100"),
        fee=Decimal("0"),
        currency="USD",
        filled_at=DECISION_TIME - timedelta(days=1),
        source_bar_time=DECISION_TIME - timedelta(days=1),
        execution_policy_version_id=EXECUTION_POLICY_ID,
    )
    ledger = apply_fill(
        initial_funding(
            PORTFOLIO_ID,
            Decimal("1000"),
            "USD",
            DECISION_TIME - timedelta(days=2),
        ),
        prior_fill,
    )

    result = graph().run(
        run_id="portfolio-run-fully-invested",
        portfolio_id=PORTFOLIO_ID,
        specification=specification(),
        market_context=market_context(),
        research=(research(),),
        bars=(decision_bar(),),
        ledger=ledger,
        prior_fills=(prior_fill,),
    )

    assert result.risk_decisions[0].reference_nav == Decimal("1000")
    assert result.order_intents[0].side is OrderSide.SELL


def test_benchmarks_use_decision_nav_as_common_fee_basis() -> None:
    next_bar_time = DECISION_TIME + timedelta(minutes=1)
    frame_time = DECISION_TIME + timedelta(days=1)
    result = graph(fee_per_share="1", minimum_fee="0").run(
        run_id="portfolio-run-benchmark-fees",
        portfolio_id=PORTFOLIO_ID,
        specification=specification(),
        market_context=market_context(),
        research=(research(),),
        bars=(
            decision_bar(),
            ExecutionBar(
                Symbol("NVDA"),
                event_time=next_bar_time,
                available_at=next_bar_time + timedelta(seconds=2),
                open=Decimal("100"),
                volume=Decimal("100"),
                content_hash="benchmark-fee-fill",
            ),
        ),
        ledger=initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", DECISION_TIME),
        benchmark_frames=(
            PriceFrame(
                DECISION_TIME,
                {Symbol("QQQ"): Decimal("100"), Symbol("NVDA"): Decimal("100")},
            ),
            PriceFrame(
                frame_time,
                {Symbol("QQQ"): Decimal("100"), Symbol("NVDA"): Decimal("100")},
            ),
        ),
    )

    assert result.nav.total == Decimal("998.0")
    assert result.benchmarks.qqq == (Decimal("-0.01"),)


def test_daily_turnover_uses_utc_day_boundary() -> None:
    decision_time = datetime(2026, 8, 22, 0, 30, tzinfo=timezone(timedelta(hours=8)))
    decision_time_utc = decision_time.astimezone(UTC)
    prior_fill = PaperFill(
        id=UUID(int=411),
        order_id=UUID(int=412),
        portfolio_id=PORTFOLIO_ID,
        symbol=Symbol("AAPL"),
        side=OrderSide.BUY,
        quantity=Decimal("2"),
        price=Decimal("100"),
        fee=Decimal("0"),
        currency="USD",
        filled_at=decision_time_utc - timedelta(hours=1),
        source_bar_time=decision_time_utc - timedelta(hours=1),
        execution_policy_version_id=EXECUTION_POLICY_ID,
    )
    ledger = apply_fill(
        initial_funding(
            PORTFOLIO_ID,
            Decimal("1000"),
            "USD",
            decision_time_utc - timedelta(days=1),
        ),
        prior_fill,
    )
    run_specification = replace(
        specification(),
        decision_time=decision_time,
        data_cutoff=decision_time,
    )
    frozen = replace(
        research(),
        as_of=decision_time_utc - timedelta(hours=2),
        available_at=decision_time_utc,
        data_cutoff=decision_time_utc,
    )
    context = replace(
        market_context(),
        as_of=decision_time_utc,
        available_at=decision_time_utc,
    )

    result = graph().run(
        run_id="portfolio-run-utc-turnover",
        portfolio_id=PORTFOLIO_ID,
        specification=run_specification,
        market_context=context,
        research=(frozen,),
        bars=(
            ExecutionBar(
                Symbol("AAPL"),
                event_time=decision_time_utc - timedelta(minutes=1),
                available_at=decision_time_utc - timedelta(seconds=30),
                open=Decimal("100"),
                volume=Decimal("100"),
                content_hash="utc-mark-aapl",
            ),
            ExecutionBar(
                Symbol("NVDA"),
                event_time=decision_time_utc - timedelta(minutes=1),
                available_at=decision_time_utc - timedelta(seconds=30),
                open=Decimal("100"),
                volume=Decimal("100"),
                content_hash="utc-mark-nvda",
            ),
        ),
        ledger=ledger,
        prior_fills=(prior_fill,),
    )

    assert result.risk_decisions[0].approved_weight == Decimal("0.05")
    assert RiskReason.DAILY_TURNOVER in result.risk_decisions[0].reason_codes


def test_rebalance_passes_drawdown_state_to_risk_gateway() -> None:
    result = graph().run(
        run_id="portfolio-run-risk-state",
        portfolio_id=PORTFOLIO_ID,
        specification=specification(),
        market_context=market_context(),
        research=(research(),),
        bars=(decision_bar(),),
        ledger=initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", DECISION_TIME),
        drawdown=Decimal("-0.25"),
    )

    assert result.risk_decisions[0].status is RiskDecisionStatus.REJECTED
    assert RiskReason.DRAWDOWN_LIMIT in result.risk_decisions[0].reason_codes
    assert result.order_intents == ()
    assert result.fills == ()


def test_rebalance_rejects_ledger_from_another_portfolio() -> None:
    with pytest.raises(ValueError, match="ledger does not belong"):
        graph().run(
            run_id="portfolio-run-invalid-snapshot",
            portfolio_id=PORTFOLIO_ID,
            specification=specification(),
            market_context=market_context(),
            research=(research(),),
            bars=(decision_bar(),),
            ledger=initial_funding(UUID(int=999), Decimal("1000"), "USD", DECISION_TIME),
        )


def test_rebalance_rejects_mismatched_research_policy_pins() -> None:
    frozen = research()
    mismatched = replace(
        frozen,
        policy_versions=replace(frozen.policy_versions, risk="wrong-risk"),
    )

    with pytest.raises(ValueError, match="policy pins"):
        graph().run(
            run_id="portfolio-run-policy-mismatch",
            portfolio_id=PORTFOLIO_ID,
            specification=specification(),
            market_context=market_context(),
            research=(mismatched,),
            bars=(decision_bar(),),
            ledger=initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", DECISION_TIME),
        )


def test_accepted_order_persists_immutable_risk_decision_link(engine: Engine) -> None:
    next_bar_time = DECISION_TIME + timedelta(minutes=1)
    result = graph().run(
        run_id="portfolio-run-persisted",
        portfolio_id=PORTFOLIO_ID,
        specification=specification(),
        market_context=market_context(),
        research=(research(),),
        bars=(
            decision_bar(),
            ExecutionBar(
                Symbol("NVDA"),
                event_time=next_bar_time,
                available_at=next_bar_time + timedelta(seconds=2),
                open=Decimal("100"),
                volume=Decimal("100"),
                content_hash="rebalance-persisted-bar",
            ),
        ),
        ledger=initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", DECISION_TIME),
    )
    decision = result.risk_decisions[0]
    order = result.order_intents[0]

    with engine.connect() as connection:
        transaction = connection.begin()
        research_policy_id = UUID(int=201)
        confidence_policy_id = UUID(int=202)
        connection.execute(
            text(
                "INSERT INTO research_scoring_policy_version (id, version) "
                "VALUES (:id, 'research-v1')"
            ),
            {"id": research_policy_id},
        )
        connection.execute(
            text("INSERT INTO risk_policy_version (id, version) VALUES (:id, 'risk-v1')"),
            {"id": RISK_POLICY_ID},
        )
        connection.execute(
            text("INSERT INTO execution_policy_version (id, version) VALUES (:id, 'execution-v1')"),
            {"id": EXECUTION_POLICY_ID},
        )
        connection.execute(
            text(
                "INSERT INTO confidence_policy_version (id, version) VALUES (:id, 'confidence-v1')"
            ),
            {"id": confidence_policy_id},
        )
        connection.execute(
            text(
                "INSERT INTO investment_thesis (id, confidence_policy_version_id) "
                "VALUES (:id, :confidence_policy_id)"
            ),
            {"id": UUID(int=102), "confidence_policy_id": confidence_policy_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO decision_snapshot (
                    id, thesis_id, research_scoring_policy_version_id,
                    risk_policy_version_id, execution_policy_version_id,
                    confidence_policy_version_id, prompt_version, model_version, data_cutoff
                ) VALUES (
                    :id, :thesis_id, :research_policy_id, :risk_policy_id,
                    :execution_policy_id, :confidence_policy_id,
                    'portfolio-prompt-v1', 'fixture-proposer-v1', :data_cutoff
                )
                """
            ),
            {
                "id": UUID(int=101),
                "thesis_id": UUID(int=102),
                "research_policy_id": research_policy_id,
                "risk_policy_id": RISK_POLICY_ID,
                "execution_policy_id": EXECUTION_POLICY_ID,
                "confidence_policy_id": confidence_policy_id,
                "data_cutoff": DECISION_TIME,
            },
        )
        store = PostgresPaperAccountingStore(connection)
        store.persist(
            order,
            result.fills,
            result.ledger,
            risk_decision=decision,
            market_context=market_context(),
        )

        persisted = connection.execute(
            select(
                order_intent.c.risk_decision_id,
                risk_decision.c.status,
                risk_decision.c.approved_weight,
                risk_decision.c.market_context_snapshot_id,
            )
            .select_from(
                order_intent.join(
                    risk_decision,
                    order_intent.c.risk_decision_id == risk_decision.c.id,
                )
            )
            .where(order_intent.c.id == order.id)
        ).one()
        assert persisted == (
            decision.id,
            "CLIPPED",
            Decimal("0.20"),
            MARKET_CONTEXT_ID,
        )

        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError, match="authorization"):
            connection.execute(
                text("UPDATE order_intent SET quantity = quantity * 10 WHERE id = :id"),
                {"id": order.id},
            )
        savepoint.rollback()

        alternate_execution_policy_id = UUID(int=203)
        connection.execute(
            text(
                "INSERT INTO execution_policy_version (id, version) "
                "VALUES (:id, 'execution-wrong-v1')"
            ),
            {"id": alternate_execution_policy_id},
        )
        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError, match="execution policy"):
            connection.execute(
                text(
                    "UPDATE order_intent SET execution_policy_version_id = :policy_id "
                    "WHERE id = :id"
                ),
                {"policy_id": alternate_execution_policy_id, "id": order.id},
            )
        savepoint.rollback()

        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError, match="status_facts"):
            connection.execute(
                text(
                    """
                    INSERT INTO risk_decision (
                        id, proposal_id, portfolio_id, symbol, status,
                        requested_weight, approved_weight, current_weight, approved_delta,
                        reference_nav, reference_price, max_order_quantity, reason_codes,
                        risk_policy_version_id, market_context_snapshot_id, decided_at
                    ) VALUES (
                        gen_random_uuid(), gen_random_uuid(), :portfolio_id, 'NVDA', 'APPROVED',
                        0.20, 0.10, 0, 0.10, 1000, 100, 1, '[]'::jsonb,
                        :risk_policy_id, :market_context_id, :decided_at
                    )
                    """
                ),
                {
                    "portfolio_id": PORTFOLIO_ID,
                    "risk_policy_id": RISK_POLICY_ID,
                    "market_context_id": MARKET_CONTEXT_ID,
                    "decided_at": DECISION_TIME,
                },
            )
        savepoint.rollback()

        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(
                text("UPDATE risk_decision SET approved_weight = 0 WHERE id = :id"),
                {"id": decision.id},
            )
        savepoint.rollback()
        transaction.rollback()
