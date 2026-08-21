from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stock_platform.domain.common.time import require_aware

ZERO = Decimal("0")


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, ZERO) / Decimal(len(values))


def _population_deviation(values: Sequence[Decimal]) -> Decimal:
    average = _mean(values)
    return (_mean(tuple((value - average) ** 2 for value in values))).sqrt()


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    return ZERO if denominator == ZERO else numerator / denominator


@dataclass(frozen=True, slots=True)
class PortfolioMetrics:
    total_return: Decimal
    cagr: Decimal
    volatility: Decimal
    sharpe: Decimal
    sortino: Decimal
    max_drawdown: Decimal
    calmar: Decimal
    turnover: Decimal
    beta: Decimal
    information_ratio: Decimal


def calculate_metrics(
    *,
    nav_points: Sequence[tuple[datetime, Decimal]],
    periodic_returns: Sequence[Decimal],
    benchmark_returns: Sequence[Decimal],
    traded_notional: Decimal,
    periods_per_year: Decimal,
    risk_free_rate: Decimal,
) -> PortfolioMetrics:
    if len(nav_points) < 2:
        raise ValueError("at least two NAV points are required")
    if not periodic_returns or len(periodic_returns) != len(benchmark_returns):
        raise ValueError("portfolio and benchmark returns must be non-empty and aligned")
    if len(periodic_returns) != len(nav_points) - 1:
        raise ValueError("returns must align with NAV intervals")
    for name, values in (
        ("periodic_returns", periodic_returns),
        ("benchmark_returns", benchmark_returns),
    ):
        if any(not isinstance(value, Decimal) or not value.is_finite() for value in values):
            raise TypeError(f"{name} must contain finite Decimal values")
    for value in (traded_notional, periods_per_year, risk_free_rate):
        if not isinstance(value, Decimal):
            raise TypeError("metric inputs must use Decimal")
        if not value.is_finite():
            raise ValueError("metric inputs must be finite")
    if traded_notional < ZERO or periods_per_year <= ZERO:
        raise ValueError("notional must be non-negative and annualization must be positive")

    ordered = tuple(nav_points)
    for index, (timestamp, nav) in enumerate(ordered):
        require_aware(timestamp)
        if not isinstance(nav, Decimal):
            raise TypeError("NAV values must use Decimal")
        if not nav.is_finite():
            raise ValueError("NAV values must be finite")
        if nav <= ZERO:
            raise ValueError("NAV values must be positive")
        if index and timestamp <= ordered[index - 1][0]:
            raise ValueError("NAV timestamps must increase")
    initial_nav = ordered[0][1]
    final_nav = ordered[-1][1]
    total_return = final_nav / initial_nav - Decimal("1")
    elapsed_seconds = Decimal(str((ordered[-1][0] - ordered[0][0]).total_seconds()))
    years = elapsed_seconds / Decimal("31536000")
    cagr = (final_nav / initial_nav) ** (Decimal("1") / years) - Decimal("1")

    annualizer = periods_per_year.sqrt()
    excess = tuple(value - risk_free_rate / periods_per_year for value in periodic_returns)
    volatility = _population_deviation(periodic_returns) * annualizer
    sharpe = _ratio(_mean(excess), _population_deviation(excess)) * annualizer
    downside = (_mean(tuple(min(value, ZERO) ** 2 for value in excess))).sqrt()
    sortino = _ratio(_mean(excess), downside) * annualizer

    peak = ordered[0][1]
    drawdowns: list[Decimal] = []
    for _, nav in ordered:
        peak = max(peak, nav)
        drawdowns.append(nav / peak - Decimal("1"))
    max_drawdown = min(drawdowns)
    calmar = _ratio(cagr, abs(max_drawdown))
    turnover = traded_notional / initial_nav

    portfolio_mean = _mean(periodic_returns)
    benchmark_mean = _mean(benchmark_returns)
    covariance = _mean(
        tuple(
            (portfolio - portfolio_mean) * (benchmark - benchmark_mean)
            for portfolio, benchmark in zip(periodic_returns, benchmark_returns, strict=True)
        )
    )
    benchmark_variance = _mean(tuple((value - benchmark_mean) ** 2 for value in benchmark_returns))
    beta = _ratio(covariance, benchmark_variance)
    active = tuple(
        portfolio - benchmark
        for portfolio, benchmark in zip(periodic_returns, benchmark_returns, strict=True)
    )
    information_ratio = _ratio(_mean(active), _population_deviation(active)) * annualizer
    return PortfolioMetrics(
        total_return=total_return,
        cagr=cagr,
        volatility=volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
        calmar=calmar,
        turnover=turnover,
        beta=beta,
        information_ratio=information_ratio,
    )
