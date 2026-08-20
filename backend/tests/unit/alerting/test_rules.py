from datetime import UTC, datetime, timedelta
from decimal import Decimal

from stock_platform.application.alerting.features import AnomalyFeatures, DataQuality
from stock_platform.application.alerting.rules import AlertRule, AlertSeverity, RuleThresholds


def feature_set(**changes: object) -> AnomalyFeatures:
    values: dict[str, object] = {
        "symbol": "NVDA",
        "event_time": datetime(2026, 8, 20, 14, 35, tzinfo=UTC),
        "five_minute_return": Decimal("0.06"),
        "relative_volume": Decimal("5"),
        "return_zscore": Decimal("3"),
        "volume_zscore": Decimal("4"),
        "volatility_zscore": Decimal("3"),
        "gap": Decimal("0.01"),
        "breakout": True,
        "data_quality": DataQuality(
            freshness=timedelta(seconds=1),
            coverage=Decimal("1"),
            provider="ALPACA",
            delay=timedelta(seconds=2),
            conflict=False,
        ),
    }
    values.update(changes)
    return AnomalyFeatures(**values)  # type: ignore[arg-type]


def test_multi_condition_rule_is_authoritative_and_assigns_materiality() -> None:
    rule = AlertRule(
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
        minimum_conditions=3,
    )

    result = rule.evaluate(feature_set())

    assert result.triggered is True
    assert result.severity is AlertSeverity.CRITICAL
    assert result.materiality == Decimal("0.8571428571428571428571428571")
    assert result.conditions == (
        "FIVE_MINUTE_RETURN",
        "RELATIVE_VOLUME",
        "RETURN_ZSCORE",
        "VOLUME_ZSCORE",
        "VOLATILITY_ZSCORE",
        "BREAKOUT",
    )
    assert result.rule_version == "alert-policy-v1"


def test_one_large_signal_does_not_bypass_multi_condition_gate() -> None:
    rule = AlertRule.default(minimum_conditions=2)

    result = rule.evaluate(
        feature_set(
            relative_volume=Decimal("1"),
            return_zscore=Decimal("0"),
            volume_zscore=Decimal("0"),
            volatility_zscore=Decimal("0"),
            gap=Decimal("0"),
            breakout=False,
        )
    )

    assert result.triggered is False
    assert result.severity is AlertSeverity.NONE
    assert result.conditions == ("FIVE_MINUTE_RETURN",)
