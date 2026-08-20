from datetime import UTC, datetime, timedelta

import pytest
from stock_platform.application.alerting.dedup import AlertIdentity


def test_alert_identity_is_stable_inside_cooldown_and_changes_after_it() -> None:
    event_time = datetime(2026, 8, 20, 14, 37, tzinfo=UTC)
    first = AlertIdentity.for_trigger(
        symbol="NVDA",
        rule_id="market-anomaly-v1",
        event_time=event_time,
        cooldown=timedelta(minutes=15),
    )
    redelivery = AlertIdentity.for_trigger(
        symbol="NVDA",
        rule_id="market-anomaly-v1",
        event_time=event_time + timedelta(minutes=5),
        cooldown=timedelta(minutes=15),
    )
    next_window = AlertIdentity.for_trigger(
        symbol="NVDA",
        rule_id="market-anomaly-v1",
        event_time=event_time + timedelta(minutes=15),
        cooldown=timedelta(minutes=15),
    )

    assert redelivery == first
    assert next_window.id != first.id
    assert next_window.key != first.key


def test_alert_identity_rejects_naive_time_and_nonpositive_cooldown() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AlertIdentity.for_trigger(
            symbol="NVDA",
            rule_id="rule",
            event_time=datetime(2026, 8, 20, 14, 37),
            cooldown=timedelta(minutes=15),
        )

    with pytest.raises(ValueError, match="positive"):
        AlertIdentity.for_trigger(
            symbol="NVDA",
            rule_id="rule",
            event_time=datetime(2026, 8, 20, 14, 37, tzinfo=UTC),
            cooldown=timedelta(0),
        )
