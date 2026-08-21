from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from stock_platform.application.portfolio.allocation import (
    MarketRegime,
    PortfolioActionValue,
    classify_market_regime,
    opinion_to_action,
)
from stock_platform.application.portfolio.risk import (
    PortfolioRiskSnapshot,
    RiskDecision,
    RiskDecisionStatus,
    RiskGateway,
    RiskPolicy,
    RiskReason,
    TargetWeightProposal,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.order import OrderIntent, OrderSide
from stock_platform.domain.research.claims import ResearchOpinionValue

DECISION_TIME = datetime(2026, 8, 21, 20, 0, tzinfo=UTC)
POLICY_ID = UUID("40000000-0000-0000-0000-000000000012")
MARKET_CONTEXT_ID = UUID("50000000-0000-0000-0000-000000000012")


def policy() -> RiskPolicy:
    return RiskPolicy(
        id=POLICY_ID,
        version="risk-v1",
        max_position_weight=Decimal("0.20"),
        max_gross_exposure=Decimal("1.00"),
        min_cash_reserve=Decimal("0.05"),
        max_daily_turnover=Decimal("0.25"),
        max_drawdown=Decimal("0.20"),
        max_research_age=timedelta(days=2),
        earnings_blackout=timedelta(days=1),
    )


def snapshot(
    *,
    cash_weight: str = "1",
    current_weights: dict[Symbol, Decimal] | None = None,
    turnover: str = "0",
    drawdown: str = "0",
    prices: dict[Symbol, Decimal] | None = None,
) -> PortfolioRiskSnapshot:
    return PortfolioRiskSnapshot(
        portfolio_id=UUID(int=700),
        market_context_snapshot_id=MARKET_CONTEXT_ID,
        nav=Decimal("1000"),
        cash_weight=Decimal(cash_weight),
        current_weights=current_weights or {},
        prices=prices or {Symbol("NVDA"): Decimal("100")},
        daily_turnover=Decimal(turnover),
        drawdown=Decimal(drawdown),
    )


def proposal(
    *,
    symbol: str = "NVDA",
    weight: str = "0.10",
    research_as_of: datetime = DECISION_TIME - timedelta(hours=1),
    earnings_at: datetime | None = None,
    proposal_id: int = 1,
) -> TargetWeightProposal:
    return TargetWeightProposal(
        id=UUID(int=proposal_id),
        research_decision_id=UUID(int=100 + proposal_id),
        symbol=Symbol(symbol),
        opinion=ResearchOpinionValue.BULLISH,
        proposed_weight=Decimal(weight),
        rationale="fixture proposal",
        research_as_of=research_as_of,
        earnings_at=earnings_at,
    )


def test_gateway_approves_valid_target_and_clips_position_limit() -> None:
    gateway = RiskGateway(policy())

    approved = gateway.evaluate((proposal(weight="0.10"),), snapshot(), DECISION_TIME)[0]
    clipped = gateway.evaluate((proposal(weight="0.50"),), snapshot(), DECISION_TIME)[0]

    assert approved.status is RiskDecisionStatus.APPROVED
    assert approved.approved_weight == Decimal("0.10")
    assert approved.reason_codes == ()
    assert clipped.status is RiskDecisionStatus.CLIPPED
    assert clipped.approved_weight == Decimal("0.20")
    assert clipped.reason_codes == (RiskReason.POSITION_LIMIT,)
    assert clipped.risk_policy_version_id == POLICY_ID


def test_order_intent_requires_deterministic_risk_decision_reference() -> None:
    with pytest.raises(ValueError, match="risk decision"):
        OrderIntent(
            id=UUID(int=500),
            portfolio_id=UUID(int=501),
            symbol=Symbol("NVDA"),
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            decision_time=DECISION_TIME,
            execution_policy_version_id=UUID(int=502),
            risk_approved=True,
        )


@pytest.mark.parametrize(
    ("risk_snapshot", "target", "expected_weight", "reason"),
    (
        (
            snapshot(
                cash_weight="0.10",
            ),
            proposal(weight="0.20"),
            Decimal("0.05"),
            RiskReason.CASH_RESERVE,
        ),
        (
            snapshot(
                cash_weight="0.10",
                current_weights={Symbol("AAPL"): Decimal("0.90")},
            ),
            proposal(weight="0.20"),
            Decimal("0.10"),
            RiskReason.GROSS_EXPOSURE,
        ),
        (
            snapshot(turnover="0.20"),
            proposal(weight="0.20"),
            Decimal("0.05"),
            RiskReason.DAILY_TURNOVER,
        ),
    ),
)
def test_gateway_clips_cash_exposure_and_turnover_limits(
    risk_snapshot: PortfolioRiskSnapshot,
    target: TargetWeightProposal,
    expected_weight: Decimal,
    reason: RiskReason,
) -> None:
    limits = policy()
    if reason is RiskReason.GROSS_EXPOSURE:
        limits = replace(limits, min_cash_reserve=Decimal("0"))

    decision = RiskGateway(limits).evaluate((target,), risk_snapshot, DECISION_TIME)[0]

    assert decision.status is RiskDecisionStatus.CLIPPED
    assert decision.approved_weight == expected_weight
    assert reason in decision.reason_codes


def test_gateway_reserves_cash_across_multiple_accepted_targets() -> None:
    decisions = RiskGateway(replace(policy(), max_daily_turnover=Decimal("1"))).evaluate(
        (
            proposal(symbol="NVDA", weight="0.20", proposal_id=1),
            proposal(symbol="MSFT", weight="0.20", proposal_id=2),
        ),
        snapshot(
            cash_weight="0.30",
            current_weights={Symbol("AAPL"): Decimal("0.70")},
            prices={
                Symbol("AAPL"): Decimal("100"),
                Symbol("MSFT"): Decimal("100"),
                Symbol("NVDA"): Decimal("100"),
            },
        ),
        DECISION_TIME,
    )

    by_symbol = {decision.symbol: decision for decision in decisions}
    assert by_symbol[Symbol("MSFT")].approved_weight == Decimal("0.20")
    assert by_symbol[Symbol("NVDA")].approved_weight == Decimal("0.05")
    assert RiskReason.CASH_RESERVE in by_symbol[Symbol("NVDA")].reason_codes
    assert sum((decision.approved_weight for decision in decisions), Decimal("0")) == Decimal(
        "0.25"
    )


def test_gateway_is_deterministic_for_reordered_proposal_sets() -> None:
    proposals = (
        proposal(symbol="NVDA", weight="0.10", proposal_id=1),
        proposal(symbol="AAPL", weight="0.10", proposal_id=2),
    )
    constrained = snapshot(
        turnover="0.15",
        prices={Symbol("AAPL"): Decimal("100"), Symbol("NVDA"): Decimal("100")},
    )

    first = RiskGateway(policy()).evaluate(proposals, constrained, DECISION_TIME)
    second = RiskGateway(policy()).evaluate(tuple(reversed(proposals)), constrained, DECISION_TIME)

    assert first == second


@pytest.mark.parametrize(
    "invalid",
    (
        RiskDecision(
            id=UUID(int=900),
            proposal_id=UUID(int=901),
            research_decision_id=UUID(int=902),
            symbol=Symbol("NVDA"),
            status=RiskDecisionStatus.APPROVED,
            requested_weight=Decimal("0.10"),
            approved_weight=Decimal("0.10"),
            reason_codes=(),
            risk_policy_version_id=POLICY_ID,
            decided_at=DECISION_TIME,
            current_weight=Decimal("0"),
            approved_delta=Decimal("0.10"),
            reference_nav=Decimal("1000"),
            reference_price=Decimal("100"),
            max_order_quantity=Decimal("1"),
            market_context_snapshot_id=MARKET_CONTEXT_ID,
            portfolio_id=UUID(int=700),
        ),
    ),
)
def test_risk_decision_rejects_naive_time_and_inconsistent_status(
    invalid: RiskDecision,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(invalid, decided_at=DECISION_TIME.replace(tzinfo=None))
    with pytest.raises(ValueError, match="approved delta|approved decision"):
        replace(invalid, approved_weight=Decimal("0.05"))
    with pytest.raises(ValueError, match="approved delta|rejected decision"):
        replace(
            invalid,
            status=RiskDecisionStatus.REJECTED,
            approved_weight=Decimal("0.01"),
            reason_codes=(RiskReason.DRAWDOWN_LIMIT,),
        )


@pytest.mark.parametrize(
    ("targets", "risk_snapshot", "reason"),
    (
        (
            (proposal(research_as_of=DECISION_TIME - timedelta(days=3)),),
            snapshot(),
            RiskReason.STALE_RESEARCH,
        ),
        (
            (proposal(),),
            snapshot(prices={Symbol("AAPL"): Decimal("100")}),
            RiskReason.MISSING_PRICE,
        ),
        (
            (proposal(earnings_at=DECISION_TIME + timedelta(hours=12)),),
            snapshot(),
            RiskReason.EARNINGS_BLACKOUT,
        ),
        (
            (proposal(),),
            snapshot(drawdown="-0.25"),
            RiskReason.DRAWDOWN_LIMIT,
        ),
        (
            (proposal(), proposal(proposal_id=2)),
            snapshot(),
            RiskReason.DUPLICATE_INTENT,
        ),
    ),
)
def test_gateway_rejects_invalid_or_duplicated_proposals(
    targets: tuple[TargetWeightProposal, ...],
    risk_snapshot: PortfolioRiskSnapshot,
    reason: RiskReason,
) -> None:
    decisions = RiskGateway(policy()).evaluate(targets, risk_snapshot, DECISION_TIME)

    assert all(decision.status is RiskDecisionStatus.REJECTED for decision in decisions)
    assert all(reason in decision.reason_codes for decision in decisions)
    assert all(decision.approved_weight == Decimal("0") for decision in decisions)


def test_opinion_and_portfolio_action_are_separate_and_regime_is_deterministic() -> None:
    assert (
        opinion_to_action(ResearchOpinionValue.BULLISH, current_weight=Decimal("0"))
        is PortfolioActionValue.ENTER
    )
    assert (
        opinion_to_action(ResearchOpinionValue.BULLISH, current_weight=Decimal("0.1"))
        is PortfolioActionValue.ADD
    )
    assert (
        opinion_to_action(ResearchOpinionValue.BEARISH, current_weight=Decimal("0.1"))
        is PortfolioActionValue.EXIT
    )
    assert (
        opinion_to_action(ResearchOpinionValue.ABSTAIN, current_weight=Decimal("0.1"))
        is PortfolioActionValue.NO_ACTION
    )
    assert not issubclass(PortfolioActionValue, ResearchOpinionValue)

    risk_on = classify_market_regime(
        snapshot_id=UUID(int=10),
        as_of=DECISION_TIME,
        available_at=DECISION_TIME,
        qqq_trend=Decimal("0.05"),
        qqq_volatility=Decimal("0.18"),
        soxx_relative_strength=Decimal("0.02"),
        vix=Decimal("18"),
        algorithm_version="regime-v1",
        source_lineage=(UUID(int=1), UUID(int=2), UUID(int=3)),
    )
    risk_off = classify_market_regime(
        snapshot_id=UUID(int=11),
        as_of=DECISION_TIME,
        available_at=DECISION_TIME,
        qqq_trend=Decimal("-0.05"),
        qqq_volatility=Decimal("0.35"),
        soxx_relative_strength=Decimal("-0.03"),
        vix=Decimal("30"),
        algorithm_version="regime-v1",
        source_lineage=(UUID(int=1), UUID(int=2), UUID(int=3)),
    )

    assert risk_on.regime is MarketRegime.RISK_ON
    assert risk_off.regime is MarketRegime.RISK_OFF
    assert risk_on.source_lineage == (UUID(int=1), UUID(int=2), UUID(int=3))
