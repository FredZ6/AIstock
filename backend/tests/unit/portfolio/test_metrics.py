from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from stock_platform.application.portfolio.benchmarks import PriceFrame, benchmark_returns
from stock_platform.application.portfolio.metrics import calculate_metrics
from stock_platform.domain.common.ids import Symbol


def test_metrics_match_hand_calculated_fixture() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    metrics = calculate_metrics(
        nav_points=(
            (start, Decimal("100")),
            (start + timedelta(days=100), Decimal("120")),
            (start + timedelta(days=200), Decimal("90")),
            (start + timedelta(days=365), Decimal("110")),
        ),
        periodic_returns=(Decimal("0.10"), Decimal("-0.05"), Decimal("0.02")),
        benchmark_returns=(Decimal("0.05"), Decimal("-0.02"), Decimal("0.01")),
        traded_notional=Decimal("25"),
        periods_per_year=Decimal("1"),
        risk_free_rate=Decimal("0"),
    )

    assert metrics.total_return == Decimal("0.10")
    assert metrics.cagr.quantize(Decimal("0.0001")) == Decimal("0.1000")
    assert metrics.volatility.quantize(Decimal("0.000001")) == Decimal("0.061283")
    assert metrics.sharpe.quantize(Decimal("0.000001")) == Decimal("0.380750")
    assert metrics.sortino.quantize(Decimal("0.000001")) == Decimal("0.808290")
    assert metrics.max_drawdown == Decimal("-0.25")
    assert metrics.calmar.quantize(Decimal("0.0001")) == Decimal("0.4000")
    assert metrics.turnover == Decimal("0.25")
    assert metrics.beta.quantize(Decimal("0.000001")) == Decimal("2.135135")
    assert metrics.information_ratio.quantize(Decimal("0.000001")) == Decimal("0.306186")


def test_cash_qqq_equal_weight_and_momentum_use_same_periods() -> None:
    start = datetime(2026, 8, 18, 20, 0, tzinfo=UTC)
    frames = (
        PriceFrame(
            start,
            {
                Symbol("QQQ"): Decimal("100"),
                Symbol("NVDA"): Decimal("100"),
                Symbol("AAPL"): Decimal("100"),
            },
        ),
        PriceFrame(
            start + timedelta(days=1),
            {
                Symbol("QQQ"): Decimal("110"),
                Symbol("NVDA"): Decimal("110"),
                Symbol("AAPL"): Decimal("90"),
            },
        ),
        PriceFrame(
            start + timedelta(days=2),
            {
                Symbol("QQQ"): Decimal("99"),
                Symbol("NVDA"): Decimal("121"),
                Symbol("AAPL"): Decimal("99"),
            },
        ),
    )

    result = benchmark_returns(
        frames,
        watchlist=(Symbol("NVDA"), Symbol("AAPL")),
        momentum_lookback=1,
        cost_bps=Decimal("0"),
    )

    assert result.cash == (Decimal("0"), Decimal("0"))
    assert result.qqq == (Decimal("0.10"), Decimal("-0.10"))
    assert result.equal_weight == (Decimal("0.00"), Decimal("0.10"))
    assert result.momentum == (Decimal("0"), Decimal("0.10"))

    with_costs = benchmark_returns(
        frames,
        watchlist=(Symbol("NVDA"), Symbol("AAPL")),
        momentum_lookback=1,
        cost_bps=Decimal("100"),
        initial_nav=Decimal("1000"),
        fee_per_share=Decimal("0"),
        minimum_fee=Decimal("0"),
    )
    assert with_costs.qqq == (Decimal("0.09"), Decimal("-0.10"))
    assert with_costs.momentum == (Decimal("0"), Decimal("0.09"))


def test_metrics_require_aligned_observations_and_finite_decimal_inputs() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    nav_points = (
        (start, Decimal("100")),
        (start + timedelta(days=1), Decimal("101")),
        (start + timedelta(days=2), Decimal("102")),
    )
    with pytest.raises(ValueError, match="NAV intervals"):
        calculate_metrics(
            nav_points=nav_points,
            periodic_returns=(Decimal("0.01"),),
            benchmark_returns=(Decimal("0.01"),),
            traded_notional=Decimal("1"),
            periods_per_year=Decimal("252"),
            risk_free_rate=Decimal("0"),
        )
    with pytest.raises(ValueError, match="finite"):
        calculate_metrics(
            nav_points=nav_points,
            periodic_returns=(Decimal("0.01"), Decimal("0.01")),
            benchmark_returns=(Decimal("0.01"), Decimal("0.01")),
            traded_notional=Decimal("1"),
            periods_per_year=Decimal("252"),
            risk_free_rate=Decimal("NaN"),
        )
    with pytest.raises(ValueError, match="NAV values must be finite"):
        calculate_metrics(
            nav_points=(nav_points[0], (nav_points[1][0], Decimal("NaN"))),
            periodic_returns=(Decimal("0.01"),),
            benchmark_returns=(Decimal("0.01"),),
            traded_notional=Decimal("1"),
            periods_per_year=Decimal("252"),
            risk_free_rate=Decimal("0"),
        )
