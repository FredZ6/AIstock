"""Deterministic recovery decisions for transient operational failures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from stock_platform.domain.common.time import require_aware


class RecoveryDecision(StrEnum):
    NO_ACTION = "NO_ACTION"
    REQUEUE = "REQUEUE"
    FAIL = "FAIL"


def recover_expired_run(
    *,
    status: str,
    lease_expires_at: datetime | None,
    attempt_count: int,
    max_attempts: int,
    now: datetime,
) -> RecoveryDecision:
    current = require_aware(now)
    if status != "RUNNING" or lease_expires_at is None:
        return RecoveryDecision.NO_ACTION
    expires = require_aware(lease_expires_at)
    if expires >= current:
        return RecoveryDecision.NO_ACTION
    if attempt_count >= max_attempts:
        return RecoveryDecision.FAIL
    return RecoveryDecision.REQUEUE


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int
    recovery_timeout: timedelta
    _failures: int = 0
    _opened_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.failure_threshold < 1 or self.recovery_timeout <= timedelta(0):
            raise ValueError("circuit breaker bounds must be positive")

    def record_failure(self, *, at: datetime) -> None:
        observed_at = require_aware(at)
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = observed_at

    def allow_request(self, *, at: datetime) -> bool:
        observed_at = require_aware(at)
        if self._opened_at is None:
            return True
        return observed_at >= self._opened_at + self.recovery_timeout

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
