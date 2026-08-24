"""Pure ingestion job and lease invariants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    FeedType,
    IngestionJobState,
    IngestionRequest,
    can_transition,
)


class InvalidJobTransition(ValueError):
    """Raised when a persisted job attempts an illegal state transition."""


class StaleIngestionLease(RuntimeError):
    """Raised when work is presented under a superseded or expired lease."""


def transition_job(current: IngestionJobState, target: IngestionJobState) -> IngestionJobState:
    if not can_transition(current, target):
        raise InvalidJobTransition(f"illegal ingestion transition: {current} -> {target}")
    return target


@dataclass(frozen=True, slots=True)
class IngestionJobSpec:
    request: IngestionRequest
    provider: str
    dataset: FeedType
    window_start: datetime
    window_end: datetime
    purpose: DataPurpose
    policy_version: str
    max_attempts: int

    def __post_init__(self) -> None:
        start = require_aware(self.window_start).astimezone(UTC)
        end = require_aware(self.window_end).astimezone(UTC)
        if start > end:
            raise ValueError("ingestion window_start must not exceed window_end")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if not self.provider or not self.policy_version:
            raise ValueError("provider and policy_version are required")
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "window_end", end)


@dataclass(frozen=True, slots=True)
class IngestionLease:
    job_id: UUID
    token: UUID
    generation: int
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.generation < 1:
            raise ValueError("lease generation must be positive")
        object.__setattr__(self, "expires_at", require_aware(self.expires_at).astimezone(UTC))


def require_current_lease(
    *,
    state: IngestionJobState,
    stored_token: UUID | None,
    stored_generation: int,
    stored_expires_at: datetime | None,
    presented: IngestionLease,
    now: datetime,
) -> IngestionLease:
    checked_now = require_aware(now).astimezone(UTC)
    checked_expiry = (
        require_aware(stored_expires_at).astimezone(UTC) if stored_expires_at is not None else None
    )
    if (
        state is not IngestionJobState.RUNNING
        or stored_token != presented.token
        or stored_generation != presented.generation
        or checked_expiry is None
        or checked_expiry <= checked_now
    ):
        raise StaleIngestionLease("ingestion lease is stale, mismatched, or expired")
    return presented
