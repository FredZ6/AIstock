from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware

ZERO = Decimal("0")
_BPS = Decimal("10000")


@dataclass(frozen=True, slots=True)
class PriceFrame:
    as_of: datetime
    prices: Mapping[Symbol, Decimal]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", require_aware(self.as_of).astimezone(UTC))
        if not self.prices:
            raise ValueError("price frame cannot be empty")
        for symbol, price in self.prices.items():
            Symbol(str(symbol))
            if not isinstance(price, Decimal):
                raise TypeError("benchmark prices must use Decimal")
            if not price.is_finite() or price <= ZERO:
                raise ValueError("benchmark prices must be finite and positive")


@dataclass(frozen=True, slots=True)
class BenchmarkReturns:
    cash: tuple[Decimal, ...]
    qqq: tuple[Decimal, ...]
    equal_weight: tuple[Decimal, ...]
    momentum: tuple[Decimal, ...]


def benchmark_returns(
    frames: Sequence[PriceFrame],
    *,
    watchlist: Sequence[Symbol],
    momentum_lookback: int,
    cost_bps: Decimal,
    initial_nav: Decimal = Decimal("1"),
    fee_per_share: Decimal = ZERO,
    minimum_fee: Decimal = ZERO,
) -> BenchmarkReturns:
    if len(frames) < 2:
        empty: tuple[Decimal, ...] = ()
        return BenchmarkReturns(empty, empty, empty, empty)
    if momentum_lookback < 1:
        raise ValueError("momentum lookback must be positive")
    for name, value in (
        ("cost_bps", cost_bps),
        ("initial_nav", initial_nav),
        ("fee_per_share", fee_per_share),
        ("minimum_fee", minimum_fee),
    ):
        if not isinstance(value, Decimal):
            raise TypeError(f"{name} must use Decimal")
        if not value.is_finite() or value < ZERO:
            raise ValueError(f"{name} must be finite and non-negative")
    if initial_nav == ZERO:
        raise ValueError("benchmark initial NAV must be positive")
    symbols = tuple(Symbol(str(symbol)) for symbol in watchlist)
    if not symbols:
        raise ValueError("watchlist cannot be empty")
    ordered = tuple(frames)
    if any(ordered[index].as_of <= ordered[index - 1].as_of for index in range(1, len(ordered))):
        raise ValueError("benchmark frames must increase")
    required = (Symbol("QQQ"),) + symbols
    if any(symbol not in frame.prices for frame in ordered for symbol in required):
        raise ValueError("every benchmark frame requires QQQ and watchlist prices")

    qqq: list[Decimal] = []
    equal: list[Decimal] = []
    momentum: list[Decimal] = []
    previous: dict[str, dict[Symbol, Decimal]] = {
        "qqq": {},
        "equal": {},
        "momentum": {},
    }

    def period_result(
        strategy: str,
        target: Mapping[Symbol, Decimal],
        current: PriceFrame,
        returns: Mapping[Symbol, Decimal],
    ) -> Decimal:
        prior = previous[strategy]
        deltas = {
            symbol: target.get(symbol, ZERO) - prior.get(symbol, ZERO)
            for symbol in set(prior) | set(target)
        }
        turnover = sum((abs(delta) for delta in deltas.values()), ZERO)
        spread_and_slippage = turnover * cost_bps / _BPS
        fees = (
            sum(
                (
                    max(
                        minimum_fee,
                        fee_per_share * abs(delta) * initial_nav / current.prices[symbol],
                    )
                    for symbol, delta in deltas.items()
                    if delta != ZERO
                ),
                ZERO,
            )
            / initial_nav
        )
        raw_return = sum(
            (weight * returns[symbol] for symbol, weight in target.items()),
            ZERO,
        )
        gross = Decimal("1") + raw_return
        previous[strategy] = (
            {
                symbol: weight * (Decimal("1") + returns[symbol]) / gross
                for symbol, weight in target.items()
            }
            if gross != ZERO
            else dict(target)
        )
        return raw_return - spread_and_slippage - fees

    for index in range(len(ordered) - 1):
        current = ordered[index]
        following = ordered[index + 1]

        period_returns = {
            symbol: following.prices[symbol] / current.prices[symbol] - Decimal("1")
            for symbol in required
        }

        qqq.append(
            period_result(
                "qqq",
                {Symbol("QQQ"): Decimal("1")},
                current,
                period_returns,
            )
        )
        equal.append(
            period_result(
                "equal",
                {symbol: Decimal("1") / Decimal(len(symbols)) for symbol in symbols},
                current,
                period_returns,
            )
        )
        if index < momentum_lookback:
            momentum.append(period_result("momentum", {}, current, period_returns))
        else:
            lookback = ordered[index - momentum_lookback]
            selected = max(
                symbols,
                key=lambda symbol: (
                    current.prices[symbol] / lookback.prices[symbol] - Decimal("1"),
                    str(symbol),
                ),
            )
            momentum.append(
                period_result(
                    "momentum",
                    {selected: Decimal("1")},
                    current,
                    period_returns,
                )
            )
    periods = len(ordered) - 1
    return BenchmarkReturns(
        cash=(ZERO,) * periods,
        qqq=tuple(qqq),
        equal_weight=tuple(equal),
        momentum=tuple(momentum),
    )
