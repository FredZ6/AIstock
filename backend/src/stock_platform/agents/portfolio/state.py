from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, TypedDict
from uuid import UUID

from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.application.portfolio.allocation import (
    MarketContextSnapshot,
    PortfolioActionValue,
)
from stock_platform.application.portfolio.benchmarks import BenchmarkReturns, PriceFrame
from stock_platform.application.portfolio.risk import RiskDecision, TargetWeightProposal
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.portfolio.fill import ExecutionBar, PaperFill
from stock_platform.domain.portfolio.ledger import LedgerEntry
from stock_platform.domain.portfolio.nav import PortfolioNav
from stock_platform.domain.portfolio.order import OrderIntent
from stock_platform.domain.research.claims import ResearchOpinionValue


def append_only[T](left: tuple[T, ...], right: tuple[T, ...]) -> tuple[T, ...]:
    return tuple(left) + tuple(right)


@dataclass(frozen=True, slots=True)
class FrozenResearchDecision:
    decision_id: UUID
    thesis_id: UUID
    symbol: Symbol
    opinion: ResearchOpinionValue
    as_of: datetime
    available_at: datetime
    evidence_complete: bool
    proposed_weight: Decimal
    rationale: str
    policy_versions: PolicyVersions
    data_cutoff: datetime
    earnings_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "opinion", ResearchOpinionValue(self.opinion))
        object.__setattr__(self, "as_of", require_aware(self.as_of).astimezone(UTC))
        object.__setattr__(self, "available_at", require_aware(self.available_at).astimezone(UTC))
        object.__setattr__(self, "data_cutoff", require_aware(self.data_cutoff).astimezone(UTC))
        if self.earnings_at is not None:
            object.__setattr__(
                self,
                "earnings_at",
                require_aware(self.earnings_at).astimezone(UTC),
            )
        if not isinstance(self.proposed_weight, Decimal):
            raise TypeError("proposed weight must use Decimal")
        if not self.proposed_weight.is_finite() or self.proposed_weight < 0:
            raise ValueError("proposed weight must be finite and non-negative")
        if not self.rationale.strip():
            raise ValueError("portfolio rationale is required")


@dataclass(frozen=True, slots=True)
class PortfolioAction:
    research_decision_id: UUID
    symbol: Symbol
    value: PortfolioActionValue
    target_weight: Decimal


class PortfolioState(TypedDict):
    run_id: str
    portfolio_id: UUID
    specification: TaskSpecification
    route: Annotated[tuple[str, ...], append_only]
    research: tuple[FrozenResearchDecision, ...]
    market_context: MarketContextSnapshot
    frozen_research: tuple[FrozenResearchDecision, ...]
    candidates: tuple[FrozenResearchDecision, ...]
    proposals: tuple[TargetWeightProposal, ...]
    actions: tuple[PortfolioAction, ...]
    risk_decisions: tuple[RiskDecision, ...]
    order_intents: tuple[OrderIntent, ...]
    bars: tuple[ExecutionBar, ...]
    prior_fills: tuple[PaperFill, ...]
    fills: tuple[PaperFill, ...]
    ledger: tuple[LedgerEntry, ...]
    cash: Decimal
    daily_turnover: Decimal
    drawdown: Decimal
    current_weights: Mapping[Symbol, Decimal]
    prices: Mapping[Symbol, Decimal]
    benchmark_frames: tuple[PriceFrame, ...]
    benchmark_watchlist: tuple[Symbol, ...]
    benchmarks: BenchmarkReturns
    decision_nav: PortfolioNav
    nav: PortfolioNav | None
    external_tool_calls: int


@dataclass(frozen=True, slots=True)
class PortfolioResult:
    run_id: str
    market_context: MarketContextSnapshot
    route: tuple[str, ...]
    risk_decisions: tuple[RiskDecision, ...]
    actions: tuple[PortfolioAction, ...]
    order_intents: tuple[OrderIntent, ...]
    fills: tuple[PaperFill, ...]
    ledger: tuple[LedgerEntry, ...]
    nav: PortfolioNav
    benchmarks: BenchmarkReturns
    external_tool_calls: int

    @classmethod
    def from_state(cls, state: PortfolioState) -> PortfolioResult:
        nav = state["nav"]
        if nav is None:
            raise ValueError("portfolio graph completed without NAV")
        return cls(
            run_id=state["run_id"],
            market_context=state["market_context"],
            route=tuple(state["route"]),
            risk_decisions=tuple(state["risk_decisions"]),
            actions=tuple(state["actions"]),
            order_intents=tuple(state["order_intents"]),
            fills=tuple(state["fills"]),
            ledger=tuple(state["ledger"]),
            nav=nav,
            benchmarks=state["benchmarks"],
            external_tool_calls=state["external_tool_calls"],
        )
