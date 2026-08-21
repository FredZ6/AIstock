from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from stock_platform.application.learning.eligibility import matured_horizons
from stock_platform.domain.learning.outcome import (
    DecisionForReview,
    Horizon,
    PriceObservation,
    compute_outcome,
)

NOW = datetime(2026, 8, 21, tzinfo=UTC)


def test_maturity_windows_only_include_elapsed_horizons() -> None:
    decision = DecisionForReview(uuid4(), "NVDA", NOW - timedelta(days=6), Decimal("100"))

    assert matured_horizons(decision, as_of=NOW) == (Horizon.DAY_1, Horizon.DAY_5)


def test_immature_decision_remains_pending() -> None:
    decision = DecisionForReview(uuid4(), "NVDA", NOW - timedelta(hours=23), Decimal("100"))

    assert matured_horizons(decision, as_of=NOW) == ()


def test_return_horizons_and_excursions_use_decimal_and_point_in_time_prices() -> None:
    decision = DecisionForReview(uuid4(), "NVDA", NOW - timedelta(days=6), Decimal("100"))
    prices = (
        PriceObservation(NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("110")),
        PriceObservation(NOW - timedelta(days=3), NOW - timedelta(days=3), Decimal("90")),
        PriceObservation(NOW - timedelta(days=1), NOW - timedelta(days=1), Decimal("120")),
    )
    benchmark = (
        PriceObservation(decision.decision_time, decision.decision_time, Decimal("100")),
        PriceObservation(NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("102")),
        PriceObservation(NOW - timedelta(days=1), NOW - timedelta(days=1), Decimal("105")),
    )

    outcome = compute_outcome(decision, prices=prices, benchmark_prices=benchmark, as_of=NOW)

    assert outcome.status == "MATURED"
    assert outcome.returns[Horizon.DAY_1] == Decimal("0.1")
    assert outcome.returns[Horizon.DAY_5] == Decimal("0.2")
    assert outcome.excess_returns[Horizon.DAY_5] == Decimal("0.15")
    assert outcome.maximum_favorable_excursion == Decimal("0.2")
    assert outcome.maximum_adverse_excursion == Decimal("-0.1")


def test_outcome_rejects_future_available_price() -> None:
    decision = DecisionForReview(uuid4(), "NVDA", NOW - timedelta(days=2), Decimal("100"))
    future = PriceObservation(NOW - timedelta(days=1), NOW + timedelta(seconds=1), Decimal("110"))

    with pytest.raises(ValueError, match="available"):
        compute_outcome(decision, prices=(future,), benchmark_prices=(), as_of=NOW)


def test_outcome_rejects_float_and_naive_time() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        DecisionForReview(uuid4(), "NVDA", NOW, 100.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        DecisionForReview(uuid4(), "NVDA", datetime(2026, 8, 21), Decimal("100"))


def test_pre_decision_prices_do_not_contaminate_excursions_or_benchmark_base() -> None:
    decision = DecisionForReview(uuid4(), "NVDA", NOW - timedelta(days=6), Decimal("100"))
    prices = (
        PriceObservation(
            decision.decision_time - timedelta(days=1),
            decision.decision_time - timedelta(days=1),
            Decimal("10"),
        ),
        PriceObservation(
            decision.decision_time + timedelta(days=1),
            decision.decision_time + timedelta(days=1),
            Decimal("110"),
        ),
    )
    benchmark = (
        PriceObservation(
            decision.decision_time - timedelta(days=2),
            decision.decision_time - timedelta(days=2),
            Decimal("50"),
        ),
        PriceObservation(decision.decision_time, decision.decision_time, Decimal("100")),
        PriceObservation(
            decision.decision_time + timedelta(days=1),
            decision.decision_time + timedelta(days=1),
            Decimal("105"),
        ),
    )

    outcome = compute_outcome(decision, prices=prices, benchmark_prices=benchmark, as_of=NOW)

    assert outcome.maximum_adverse_excursion == Decimal("0")
    assert outcome.maximum_favorable_excursion == Decimal("0.1")
    assert outcome.excess_returns[Horizon.DAY_1] == Decimal("0.05")


def test_missing_benchmark_base_does_not_fabricate_excess_return() -> None:
    decision = DecisionForReview(uuid4(), "NVDA", NOW - timedelta(days=2), Decimal("100"))
    target = NOW - timedelta(days=1)

    outcome = compute_outcome(
        decision,
        prices=(PriceObservation(target, target, Decimal("110")),),
        benchmark_prices=(PriceObservation(target, target, Decimal("220")),),
        as_of=NOW,
    )

    assert outcome.returns[Horizon.DAY_1] == Decimal("0.1")
    assert Horizon.DAY_1 not in outcome.excess_returns
