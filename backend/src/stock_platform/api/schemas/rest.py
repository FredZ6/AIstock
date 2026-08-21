from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
