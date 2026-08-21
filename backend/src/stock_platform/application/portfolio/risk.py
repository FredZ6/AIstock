from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid5

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.research.claims import ResearchOpinionValue

ZERO = Decimal("0")
_RISK_NAMESPACE = UUID("6faf8c03-4a69-4772-bb06-b23b6766f40d")


class RiskDecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    CLIPPED = "CLIPPED"
    REJECTED = "REJECTED"


class RiskReason(StrEnum):
    POSITION_LIMIT = "POSITION_LIMIT"
    GROSS_EXPOSURE = "GROSS_EXPOSURE"
    CASH_RESERVE = "CASH_RESERVE"
    DAILY_TURNOVER = "DAILY_TURNOVER"
    STALE_RESEARCH = "STALE_RESEARCH"
    MISSING_PRICE = "MISSING_PRICE"
    EARNINGS_BLACKOUT = "EARNINGS_BLACKOUT"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    DUPLICATE_INTENT = "DUPLICATE_INTENT"
    INCOMPLETE_EVIDENCE = "INCOMPLETE_EVIDENCE"


def _decimal(name: str, value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must use Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    id: UUID
    version: str
    max_position_weight: Decimal
    max_gross_exposure: Decimal
    min_cash_reserve: Decimal
    max_daily_turnover: Decimal
    max_drawdown: Decimal
    max_research_age: timedelta
    earnings_blackout: timedelta

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("risk policy version is required")
        for name in (
            "max_position_weight",
            "max_gross_exposure",
            "min_cash_reserve",
            "max_daily_turnover",
            "max_drawdown",
        ):
            value = _decimal(name, getattr(self, name))
            if value < ZERO:
                raise ValueError(f"{name} must be non-negative")
        if self.max_position_weight > self.max_gross_exposure:
            raise ValueError("position limit cannot exceed gross exposure limit")
        if self.max_gross_exposure > Decimal("1"):
            raise ValueError("long-only gross exposure cannot exceed one")
        if self.min_cash_reserve > Decimal("1") or self.max_daily_turnover > Decimal("1"):
            raise ValueError("cash reserve and daily turnover cannot exceed one")
        if self.max_research_age <= timedelta(0):
            raise ValueError("max research age must be positive")
        if self.earnings_blackout < timedelta(0):
            raise ValueError("earnings blackout cannot be negative")


@dataclass(frozen=True, slots=True)
class TargetWeightProposal:
    id: UUID
    research_decision_id: UUID
    symbol: Symbol
    opinion: ResearchOpinionValue
    proposed_weight: Decimal
    rationale: str
    research_as_of: datetime
    earnings_at: datetime | None = None
    evidence_complete: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "opinion", ResearchOpinionValue(self.opinion))
        weight = _decimal("proposed_weight", self.proposed_weight)
        if weight < ZERO:
            raise ValueError("proposed weight must be non-negative")
        if not self.rationale.strip():
            raise ValueError("proposal rationale is required")
        object.__setattr__(
            self, "research_as_of", require_aware(self.research_as_of).astimezone(UTC)
        )
        if self.earnings_at is not None:
            object.__setattr__(
                self,
                "earnings_at",
                require_aware(self.earnings_at).astimezone(UTC),
            )


@dataclass(frozen=True, slots=True)
class PortfolioRiskSnapshot:
    portfolio_id: UUID
    market_context_snapshot_id: UUID
    nav: Decimal
    cash_weight: Decimal
    current_weights: Mapping[Symbol, Decimal]
    prices: Mapping[Symbol, Decimal]
    daily_turnover: Decimal
    drawdown: Decimal

    def __post_init__(self) -> None:
        nav = _decimal("nav", self.nav)
        if nav <= ZERO:
            raise ValueError("NAV must be positive")
        cash = _decimal("cash_weight", self.cash_weight)
        turnover = _decimal("daily_turnover", self.daily_turnover)
        drawdown = _decimal("drawdown", self.drawdown)
        if cash < ZERO or turnover < ZERO:
            raise ValueError("cash weight and turnover must be non-negative")
        if cash > Decimal("1"):
            raise ValueError("cash weight cannot exceed one")
        if drawdown > ZERO:
            raise ValueError("drawdown cannot be positive")
        for collection_name, values in (
            ("current_weights", self.current_weights),
            ("prices", self.prices),
        ):
            for symbol, value in values.items():
                Symbol(str(symbol))
                checked = _decimal(collection_name, value)
                if checked < ZERO or (collection_name == "prices" and checked == ZERO):
                    raise ValueError(f"{collection_name} values must be positive")
        if sum(self.current_weights.values(), ZERO) > Decimal("1"):
            raise ValueError("current gross weight cannot exceed one")


@dataclass(frozen=True, slots=True)
class RiskDecision:
    id: UUID
    proposal_id: UUID
    research_decision_id: UUID | None
    symbol: Symbol
    status: RiskDecisionStatus
    requested_weight: Decimal
    approved_weight: Decimal
    reason_codes: tuple[RiskReason, ...]
    risk_policy_version_id: UUID
    decided_at: datetime
    current_weight: Decimal
    approved_delta: Decimal
    reference_nav: Decimal | None
    reference_price: Decimal | None
    max_order_quantity: Decimal
    market_context_snapshot_id: UUID
    portfolio_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", Symbol(str(self.symbol)))
        object.__setattr__(self, "status", RiskDecisionStatus(self.status))
        requested = _decimal("requested_weight", self.requested_weight)
        approved = _decimal("approved_weight", self.approved_weight)
        current = _decimal("current_weight", self.current_weight)
        delta = _decimal("approved_delta", self.approved_delta)
        maximum = _decimal("max_order_quantity", self.max_order_quantity)
        reference_nav = (
            _decimal("reference_nav", self.reference_nav)
            if self.reference_nav is not None
            else None
        )
        reference_price = (
            _decimal("reference_price", self.reference_price)
            if self.reference_price is not None
            else None
        )
        if requested < ZERO or approved < ZERO or current < ZERO or maximum < ZERO:
            raise ValueError("risk decision weights must be non-negative")
        if reference_nav is not None and reference_nav <= ZERO:
            raise ValueError("reference NAV must be positive")
        if reference_price is not None and reference_price <= ZERO:
            raise ValueError("reference price must be positive")
        if delta != approved - current:
            raise ValueError("approved delta must match current and approved weights")
        reasons = tuple(RiskReason(reason) for reason in self.reason_codes)
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(
            self,
            "decided_at",
            require_aware(self.decided_at).astimezone(UTC),
        )
        if self.status is RiskDecisionStatus.APPROVED and (approved != requested or reasons):
            raise ValueError("approved decision must preserve weight without reason codes")
        if self.status is RiskDecisionStatus.CLIPPED and (approved == requested or not reasons):
            raise ValueError("clipped decision must change weight and record a reason")
        if self.status is RiskDecisionStatus.REJECTED and (approved != ZERO or not reasons):
            raise ValueError("rejected decision must have zero weight and record a reason")
        if self.status is RiskDecisionStatus.REJECTED:
            if maximum != ZERO:
                raise ValueError("rejected decision cannot authorize order quantity")
        elif delta == ZERO:
            if maximum != ZERO:
                raise ValueError("unchanged target cannot authorize order quantity")
        elif reference_nav is None or reference_price is None:
            raise ValueError("approved order requires reference NAV and price")
        elif maximum != abs(delta) * reference_nav / reference_price:
            raise ValueError("maximum order quantity must match approved economics")

    @property
    def approved(self) -> bool:
        return self.status is not RiskDecisionStatus.REJECTED


class RiskGateway:
    def __init__(self, policy: RiskPolicy) -> None:
        self.policy = policy

    def _decision(
        self,
        proposal: TargetWeightProposal,
        *,
        status: RiskDecisionStatus,
        approved_weight: Decimal,
        reasons: Sequence[RiskReason],
        decision_time: datetime,
        current_weight: Decimal,
        snapshot: PortfolioRiskSnapshot,
    ) -> RiskDecision:
        reason_codes = tuple(dict.fromkeys(reasons))
        identity = "|".join(
            (
                str(proposal.id),
                str(self.policy.id),
                decision_time.isoformat(),
                status.value,
                str(approved_weight),
                str(current_weight),
                str(snapshot.nav),
                str(snapshot.prices.get(proposal.symbol)),
                str(snapshot.market_context_snapshot_id),
                str(snapshot.portfolio_id),
                ",".join(reason.value for reason in reason_codes),
            )
        )
        reference_price = snapshot.prices.get(proposal.symbol)
        approved_delta = approved_weight - current_weight
        maximum = (
            abs(approved_delta) * snapshot.nav / reference_price
            if reference_price is not None
            and approved_delta != ZERO
            and status is not RiskDecisionStatus.REJECTED
            else ZERO
        )
        return RiskDecision(
            id=uuid5(_RISK_NAMESPACE, identity),
            proposal_id=proposal.id,
            research_decision_id=proposal.research_decision_id,
            symbol=proposal.symbol,
            status=status,
            requested_weight=proposal.proposed_weight,
            approved_weight=approved_weight,
            reason_codes=reason_codes,
            risk_policy_version_id=self.policy.id,
            decided_at=decision_time,
            current_weight=current_weight,
            approved_delta=approved_delta,
            reference_nav=snapshot.nav if reference_price is not None else None,
            reference_price=reference_price,
            max_order_quantity=maximum,
            market_context_snapshot_id=snapshot.market_context_snapshot_id,
            portfolio_id=snapshot.portfolio_id,
        )

    def evaluate(
        self,
        proposals: Sequence[TargetWeightProposal],
        snapshot: PortfolioRiskSnapshot,
        decision_time: datetime,
    ) -> tuple[RiskDecision, ...]:
        cutoff = require_aware(decision_time).astimezone(UTC)
        symbol_counts = Counter(proposal.symbol for proposal in proposals)
        current_gross = sum(snapshot.current_weights.values(), ZERO)
        remaining_cash = snapshot.cash_weight
        remaining_turnover = max(
            ZERO,
            self.policy.max_daily_turnover - snapshot.daily_turnover,
        )
        decisions: list[RiskDecision] = []
        for proposal in sorted(proposals, key=lambda item: (str(item.symbol), str(item.id))):
            current = snapshot.current_weights.get(proposal.symbol, ZERO)
            hard_reasons: list[RiskReason] = []
            if symbol_counts[proposal.symbol] > 1:
                hard_reasons.append(RiskReason.DUPLICATE_INTENT)
            if proposal.symbol not in snapshot.prices:
                hard_reasons.append(RiskReason.MISSING_PRICE)
            if cutoff < proposal.research_as_of or (
                cutoff - proposal.research_as_of > self.policy.max_research_age
            ):
                hard_reasons.append(RiskReason.STALE_RESEARCH)
            if (
                proposal.earnings_at is not None
                and abs(proposal.earnings_at - cutoff) <= self.policy.earnings_blackout
            ):
                hard_reasons.append(RiskReason.EARNINGS_BLACKOUT)
            if not proposal.evidence_complete:
                hard_reasons.append(RiskReason.INCOMPLETE_EVIDENCE)
            if (
                snapshot.drawdown <= -self.policy.max_drawdown
                and proposal.proposed_weight > current
            ):
                hard_reasons.append(RiskReason.DRAWDOWN_LIMIT)
            if hard_reasons:
                decisions.append(
                    self._decision(
                        proposal,
                        status=RiskDecisionStatus.REJECTED,
                        approved_weight=ZERO,
                        reasons=hard_reasons,
                        decision_time=cutoff,
                        current_weight=current,
                        snapshot=snapshot,
                    )
                )
                continue

            approved = proposal.proposed_weight
            reasons: list[RiskReason] = []
            if approved > current:
                limits = (
                    (self.policy.max_position_weight, RiskReason.POSITION_LIMIT),
                    (
                        current + max(ZERO, self.policy.max_gross_exposure - current_gross),
                        RiskReason.GROSS_EXPOSURE,
                    ),
                    (
                        current + max(ZERO, remaining_cash - self.policy.min_cash_reserve),
                        RiskReason.CASH_RESERVE,
                    ),
                    (current + remaining_turnover, RiskReason.DAILY_TURNOVER),
                )
                for limit, reason in limits:
                    if approved > limit:
                        approved = limit
                        reasons.append(reason)
            elif approved < current:
                minimum = max(ZERO, current - remaining_turnover)
                if approved < minimum:
                    approved = minimum
                    reasons.append(RiskReason.DAILY_TURNOVER)

            if approved == current and proposal.proposed_weight != current:
                decisions.append(
                    self._decision(
                        proposal,
                        status=RiskDecisionStatus.REJECTED,
                        approved_weight=ZERO,
                        reasons=reasons or (RiskReason.DAILY_TURNOVER,),
                        decision_time=cutoff,
                        current_weight=current,
                        snapshot=snapshot,
                    )
                )
                continue
            status = (
                RiskDecisionStatus.APPROVED
                if approved == proposal.proposed_weight
                else RiskDecisionStatus.CLIPPED
            )
            decisions.append(
                self._decision(
                    proposal,
                    status=status,
                    approved_weight=approved,
                    reasons=reasons,
                    decision_time=cutoff,
                    current_weight=current,
                    snapshot=snapshot,
                )
            )
            remaining_turnover = max(ZERO, remaining_turnover - abs(approved - current))
            remaining_cash -= approved - current
            current_gross += approved - current
        return tuple(decisions)
