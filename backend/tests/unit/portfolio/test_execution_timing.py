from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st
from stock_platform.application.portfolio.execution import ExecutionPolicy, PaperExecutionSimulator
from stock_platform.application.portfolio.risk import RiskDecision, RiskDecisionStatus
from stock_platform.application.portfolio.valuation import visible_bar_prices
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.fill import ExecutionBar
from stock_platform.domain.portfolio.order import OrderIntent, OrderSide

DECISION_TIME = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
PORTFOLIO_ID = UUID("10000000-0000-0000-0000-000000000001")
ORDER_ID = UUID("20000000-0000-0000-0000-000000000001")
POLICY_ID = UUID("30000000-0000-0000-0000-000000000001")
RISK_DECISION_ID = UUID("40000000-0000-0000-0000-000000000001")


def policy(*, participation: str = "0.25") -> ExecutionPolicy:
    return ExecutionPolicy(
        id=POLICY_ID,
        version="execution-v1",
        spread_bps=Decimal("4"),
        slippage_bps=Decimal("2"),
        fee_per_share=Decimal("0.01"),
        minimum_fee=Decimal("1"),
        volume_participation=Decimal(participation),
    )


def order(*, approved: bool = True, quantity: str = "10") -> OrderIntent:
    return OrderIntent(
        id=ORDER_ID,
        portfolio_id=PORTFOLIO_ID,
        symbol=Symbol("NVDA"),
        side=OrderSide.BUY,
        quantity=Decimal(quantity),
        decision_time=DECISION_TIME,
        execution_policy_version_id=POLICY_ID,
        risk_approved=approved,
        risk_decision_id=RISK_DECISION_ID,
    )


def risk(intent: OrderIntent) -> RiskDecision:
    return RiskDecision(
        id=RISK_DECISION_ID,
        proposal_id=UUID(int=50),
        research_decision_id=UUID(int=51),
        symbol=intent.symbol,
        status=RiskDecisionStatus.APPROVED,
        requested_weight=Decimal("0.10"),
        approved_weight=Decimal("0.10"),
        reason_codes=(),
        risk_policy_version_id=UUID(int=52),
        decided_at=intent.decision_time,
        current_weight=Decimal("0"),
        approved_delta=Decimal("0.10"),
        reference_nav=intent.quantity * Decimal("1000"),
        reference_price=Decimal("100"),
        max_order_quantity=intent.quantity,
        market_context_snapshot_id=UUID(int=53),
        portfolio_id=intent.portfolio_id,
    )


def bar(
    minutes: int,
    *,
    symbol: str = "NVDA",
    open_: str = "100",
    volume: str = "100",
) -> ExecutionBar:
    event_time = DECISION_TIME + timedelta(minutes=minutes)
    return ExecutionBar(
        symbol=Symbol(symbol),
        event_time=event_time,
        available_at=event_time + timedelta(seconds=2),
        open=Decimal(open_),
        volume=Decimal(volume),
        content_hash=f"fixture-{symbol}-{minutes}-{open_}-{volume}",
    )


def test_rejected_order_never_fills() -> None:
    fills = PaperExecutionSimulator(policy()).execute(order(approved=False), (bar(1),))

    assert fills == ()


def test_fill_uses_next_eligible_bar_and_is_strictly_after_decision() -> None:
    simulator = PaperExecutionSimulator(policy())
    bars = (bar(0), bar(1, symbol="AAPL"), bar(2, open_="101"), bar(3, open_="102"))

    intent = order()
    fills = simulator.execute(intent, bars, risk_decision=risk(intent))

    assert len(fills) == 1
    fill = fills[0]
    assert fill.source_bar_time == DECISION_TIME + timedelta(minutes=2)
    assert fill.filled_at > DECISION_TIME
    assert fill.price == Decimal("101.0404")
    assert fill.execution_policy_version_id == POLICY_ID
    assert simulator.execute(intent, tuple(reversed(bars)), risk_decision=risk(intent)) == fills


def test_available_volume_cap_creates_deterministic_partial_fills() -> None:
    simulator = PaperExecutionSimulator(policy(participation="0.10"))
    bars = (bar(1, volume="30"), bar(2, volume="20"), bar(3, volume="100"))

    intent = order(quantity="12")
    fills = simulator.execute(intent, bars, risk_decision=risk(intent))

    assert [fill.quantity for fill in fills] == [Decimal("3"), Decimal("2"), Decimal("7")]
    assert len({fill.id for fill in fills}) == 3
    assert simulator.execute(intent, bars + (bars[-1],), risk_decision=risk(intent)) == fills


def test_incremental_bars_respect_quantity_already_filled() -> None:
    simulator = PaperExecutionSimulator(policy(participation="0.10"))
    intent = order(quantity="10")
    first_batch = simulator.execute(intent, (bar(1, volume="30"),), risk_decision=risk(intent))

    second_batch = simulator.execute(
        intent,
        (bar(2, volume="100"),),
        prior_fills=first_batch,
        risk_decision=risk(intent),
    )

    assert [fill.quantity for fill in first_batch] == [Decimal("3")]
    assert [fill.quantity for fill in second_batch] == [Decimal("7")]
    assert sum((fill.quantity for fill in first_batch + second_batch), Decimal("0")) == Decimal(
        "10"
    )


def test_same_timestamp_revisions_are_canonical_across_input_order() -> None:
    simulator = PaperExecutionSimulator(policy())
    event_time = DECISION_TIME + timedelta(minutes=1)
    available_at = event_time + timedelta(seconds=2)
    first_revision = ExecutionBar(
        symbol=Symbol("NVDA"),
        event_time=event_time,
        available_at=available_at,
        open=Decimal("100"),
        volume=Decimal("100"),
        content_hash="revision-a",
    )
    second_revision = ExecutionBar(
        symbol=Symbol("NVDA"),
        event_time=event_time,
        available_at=available_at,
        open=Decimal("101"),
        volume=Decimal("100"),
        content_hash="revision-b",
    )

    intent = order()
    forward = simulator.execute(
        intent, (first_revision, second_revision), risk_decision=risk(intent)
    )
    reversed_input = simulator.execute(
        intent, (second_revision, first_revision), risk_decision=risk(intent)
    )

    assert forward == reversed_input
    assert forward[0].price == Decimal("101.0404")


def test_valuation_rejects_conflicting_revision_identity_in_both_input_orders() -> None:
    first = bar(0, open_="100")
    conflicting = replace(first, open=Decimal("101"))

    for bars in ((first, conflicting), (conflicting, first)):
        with pytest.raises(ValueError, match="conflicting bars"):
            visible_bar_prices(
                bars,
                event_cutoff=DECISION_TIME,
                available_cutoff=DECISION_TIME + timedelta(seconds=2),
            )


@given(minutes=st.integers(min_value=-30, max_value=30))
def test_fills_never_precede_or_equal_decision_time(minutes: int) -> None:
    intent = order()
    fills = PaperExecutionSimulator(policy()).execute(
        intent, (bar(minutes),), risk_decision=risk(intent)
    )

    assert all(fill.filled_at > DECISION_TIME for fill in fills)
    assert fills == () if minutes <= 0 else len(fills) == 1


def test_execution_inputs_reject_naive_time_and_binary_float() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        OrderIntent(
            id=ORDER_ID,
            portfolio_id=PORTFOLIO_ID,
            symbol=Symbol("NVDA"),
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            decision_time=datetime(2026, 8, 21, 14, 30),
            execution_policy_version_id=POLICY_ID,
            risk_approved=True,
            risk_decision_id=RISK_DECISION_ID,
        )

    intent = order(quantity="20")
    with pytest.raises(ValueError, match="risk authorization"):
        PaperExecutionSimulator(policy()).execute(
            intent,
            (bar(1),),
            risk_decision=risk(order(quantity="10")),
        )
    authorized = order()
    for changed in (
        replace(authorized, portfolio_id=UUID(int=999)),
        replace(authorized, decision_time=DECISION_TIME + timedelta(seconds=1)),
    ):
        with pytest.raises(ValueError, match="risk authorization"):
            PaperExecutionSimulator(policy()).execute(
                changed,
                (bar(1),),
                risk_decision=risk(authorized),
            )

    with pytest.raises(TypeError, match="Decimal"):
        ExecutionPolicy(
            id=POLICY_ID,
            version="invalid-float",
            spread_bps=4.0,  # type: ignore[arg-type]
            slippage_bps=Decimal("2"),
            fee_per_share=Decimal("0.01"),
            minimum_fee=Decimal("1"),
            volume_participation=Decimal("0.25"),
        )
