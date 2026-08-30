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
    fmp: ProviderState


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
    def valid_cutoff(self) -> "ResearchRunRequest":
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
    def valid_cutoff(self) -> "PortfolioRunRequest":
        if self.data_cutoff > self.decision_time:
            raise ValueError("data_cutoff cannot be after decision_time")
        return self


class RunResponse(BaseModel):
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
