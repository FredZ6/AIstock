"""Versioned deterministic multi-condition alert rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from stock_platform.application.alerting.features import AnomalyFeatures


class AlertSeverity(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class RuleThresholds:
    five_minute_return: Decimal
    relative_volume: Decimal
    return_zscore: Decimal
    volume_zscore: Decimal
    volatility_zscore: Decimal
    gap: Decimal


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    triggered: bool
    conditions: tuple[str, ...]
    severity: AlertSeverity
    materiality: Decimal
    rule_id: str
    rule_version: str


@dataclass(frozen=True, slots=True)
class AlertRule:
    rule_id: str
    version: str
    thresholds: RuleThresholds
    minimum_conditions: int

    def __post_init__(self) -> None:
        if self.minimum_conditions < 1 or self.minimum_conditions > 7:
            raise ValueError("minimum_conditions must be between one and seven")

    @classmethod
    def default(cls, *, minimum_conditions: int = 3) -> AlertRule:
        return cls(
            rule_id="market-anomaly-v1",
            version="alert-policy-v1",
            thresholds=RuleThresholds(
                five_minute_return=Decimal("0.04"),
                relative_volume=Decimal("3"),
                return_zscore=Decimal("2"),
                volume_zscore=Decimal("2"),
                volatility_zscore=Decimal("2"),
                gap=Decimal("0.02"),
            ),
            minimum_conditions=minimum_conditions,
        )

    def evaluate(self, features: AnomalyFeatures) -> RuleEvaluation:
        checks = (
            (
                "FIVE_MINUTE_RETURN",
                features.five_minute_return is not None
                and abs(features.five_minute_return) >= self.thresholds.five_minute_return,
            ),
            (
                "RELATIVE_VOLUME",
                features.relative_volume is not None
                and features.relative_volume >= self.thresholds.relative_volume,
            ),
            (
                "RETURN_ZSCORE",
                features.return_zscore is not None
                and abs(features.return_zscore) >= self.thresholds.return_zscore,
            ),
            (
                "VOLUME_ZSCORE",
                features.volume_zscore is not None
                and abs(features.volume_zscore) >= self.thresholds.volume_zscore,
            ),
            (
                "VOLATILITY_ZSCORE",
                features.volatility_zscore is not None
                and abs(features.volatility_zscore) >= self.thresholds.volatility_zscore,
            ),
            (
                "GAP",
                features.gap is not None and abs(features.gap) >= self.thresholds.gap,
            ),
            ("BREAKOUT", features.breakout is True),
        )
        conditions = tuple(name for name, matched in checks if matched)
        count = len(conditions)
        triggered = count >= self.minimum_conditions
        if not triggered:
            severity = AlertSeverity.NONE
        elif count >= 5:
            severity = AlertSeverity.CRITICAL
        elif count >= 4:
            severity = AlertSeverity.HIGH
        elif count >= 3:
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW
        return RuleEvaluation(
            triggered=triggered,
            conditions=conditions,
            severity=severity,
            materiality=Decimal(count) / Decimal(len(checks)),
            rule_id=self.rule_id,
            rule_version=self.version,
        )
