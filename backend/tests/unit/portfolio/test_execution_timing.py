from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st
from stock_platform.application.portfolio.execution import ExecutionPolicy, PaperExecutionSimulator
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.fill import ExecutionBar
from stock_platform.domain.portfolio.order import OrderIntent, OrderSide

DECISION_TIME = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
PORTFOLIO_ID = UUID("10000000-0000-0000-0000-000000000001")
ORDER_ID = UUID("20000000-0000-0000-0000-000000000001")
POLICY_ID = UUID("30000000-0000-0000-0000-000000000001")


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
    )


def test_rejected_order_never_fills() -> None:
    fills = PaperExecutionSimulator(policy()).execute(order(approved=False), (bar(1),))

    assert fills == ()


def test_fill_uses_next_eligible_bar_and_is_strictly_after_decision() -> None:
    simulator = PaperExecutionSimulator(policy())
    bars = (bar(0), bar(1, symbol="AAPL"), bar(2, open_="101"), bar(3, open_="102"))

    fills = simulator.execute(order(), bars)

    assert len(fills) == 1
    fill = fills[0]
    assert fill.source_bar_time == DECISION_TIME + timedelta(minutes=2)
    assert fill.filled_at > DECISION_TIME
    assert fill.price == Decimal("101.0404")
    assert fill.execution_policy_version_id == POLICY_ID
    assert simulator.execute(order(), tuple(reversed(bars))) == fills


def test_available_volume_cap_creates_deterministic_partial_fills() -> None:
    simulator = PaperExecutionSimulator(policy(participation="0.10"))
    bars = (bar(1, volume="30"), bar(2, volume="20"), bar(3, volume="100"))

    fills = simulator.execute(order(quantity="12"), bars)

    assert [fill.quantity for fill in fills] == [Decimal("3"), Decimal("2"), Decimal("7")]
    assert len({fill.id for fill in fills}) == 3
    assert simulator.execute(order(quantity="12"), bars + (bars[-1],)) == fills


@given(minutes=st.integers(min_value=-30, max_value=30))
def test_fills_never_precede_or_equal_decision_time(minutes: int) -> None:
    fills = PaperExecutionSimulator(policy()).execute(order(), (bar(minutes),))

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
