from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC
from decimal import Decimal
from itertools import pairwise
from typing import cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from stock_platform.agents.harness.task_spec import TaskSpecification
from stock_platform.agents.portfolio.nodes import PortfolioNodes
from stock_platform.agents.portfolio.state import (
    FrozenResearchDecision,
    PortfolioResult,
    PortfolioState,
)
from stock_platform.application.portfolio.allocation import MarketContextSnapshot
from stock_platform.application.portfolio.benchmarks import BenchmarkReturns, PriceFrame
from stock_platform.application.portfolio.execution import ExecutionPolicy
from stock_platform.application.portfolio.risk import RiskPolicy
from stock_platform.application.portfolio.valuation import visible_bar_prices
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.fill import ExecutionBar, PaperFill
from stock_platform.domain.portfolio.ledger import LedgerEntry
from stock_platform.domain.portfolio.nav import rebuild_nav
from stock_platform.domain.portfolio.position import rebuild_positions


class PortfolioDecisionGraph:
    node_names = (
        "load_frozen_research",
        "generate_candidates",
        "build_target_weights",
        "risk_gateway",
        "create_pending_orders",
        "next_eligible_bar_fill",
        "update_ledger_nav",
    )

    def __init__(self, *, risk_policy: RiskPolicy, execution_policy: ExecutionPolicy) -> None:
        self._risk_policy = risk_policy
        self._execution_policy = execution_policy
        nodes = PortfolioNodes(risk_policy=risk_policy, execution_policy=execution_policy)
        builder = StateGraph(PortfolioState)
        for name in self.node_names:
            builder.add_node(name, getattr(nodes, name))
        builder.add_edge(START, self.node_names[0])
        for current, following in pairwise(self.node_names):
            builder.add_edge(current, following)
        builder.add_edge(self.node_names[-1], END)
        self._compiled = builder.compile()

    def run(
        self,
        *,
        run_id: str,
        portfolio_id: UUID,
        specification: TaskSpecification,
        research: Sequence[FrozenResearchDecision],
        market_context: MarketContextSnapshot,
        bars: Sequence[ExecutionBar],
        ledger: Sequence[LedgerEntry],
        prior_fills: Sequence[PaperFill] = (),
        benchmark_frames: Sequence[PriceFrame] = (),
        benchmark_watchlist: Sequence[Symbol] = (),
        drawdown: Decimal = Decimal("0"),
    ) -> PortfolioResult:
        if specification.allowed_tools or specification.budgets.tool_calls != 0:
            raise ValueError("portfolio graph forbids external tools")
        if specification.budgets.llm_calls > 3:
            raise ValueError("portfolio graph allows at most three LLM calls")
        if specification.budgets.wall_time.total_seconds() > 60:
            raise ValueError("portfolio graph wall time cannot exceed 60 seconds")
        if specification.policy_versions.risk != self._risk_policy.version:
            raise ValueError("risk policy version does not match task specification")
        if specification.policy_versions.execution != self._execution_policy.version:
            raise ValueError("execution policy version does not match task specification")
        if market_context.as_of > specification.decision_time:
            raise ValueError("market context cannot be after decision time")
        if market_context.available_at > specification.data_cutoff:
            raise ValueError("market context was unavailable at the data cutoff")
        for item in research:
            if item.policy_versions != specification.policy_versions:
                raise ValueError("frozen research policy pins do not match task specification")
            if item.data_cutoff != specification.data_cutoff:
                raise ValueError("frozen research data cutoff does not match task specification")
        if not isinstance(drawdown, Decimal):
            raise TypeError("drawdown must use Decimal")
        if any(item.portfolio_id != portfolio_id for item in ledger):
            raise ValueError("ledger does not belong to the requested portfolio")
        if any(item.portfolio_id != portfolio_id for item in prior_fills):
            raise ValueError("prior fills do not belong to the requested portfolio")
        decision_prices = visible_bar_prices(
            bars,
            event_cutoff=specification.decision_time,
            available_cutoff=specification.data_cutoff,
        )
        try:
            decision_nav = rebuild_nav(
                ledger,
                prior_fills,
                prices=decision_prices,
                as_of=specification.decision_time,
            )
        except KeyError as error:
            raise ValueError("current position lacks a point-in-time valuation bar") from error
        if decision_nav.total <= 0:
            raise ValueError("portfolio NAV must be positive")
        positions = rebuild_positions(prior_fills, as_of=specification.decision_time)
        current_weights = {
            symbol: position.quantity * decision_prices[symbol] / decision_nav.total
            for symbol, position in positions.items()
        }
        daily_turnover = sum(
            (
                fill.quantity * fill.price / decision_nav.total
                for fill in prior_fills
                if fill.filled_at.date() == specification.decision_time.astimezone(UTC).date()
                and fill.filled_at <= specification.decision_time
            ),
            Decimal("0"),
        )
        watchlist = tuple(benchmark_watchlist) or tuple(
            sorted((item.symbol for item in research), key=str)
        )
        empty_benchmarks = BenchmarkReturns((), (), (), ())
        initial: PortfolioState = {
            "run_id": run_id,
            "portfolio_id": portfolio_id,
            "specification": specification,
            "route": (),
            "research": tuple(research),
            "market_context": market_context,
            "frozen_research": (),
            "candidates": (),
            "proposals": (),
            "actions": (),
            "risk_decisions": (),
            "order_intents": (),
            "bars": tuple(bars),
            "prior_fills": tuple(prior_fills),
            "fills": (),
            "ledger": tuple(ledger),
            "cash": decision_nav.cash,
            "daily_turnover": daily_turnover,
            "drawdown": drawdown,
            "current_weights": current_weights,
            "prices": decision_prices,
            "benchmark_frames": tuple(benchmark_frames),
            "benchmark_watchlist": watchlist,
            "benchmarks": empty_benchmarks,
            "decision_nav": decision_nav,
            "nav": None,
            "external_tool_calls": 0,
        }
        final = cast(PortfolioState, self._compiled.invoke(initial))
        return PortfolioResult.from_state(final)
