from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from stock_platform.application.alerting.features import FeatureCalculator, GapContext, MinuteBar
from stock_platform.domain.common.ids import Symbol

START = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)


def bar(
    minute: int,
    *,
    close: str,
    volume: str,
    open_: str | None = None,
    previous_close: str | None = "99",
) -> MinuteBar:
    event_time = START + timedelta(minutes=minute)
    close_value = Decimal(close)
    open_value = Decimal(open_ or close)
    return MinuteBar(
        symbol=Symbol("NVDA"),
        event_time=event_time,
        available_at=event_time + timedelta(seconds=2),
        ingested_at=event_time + timedelta(seconds=3),
        open=open_value,
        high=max(open_value, close_value) + Decimal("0.2"),
        low=min(open_value, close_value) - Decimal("0.2"),
        close=close_value,
        volume=Decimal(volume),
        previous_close=Decimal(previous_close) if previous_close is not None else None,
        provider="ALPACA",
        content_hash=f"{minute:064x}",
        raw_object_key=f"alpaca-stream/nvda/{minute}.json",
        raw_payload={"minute": minute},
    )


def test_anomaly_features_are_decimal_deterministic_and_point_in_time_safe() -> None:
    bars = (
        bar(0, close="100", volume="100", open_="100"),
        bar(1, close="100.2", volume="110"),
        bar(2, close="99.9", volume="90"),
        bar(3, close="100.3", volume="105"),
        bar(4, close="100.1", volume="95"),
        bar(5, close="106", volume="600", open_="100"),
    )

    features = FeatureCalculator(lookback=5).calculate(
        bars,
        evaluated_at=bars[-1].ingested_at,
        gap_context=GapContext(
            session_open=Decimal("100"),
            previous_close=Decimal("99"),
        ),
    )

    assert features.five_minute_return == Decimal("0.06")
    assert features.relative_volume == Decimal("6")
    assert features.return_zscore is not None and features.return_zscore > Decimal("1")
    assert features.volume_zscore is not None and features.volume_zscore > Decimal("1")
    assert features.volatility_zscore is not None and features.volatility_zscore > Decimal("1")
    assert features.gap == Decimal("100") / Decimal("99") - Decimal("1")
    assert features.breakout is True
    assert features.data_quality.provider == "ALPACA"
    assert features.data_quality.delay == timedelta(seconds=3)
    assert features.data_quality.coverage == Decimal("1")
    assert features.data_quality.conflict is False

    repeated = FeatureCalculator(lookback=5).calculate(
        tuple(reversed(tuple(reversed(bars)))),
        evaluated_at=bars[-1].ingested_at,
        gap_context=GapContext(
            session_open=Decimal("100"),
            previous_close=Decimal("99"),
        ),
    )
    assert repeated == features


def test_gap_is_not_invented_from_a_truncated_intraday_window() -> None:
    bars = tuple(bar(index, close="100", volume="100") for index in range(6))

    features = FeatureCalculator(lookback=5).calculate(
        bars,
        evaluated_at=bars[-1].ingested_at,
    )

    assert features.gap is None


def test_feature_calculation_rejects_future_or_naive_market_data() -> None:
    item = bar(0, close="100", volume="100")

    with pytest.raises(ValueError, match="available at evaluation time"):
        FeatureCalculator().calculate((item,), evaluated_at=item.event_time)

    with pytest.raises(ValueError, match="timezone-aware"):
        MinuteBar(
            symbol=Symbol("NVDA"),
            event_time=datetime(2026, 8, 20, 14, 30),
            available_at=START,
            ingested_at=START,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("100"),
            previous_close=None,
            provider="ALPACA",
            content_hash="a" * 64,
            raw_object_key="fixture.json",
            raw_payload={},
        )


def test_market_values_reject_binary_float() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        MinuteBar(
            symbol=Symbol("NVDA"),
            event_time=START,
            available_at=START,
            ingested_at=START,
            open=100.0,  # type: ignore[arg-type]
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("100"),
            previous_close=None,
            provider="ALPACA",
            content_hash="a" * 64,
            raw_object_key="fixture.json",
            raw_payload={},
        )
