from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid5

from stock_platform.agents.portfolio.state import (
    PortfolioAction,
    PortfolioState,
)
from stock_platform.application.portfolio.accounting import apply_fill
from stock_platform.application.portfolio.allocation import opinion_to_action
from stock_platform.application.portfolio.benchmarks import benchmark_returns
from stock_platform.application.portfolio.execution import ExecutionPolicy, PaperExecutionSimulator
from stock_platform.application.portfolio.risk import (
    PortfolioRiskSnapshot,
    RiskGateway,
    RiskPolicy,
    TargetWeightProposal,
)
from stock_platform.application.portfolio.valuation import visible_bar_prices
from stock_platform.domain.portfolio.nav import rebuild_nav
from stock_platform.domain.portfolio.order import OrderIntent, OrderSide
from stock_platform.domain.research.claims import ResearchOpinionValue

ZERO = Decimal("0")
_PORTFOLIO_NAMESPACE = UUID("28db7f72-50e2-4d11-a731-b049879320a5")


class PortfolioNodes:
    def __init__(self, *, risk_policy: RiskPolicy, execution_policy: ExecutionPolicy) -> None:
        self._risk_gateway = RiskGateway(risk_policy)
        self._execution = PaperExecutionSimulator(execution_policy)
        self._execution_policy = execution_policy

    def load_frozen_research(self, state: PortfolioState) -> dict[str, object]:
        specification = state["specification"]
        visible = tuple(
            item
            for item in state["research"]
            if item.as_of <= specification.decision_time
            and item.available_at <= specification.data_cutoff
        )
        return {"route": ("load_frozen_research",), "frozen_research": visible}

    def generate_candidates(self, state: PortfolioState) -> dict[str, object]:
        candidates = tuple(
            item
            for item in state["frozen_research"]
            if item.opinion is not ResearchOpinionValue.ABSTAIN
        )
        return {"route": ("generate_candidates",), "candidates": candidates}

    def build_target_weights(self, state: PortfolioState) -> dict[str, object]:
        proposals: list[TargetWeightProposal] = []
        actions: list[PortfolioAction] = []
        for item in state["candidates"]:
            current = state["current_weights"].get(item.symbol, ZERO)
            action = opinion_to_action(item.opinion, current_weight=current)
            target_weight = (
                ZERO
                if item.opinion is ResearchOpinionValue.BEARISH
                else current
                if item.opinion is ResearchOpinionValue.NEUTRAL
                else item.proposed_weight
            )
            proposal_id = uuid5(
                _PORTFOLIO_NAMESPACE,
                f"{state['run_id']}|{item.decision_id}|{target_weight}",
            )
            proposals.append(
                TargetWeightProposal(
                    id=proposal_id,
                    research_decision_id=item.decision_id,
                    symbol=item.symbol,
                    opinion=item.opinion,
                    proposed_weight=target_weight,
                    rationale=item.rationale,
                    research_as_of=item.as_of,
                    earnings_at=item.earnings_at,
                    evidence_complete=item.evidence_complete,
                )
            )
            actions.append(
                PortfolioAction(
                    research_decision_id=item.decision_id,
                    symbol=item.symbol,
                    value=action,
                    target_weight=target_weight,
                )
            )
        return {
            "route": ("build_target_weights",),
            "proposals": tuple(proposals),
            "actions": tuple(actions),
        }

    def risk_gateway(self, state: PortfolioState) -> dict[str, object]:
        nav = state["decision_nav"]
        cash_weight = nav.cash / nav.total
        snapshot = PortfolioRiskSnapshot(
            portfolio_id=state["portfolio_id"],
            market_context_snapshot_id=state["market_context"].id,
            nav=nav.total,
            cash_weight=cash_weight,
            current_weights=state["current_weights"],
            prices=state["prices"],
            daily_turnover=state["daily_turnover"],
            drawdown=state["drawdown"],
        )
        decisions = self._risk_gateway.evaluate(
            state["proposals"],
            snapshot,
            state["specification"].decision_time,
        )
        return {"route": ("risk_gateway",), "risk_decisions": decisions}

    def create_pending_orders(self, state: PortfolioState) -> dict[str, object]:
        orders: list[OrderIntent] = []
        for decision in state["risk_decisions"]:
            if not decision.approved:
                continue
            current = state["current_weights"].get(decision.symbol, ZERO)
            delta = decision.approved_weight - current
            if delta == ZERO:
                continue
            quantity = decision.max_order_quantity
            order_id = uuid5(
                _PORTFOLIO_NAMESPACE,
                f"{state['run_id']}|{decision.id}|order",
            )
            orders.append(
                OrderIntent(
                    id=order_id,
                    portfolio_id=state["portfolio_id"],
                    symbol=decision.symbol,
                    side=OrderSide.BUY if delta > ZERO else OrderSide.SELL,
                    quantity=quantity,
                    decision_time=state["specification"].decision_time,
                    execution_policy_version_id=self._execution_policy.id,
                    risk_approved=True,
                    risk_decision_id=decision.id,
                )
            )
        return {"route": ("create_pending_orders",), "order_intents": tuple(orders)}

    def next_eligible_bar_fill(self, state: PortfolioState) -> dict[str, object]:
        fills = tuple(
            fill
            for order in state["order_intents"]
            for fill in self._execution.execute(
                order,
                state["bars"],
                risk_decision=next(
                    decision
                    for decision in state["risk_decisions"]
                    if decision.id == order.risk_decision_id
                ),
                prior_fills=tuple(
                    prior for prior in state["prior_fills"] if prior.order_id == order.id
                ),
            )
        )
        return {"route": ("next_eligible_bar_fill",), "fills": fills}

    def update_ledger_nav(self, state: PortfolioState) -> dict[str, object]:
        ledger = state["ledger"]
        for fill in state["fills"]:
            ledger = apply_fill(ledger, fill)
        all_fills = tuple(state["prior_fills"]) + tuple(state["fills"])
        nav_time = max(
            (fill.filled_at for fill in state["fills"]),
            default=state["specification"].decision_time,
        )
        mark_prices = visible_bar_prices(
            state["bars"],
            event_cutoff=nav_time,
            available_cutoff=nav_time,
        )
        nav = rebuild_nav(
            ledger,
            all_fills,
            prices=mark_prices,
            as_of=nav_time,
        )
        benchmarks = benchmark_returns(
            state["benchmark_frames"],
            watchlist=state["benchmark_watchlist"],
            momentum_lookback=1,
            cost_bps=self._execution_policy.spread_bps / Decimal("2")
            + self._execution_policy.slippage_bps,
            initial_nav=state["decision_nav"].total,
            fee_per_share=self._execution_policy.fee_per_share,
            minimum_fee=self._execution_policy.minimum_fee,
        )
        return {
            "route": ("update_ledger_nav",),
            "ledger": ledger,
            "nav": nav,
            "benchmarks": benchmarks,
        }
