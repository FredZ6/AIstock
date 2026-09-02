from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


ReadStatus = Literal["SUCCESS", "DEGRADED", "FAILURE"]


class ProviderState(StrictModel):
    configured: bool
    mode: Literal["read_only", "unavailable"]
    status: Literal["SUCCESS", "DEGRADED", "FAILURE", "UNAVAILABLE"] | None = None
    coverage: str | None = None
    latest_job_state: str | None = None
    latest_quality_status: str | None = None


class ProviderStates(StrictModel):
    sec: ProviderState
    alpaca: ProviderState
    alpha_vantage: ProviderState


class ProviderHealthResponse(StrictModel):
    mode: Literal["fixture", "paper", "test"]
    providers: ProviderStates


class MarketDataItem(StrictModel):
    symbol: str
    provider: str
    feed_type: str
    timeframe: Literal["1Min", "1Day"]
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    content_hash: str
    raw_object_key: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    coverage: Literal["IEX", "SIP"]
    session: Literal["PRE_MARKET", "REGULAR", "AFTER_HOURS", "OVERNIGHT"]
    conflict: bool


class MarketDataResponse(StrictModel):
    status: ReadStatus
    decision_time: datetime
    missing_symbols: list[str] = Field(default_factory=list)
    items: list[MarketDataItem]


class DataQualityItem(StrictModel):
    id: UUID
    raw_data_object_id: UUID
    normalized_record_id: UUID
    provider: str
    dataset: str
    dimension: str
    status: Literal["PASS", "DEGRADED", "UNAVAILABLE", "FAIL"]
    observed_at: datetime
    freshness: timedelta | None
    coverage: Literal["IEX", "SIP"] | None
    delay: timedelta | None
    conflict: bool
    policy_version: str
    details: dict[str, Any]
    created_at: datetime


class DataQualityResponse(StrictModel):
    status: ReadStatus
    decision_time: datetime
    items: list[DataQualityItem]


class ResearchRunRequest(StrictModel):
    symbol: str
    decision_time: datetime
    data_cutoff: datetime

    @field_validator("symbol")
    @classmethod
    def valid_symbol(cls, value: str) -> str:
        return str(Symbol(value))

    @field_validator("decision_time", "data_cutoff")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return require_aware(value)

    @model_validator(mode="after")
    def valid_cutoff(self) -> ResearchRunRequest:
        if self.data_cutoff > self.decision_time:
            raise ValueError("data_cutoff cannot be after decision_time")
        return self


class PortfolioRunRequest(StrictModel):
    decision_time: datetime
    data_cutoff: datetime

    @field_validator("decision_time", "data_cutoff")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return require_aware(value)

    @model_validator(mode="after")
    def valid_cutoff(self) -> PortfolioRunRequest:
        if self.data_cutoff > self.decision_time:
            raise ValueError("data_cutoff cannot be after decision_time")
        return self


class PortfolioInitializationRequest(StrictModel):
    effective_at: datetime

    @field_validator("effective_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return require_aware(value)


class PortfolioInitializationResponse(StrictModel):
    status: Literal["READY"]
    portfolio_id: UUID
    name: str
    initial_cash: Decimal
    currency: Literal["USD"]
    initialized_at: datetime


class PortfolioConfiguration(StrictModel):
    id: UUID
    name: str
    initial_cash: Decimal
    currency: Literal["USD"]


class PortfolioCash(StrictModel):
    balance: Decimal
    currency: Literal["USD"]


class PortfolioPositionItem(StrictModel):
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    market_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    price_available_at: datetime | None


class RiskDecisionItem(StrictModel):
    id: UUID
    proposal_id: UUID
    research_decision_id: UUID | None
    portfolio_id: UUID
    symbol: str
    status: Literal["APPROVED", "CLIPPED", "REJECTED"]
    requested_weight: Decimal
    approved_weight: Decimal
    current_weight: Decimal
    approved_delta: Decimal
    reference_nav: Decimal | None
    reference_price: Decimal | None
    max_order_quantity: Decimal
    authorization_source: str
    authorized_side: Literal["BUY", "SELL"] | None
    market_context_snapshot_id: UUID
    reason_codes: list[str]
    risk_policy_version_id: UUID
    decided_at: datetime
    created_at: datetime


class CashLedgerItem(StrictModel):
    id: UUID
    transaction_id: UUID
    source_id: UUID
    account: str
    debit: Decimal
    credit: Decimal
    currency: str
    occurred_at: datetime
    idempotency_key: str
    reversal_of_id: UUID | None
    created_at: datetime


class PortfolioNavItem(StrictModel):
    id: UUID
    event_time: datetime
    portfolio_id: UUID
    nav: Decimal
    available_at: datetime


class PortfolioResponse(StrictModel):
    status: Literal["EMPTY", "SUCCESS"]
    decision_time: datetime
    trading: Literal["paper_only"]
    configuration: PortfolioConfiguration | None
    initialized_at: datetime | None
    cash: PortfolioCash | None
    latest_nav: PortfolioNavItem | None
    positions: list[PortfolioPositionItem]
    risk_decisions: list[RiskDecisionItem]
    orders: list[PaperOrderItem]
    fills: list[PaperFillItem]
    cash_ledger: list[CashLedgerItem]
    performance_history: list[PortfolioNavItem]


class RunResponse(StrictModel):
    run_id: UUID
    run_type: Literal["RESEARCH", "PORTFOLIO"]
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
    symbol: str | None
    decision_time: datetime
    data_cutoff: datetime


class WatchlistRequest(StrictModel):
    symbol: str
    daily_research: bool = True
    intraday_monitoring: bool = True
    thresholds: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def valid_symbol(cls, value: str) -> str:
        return str(Symbol(value))


class WatchlistPatch(StrictModel):
    daily_research: bool | None = None
    intraday_monitoring: bool | None = None
    thresholds: dict[str, Any] | None = None


class HumanAction(StrictModel):
    rationale: Annotated[str, Field(min_length=1)]
    expected_revision: int = Field(default=0, ge=0)


class ResearchItem(StrictModel):
    id: UUID
    run_id: UUID
    symbol: str
    as_of: datetime
    direction: str
    summary: str
    catalysts: list[Any]
    risks: list[Any]
    invalidation_conditions: list[Any]
    horizon: str
    confidence: Decimal
    confidence_policy_version_id: UUID | None
    supersedes_thesis_id: UUID | None
    created_at: datetime
    opinion: Literal["BULLISH", "NEUTRAL", "BEARISH", "ABSTAIN"] | None


class ResearchPage(StrictModel):
    decision_time: datetime
    items: list[ResearchItem]
    next_cursor: str | None


class AlertItem(StrictModel):
    id: UUID
    correlation_id: UUID
    alert_key: str
    symbol: str
    event_time: datetime
    rule_id: str
    rule_version: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    materiality: Decimal
    conditions: list[Any]
    metrics: dict[str, Any]
    data_quality: dict[str, Any]
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    created_at: datetime


class AlertPage(StrictModel):
    decision_time: datetime
    items: list[AlertItem]
    next_cursor: str | None


class PaperOrderItem(StrictModel):
    id: UUID
    order_intent_id: UUID
    portfolio_id: UUID
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    decision_time: datetime
    execution_policy_version_id: UUID
    risk_approved: bool
    status: Literal["REJECTED", "PENDING", "PARTIALLY_FILLED", "FILLED"]
    created_at: datetime


class PaperOrderPage(StrictModel):
    decision_time: datetime
    items: list[PaperOrderItem]
    next_cursor: str | None


class PaperFillItem(StrictModel):
    id: UUID
    order_id: UUID
    portfolio_id: UUID
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    price: Decimal
    fee: Decimal
    currency: str
    filled_at: datetime
    source_bar_time: datetime
    execution_policy_version_id: UUID
    idempotency_key: str
    reversal_of_id: UUID | None
    created_at: datetime


class PaperFillPage(StrictModel):
    decision_time: datetime
    items: list[PaperFillItem]
    next_cursor: str | None


class WeeklyReviewItem(StrictModel):
    id: UUID
    run_key: str
    decision_ids: list[Any]
    decision_time: datetime
    data_cutoff: datetime
    research_scoring_policy_version: str
    risk_policy_version: str
    execution_policy_version: str
    confidence_policy_version: str
    prompt_version: str
    model_version: str
    status: Literal["RUNNING", "COMPLETED", "FAILED"]
    created_at: datetime


class WeeklyReviewPage(StrictModel):
    decision_time: datetime
    items: list[WeeklyReviewItem]
    next_cursor: str | None


class WeeklyOutcomeItem(StrictModel):
    id: UUID
    decision_id: UUID
    symbol: str
    opinion: Literal["BULLISH", "NEUTRAL", "BEARISH", "ABSTAIN"]
    confidence: Decimal
    status: Literal["PENDING", "MATURED"]
    returns: dict[str, Decimal]
    excess_returns: dict[str, Decimal]
    maximum_favorable_excursion: Decimal
    maximum_adverse_excursion: Decimal
    risk_adjusted_return: Decimal
    calibration_error: Decimal
    computed_at: datetime
    created_at: datetime


class WeeklyAttributionItem(StrictModel):
    id: UUID
    outcome_id: UUID
    category: Literal[
        "STALE_DATA",
        "MISSING_EVIDENCE",
        "FACT_ERROR",
        "CONFLICT_IGNORED",
        "THESIS_ERROR",
        "TIMING_ERROR",
        "POSITION_SIZING_ERROR",
        "EXECUTION_ERROR",
        "REGIME_CHANGE",
        "RISK_POLICY_FAILURE",
        "UNCONTROLLABLE_EVENT",
    ]
    rationale: str
    controllable: bool
    created_at: datetime


class WeeklyLessonItem(StrictModel):
    id: UUID
    attribution_id: UUID
    scope: str
    statement: str
    evidence: list[Any]
    counter_evidence: list[Any]
    confidence: Decimal
    replay_delta: Decimal
    creator: str
    status: Literal["CANDIDATE", "APPROVED", "REJECTED"]
    created_at: datetime


class WeeklyApprovalItem(StrictModel):
    id: UUID
    lesson_id: UUID
    actor_id: str
    action: Literal["APPROVE", "REJECT"]
    rationale: str
    created_at: datetime


class WeeklyReplayItem(StrictModel):
    id: UUID
    lesson_id: UUID
    decision_ids: list[UUID]
    baseline_score: Decimal
    candidate_score: Decimal
    delta: Decimal
    data_cutoff: datetime
    created_at: datetime


class WeeklyCalibrationItem(StrictModel):
    decision_id: UUID
    confidence: Decimal
    status: Literal["PENDING", "MATURED"]
    realized_return: Decimal | None
    calibration_error: Decimal


class WeeklyReviewDetail(StrictModel):
    decision_time: datetime
    review: WeeklyReviewItem
    outcomes: list[WeeklyOutcomeItem]
    attributions: list[WeeklyAttributionItem]
    lessons: list[WeeklyLessonItem]
    approvals: list[WeeklyApprovalItem]
    replays: list[WeeklyReplayItem]
    calibration: list[WeeklyCalibrationItem]


class EvalRunItem(StrictModel):
    id: UUID
    status: str
    created_at: datetime


class EvalRunPage(StrictModel):
    decision_time: datetime
    items: list[EvalRunItem]
    next_cursor: str | None
