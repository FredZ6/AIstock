"""Deterministic weekly-review maturity gates."""

from datetime import datetime, timedelta

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.learning.outcome import DecisionForReview, Horizon


def matured_horizons(decision: DecisionForReview, *, as_of: datetime) -> tuple[Horizon, ...]:
    cutoff = require_aware(as_of)
    return tuple(
        horizon
        for horizon in Horizon
        if decision.decision_time + timedelta(days=int(horizon)) <= cutoff
    )
