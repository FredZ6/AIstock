"""Deterministic, versioned ingestion quality assessments."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import cast

from stock_platform.application.market_data.reconciliation import (
    ReconciliationFinding,
    ReconciliationKind,
)
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import MarketDataCoverage


class QualityDimension(StrEnum):
    FRESHNESS = "FRESHNESS"
    COVERAGE = "COVERAGE"
    PROVIDER = "PROVIDER"
    DELAY = "DELAY"
    CONFLICT = "CONFLICT"
    RECONCILIATION = "RECONCILIATION"
    HEARTBEAT = "HEARTBEAT"


class QualityStatus(StrEnum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    dimension: QualityDimension
    status: QualityStatus
    provider: str
    dataset: str
    observed_at: datetime
    freshness: timedelta | None
    coverage: str | None
    delay: timedelta | None
    conflict: bool
    policy_version: str
    details: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.provider or not self.dataset or not self.policy_version:
            raise ValueError("provider, dataset, and policy version are required")
        if self.freshness is not None and self.freshness < timedelta(0):
            raise ValueError("freshness cannot be negative")
        if self.delay is not None and self.delay < timedelta(0):
            raise ValueError("delay cannot be negative")
        if self.coverage not in {None, MarketDataCoverage.IEX.value, MarketDataCoverage.SIP.value}:
            raise ValueError("quality coverage must be IEX, SIP, or null")
        object.__setattr__(self, "observed_at", require_aware(self.observed_at).astimezone(UTC))
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True, slots=True)
class _Threshold:
    degraded_after: timedelta
    unavailable_after: timedelta

    def __post_init__(self) -> None:
        if self.degraded_after < timedelta(0):
            raise ValueError("quality degraded threshold cannot be negative")
        if self.degraded_after >= self.unavailable_after:
            raise ValueError("quality thresholds must increase")


class QualityPolicy:
    def __init__(
        self,
        *,
        version: str,
        freshness: Mapping[str, _Threshold],
        heartbeat: Mapping[str, _Threshold],
        delay: Mapping[str, _Threshold],
    ) -> None:
        if not version:
            raise ValueError("data quality policy version is required")
        self.version = version
        self._freshness = dict(freshness)
        self._heartbeat = dict(heartbeat)
        self._delay = dict(delay)

    @classmethod
    def load(cls, path: Path) -> QualityPolicy:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("data quality configuration is invalid") from error
        if not isinstance(document, dict) or not isinstance(document.get("version"), str):
            raise ValueError("data quality policy version is required")
        return cls(
            version=str(document["version"]),
            freshness=cls._thresholds(document.get("freshness"), section="freshness"),
            heartbeat=cls._thresholds(document.get("heartbeat"), section="heartbeat"),
            delay=cls._thresholds(document.get("delay"), section="delay"),
        )

    @staticmethod
    def _thresholds(value: object, *, section: str) -> dict[str, _Threshold]:
        if not isinstance(value, dict):
            raise ValueError(f"data quality {section} thresholds must be an object")
        result: dict[str, _Threshold] = {}
        for key, raw in cast(dict[object, object], value).items():
            if not isinstance(key, str) or not isinstance(raw, dict):
                raise ValueError(f"data quality {section} threshold entry is invalid")
            degraded = raw.get("degraded_after_seconds")
            unavailable = raw.get("unavailable_after_seconds")
            if (
                not isinstance(degraded, int)
                or isinstance(degraded, bool)
                or not isinstance(unavailable, int)
                or isinstance(unavailable, bool)
            ):
                raise ValueError("data quality threshold seconds must be integers")
            result[key] = _Threshold(
                degraded_after=timedelta(seconds=degraded),
                unavailable_after=timedelta(seconds=unavailable),
            )
        return result

    def thresholds(self, provider: str, dataset: str) -> tuple[timedelta, timedelta]:
        try:
            threshold = self._freshness[f"{provider}:{dataset}"]
        except KeyError as error:
            raise ValueError("quality freshness threshold is not configured") from error
        return threshold.degraded_after, threshold.unavailable_after

    def heartbeat_thresholds(
        self, provider: str, coverage: MarketDataCoverage
    ) -> tuple[timedelta, timedelta]:
        try:
            threshold = self._heartbeat[f"{provider}:{coverage.value}"]
        except KeyError as error:
            raise ValueError("quality heartbeat threshold is not configured") from error
        return threshold.degraded_after, threshold.unavailable_after

    def delay_thresholds(self, provider: str, dataset: str) -> tuple[timedelta, timedelta]:
        try:
            threshold = self._delay[f"{provider}:{dataset}"]
        except KeyError as error:
            raise ValueError("quality delay threshold is not configured") from error
        return threshold.degraded_after, threshold.unavailable_after


def _status(age: timedelta, thresholds: tuple[timedelta, timedelta]) -> QualityStatus:
    degraded_after, unavailable_after = thresholds
    if age >= unavailable_after:
        return QualityStatus.UNAVAILABLE
    if age >= degraded_after:
        return QualityStatus.DEGRADED
    return QualityStatus.PASS


def evaluate_freshness(
    *,
    provider: str,
    dataset: str,
    observed_at: datetime,
    latest_available_at: datetime,
    coverage: MarketDataCoverage | None,
    declared_delay: timedelta,
    policy: QualityPolicy,
) -> QualityAssessment:
    observed = require_aware(observed_at).astimezone(UTC)
    latest = require_aware(latest_available_at).astimezone(UTC)
    if declared_delay < timedelta(0):
        raise ValueError("declared delay cannot be negative")
    if latest > observed:
        raise ValueError("latest availability cannot be after observation time")
    freshness = observed - latest
    effective_age = max(timedelta(0), freshness - declared_delay)
    return QualityAssessment(
        dimension=QualityDimension.FRESHNESS,
        status=_status(effective_age, policy.thresholds(provider, dataset)),
        provider=provider,
        dataset=dataset,
        observed_at=observed,
        freshness=freshness,
        coverage=coverage.value if coverage is not None else None,
        delay=declared_delay,
        conflict=False,
        policy_version=policy.version,
        details={"effective_age_seconds": int(effective_age.total_seconds())},
    )


def evaluate_heartbeat(
    *,
    provider: str,
    observed_at: datetime,
    heartbeat_at: datetime,
    coverage: MarketDataCoverage,
    policy: QualityPolicy,
) -> QualityAssessment:
    observed = require_aware(observed_at).astimezone(UTC)
    heartbeat = require_aware(heartbeat_at).astimezone(UTC)
    if heartbeat > observed:
        raise ValueError("heartbeat cannot be after observation time")
    lag = observed - heartbeat
    return QualityAssessment(
        dimension=QualityDimension.HEARTBEAT,
        status=_status(lag, policy.heartbeat_thresholds(provider, coverage)),
        provider=provider,
        dataset="stream_heartbeat",
        observed_at=observed,
        freshness=lag,
        coverage=coverage.value,
        delay=timedelta(0),
        conflict=False,
        policy_version=policy.version,
        details={"heartbeat_lag_seconds": int(lag.total_seconds())},
    )


def evaluate_coverage(
    *,
    provider: str,
    dataset: str,
    observed_at: datetime,
    actual: MarketDataCoverage | None,
    required: MarketDataCoverage,
    policy_version: str,
) -> QualityAssessment:
    status = (
        QualityStatus.UNAVAILABLE
        if actual is None
        else QualityStatus.PASS
        if actual is required
        else QualityStatus.DEGRADED
    )
    return QualityAssessment(
        dimension=QualityDimension.COVERAGE,
        status=status,
        provider=provider,
        dataset=dataset,
        observed_at=observed_at,
        freshness=None,
        coverage=actual.value if actual is not None else None,
        delay=None,
        conflict=False,
        policy_version=policy_version,
        details={"required_coverage": required.value},
    )


def evaluate_delay(
    *,
    provider: str,
    dataset: str,
    observed_at: datetime,
    delay: timedelta,
    coverage: MarketDataCoverage | None,
    policy: QualityPolicy,
) -> QualityAssessment:
    if delay < timedelta(0):
        raise ValueError("delay cannot be negative")
    return QualityAssessment(
        dimension=QualityDimension.DELAY,
        status=_status(delay, policy.delay_thresholds(provider, dataset)),
        provider=provider,
        dataset=dataset,
        observed_at=observed_at,
        freshness=None,
        coverage=coverage.value if coverage is not None else None,
        delay=delay,
        conflict=False,
        policy_version=policy.version,
        details={"delay_seconds": int(delay.total_seconds())},
    )


def evaluate_conflict(
    *,
    provider: str,
    dataset: str,
    observed_at: datetime,
    conflict: bool,
    coverage: MarketDataCoverage | None,
    policy_version: str,
) -> QualityAssessment:
    return QualityAssessment(
        dimension=QualityDimension.CONFLICT,
        status=QualityStatus.FAIL if conflict else QualityStatus.PASS,
        provider=provider,
        dataset=dataset,
        observed_at=observed_at,
        freshness=None,
        coverage=coverage.value if coverage is not None else None,
        delay=None,
        conflict=conflict,
        policy_version=policy_version,
        details={},
    )


def assess_reconciliation(
    finding: ReconciliationFinding,
    *,
    provider: str,
    dataset: str,
    observed_at: datetime,
    policy_version: str,
) -> QualityAssessment:
    conflicting = finding.kind in {
        ReconciliationKind.OHLC_INVALID,
        ReconciliationKind.VOLUME_INVALID,
        ReconciliationKind.VOLUME_MISMATCH,
    }
    return QualityAssessment(
        dimension=QualityDimension.RECONCILIATION,
        status=QualityStatus.FAIL if conflicting else QualityStatus.DEGRADED,
        provider=provider,
        dataset=dataset,
        observed_at=observed_at,
        freshness=None,
        coverage=finding.coverage.value,
        delay=None,
        conflict=conflicting,
        policy_version=policy_version,
        details={
            "kind": finding.kind.value,
            "symbol": finding.symbol,
            "session": finding.session.value,
            "event_time": finding.event_time.isoformat(),
            **finding.details,
        },
    )


@dataclass(frozen=True, slots=True)
class ProviderHealthSignals:
    provider: str
    job_states: tuple[str, ...]
    cursor_lag: timedelta | None
    cursor_status: QualityStatus | None
    observations: tuple[QualityAssessment, ...]

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValueError("provider is required")
        if self.cursor_lag is not None and self.cursor_lag < timedelta(0):
            raise ValueError("cursor lag cannot be negative")
        if (self.cursor_lag is None) != (self.cursor_status is None):
            raise ValueError("cursor lag and cursor status must be provided together")
        if any(observation.provider != self.provider for observation in self.observations):
            raise ValueError("provider health observations must match the provider")


def derive_provider_health(signals: ProviderHealthSignals) -> QualityStatus:
    if (
        signals.cursor_status in {QualityStatus.UNAVAILABLE, QualityStatus.FAIL}
        or any(state in {"FAILED", "DEAD_LETTER"} for state in signals.job_states)
        or any(
            observation.status in {QualityStatus.UNAVAILABLE, QualityStatus.FAIL}
            for observation in signals.observations
        )
    ):
        return QualityStatus.UNAVAILABLE
    if (
        signals.cursor_status is QualityStatus.DEGRADED
        or any(state in {"RETRY_SCHEDULED", "COMPLETED_WITH_GAPS"} for state in signals.job_states)
        or any(observation.status is QualityStatus.DEGRADED for observation in signals.observations)
    ):
        return QualityStatus.DEGRADED
    return QualityStatus.PASS


def provider_health_transition(
    signals: ProviderHealthSignals,
    *,
    observed_at: datetime,
    policy_version: str,
) -> QualityAssessment:
    return QualityAssessment(
        dimension=QualityDimension.PROVIDER,
        status=derive_provider_health(signals),
        provider=signals.provider,
        dataset="provider_health",
        observed_at=observed_at,
        freshness=signals.cursor_lag,
        coverage=None,
        delay=None,
        conflict=False,
        policy_version=policy_version,
        details={"job_states": list(signals.job_states)},
    )
