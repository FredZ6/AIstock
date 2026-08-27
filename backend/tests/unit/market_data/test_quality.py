import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from stock_platform.application.market_data.quality import (
    ProviderHealthSignals,
    QualityDimension,
    QualityPolicy,
    QualityStatus,
    assess_reconciliation,
    derive_provider_health,
    evaluate_coverage,
    evaluate_freshness,
    evaluate_heartbeat,
    provider_health_transition,
)
from stock_platform.application.market_data.reconciliation import (
    BarObservation,
    ReconciliationKind,
    reconcile_bars,
)
from stock_platform.domain.ingestion.models import MarketDataCoverage, MarketSession

NOW = datetime(2026, 8, 27, 14, tzinfo=UTC)
CONFIG = Path("backend/config/data_quality_v1.yaml")


def test_versioned_policy_loads_raw_thresholds_without_ui_grade() -> None:
    policy = QualityPolicy.load(CONFIG)

    assert policy.version == "data-quality-v1"
    assert policy.thresholds("ALPACA", "company_news") == (
        timedelta(minutes=10),
        timedelta(minutes=30),
    )
    assert policy.thresholds("SEC", "filings") == (
        timedelta(minutes=15),
        timedelta(minutes=60),
    )
    document = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert "grade" not in document


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(minutes=9), QualityStatus.PASS),
        (timedelta(minutes=10), QualityStatus.DEGRADED),
        (timedelta(minutes=30), QualityStatus.UNAVAILABLE),
    ],
)
def test_news_freshness_uses_versioned_threshold_boundaries(
    age: timedelta,
    expected: QualityStatus,
) -> None:
    result = evaluate_freshness(
        provider="ALPACA",
        dataset="company_news",
        observed_at=NOW,
        latest_available_at=NOW - age,
        coverage=None,
        declared_delay=timedelta(0),
        policy=QualityPolicy.load(CONFIG),
    )

    assert result.dimension is QualityDimension.FRESHNESS
    assert result.status is expected
    assert result.freshness == age
    assert result.delay == timedelta(0)
    assert result.provider == "ALPACA"
    assert result.conflict is False


def test_sip_freshness_is_relative_to_declared_entitlement_delay() -> None:
    result = evaluate_freshness(
        provider="ALPACA",
        dataset="price_bars",
        observed_at=NOW,
        latest_available_at=NOW - timedelta(minutes=17),
        coverage=MarketDataCoverage.SIP,
        declared_delay=timedelta(minutes=15),
        policy=QualityPolicy.load(CONFIG),
    )

    assert result.status is QualityStatus.PASS
    assert result.freshness == timedelta(minutes=17)
    assert result.delay == timedelta(minutes=15)


def test_quality_evaluation_rejects_naive_time_and_negative_delay() -> None:
    policy = QualityPolicy.load(CONFIG)
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_freshness(
            provider="ALPACA",
            dataset="company_news",
            observed_at=datetime(2026, 8, 27, 14),
            latest_available_at=NOW,
            coverage=None,
            declared_delay=timedelta(0),
            policy=policy,
        )
    with pytest.raises(ValueError, match="delay"):
        evaluate_freshness(
            provider="ALPACA",
            dataset="company_news",
            observed_at=NOW,
            latest_available_at=NOW,
            coverage=None,
            declared_delay=timedelta(seconds=-1),
            policy=policy,
        )


def test_iex_health_uses_stream_heartbeat_not_absence_of_symbol_trades() -> None:
    healthy = evaluate_heartbeat(
        provider="ALPACA",
        observed_at=NOW,
        heartbeat_at=NOW - timedelta(seconds=20),
        coverage=MarketDataCoverage.IEX,
        policy=QualityPolicy.load(CONFIG),
    )
    unavailable = evaluate_heartbeat(
        provider="ALPACA",
        observed_at=NOW,
        heartbeat_at=NOW - timedelta(minutes=3),
        coverage=MarketDataCoverage.IEX,
        policy=QualityPolicy.load(CONFIG),
    )

    assert healthy.status is QualityStatus.PASS
    assert unavailable.status is QualityStatus.UNAVAILABLE


def test_provider_health_is_derived_without_a_persisted_snapshot() -> None:
    policy = QualityPolicy.load(CONFIG)
    degraded = evaluate_freshness(
        provider="ALPACA",
        dataset="company_news",
        observed_at=NOW,
        latest_available_at=NOW - timedelta(minutes=12),
        coverage=None,
        declared_delay=timedelta(0),
        policy=policy,
    )

    result = derive_provider_health(
        ProviderHealthSignals(
            provider="ALPACA",
            job_states=("SUCCEEDED", "RETRY_SCHEDULED"),
            cursor_lag=timedelta(minutes=1),
            observations=(degraded,),
        )
    )

    assert result is QualityStatus.DEGRADED


def test_coverage_gap_and_provider_health_transition_remain_raw_observations() -> None:
    coverage = evaluate_coverage(
        provider="ALPACA",
        dataset="price_bars",
        observed_at=NOW,
        actual=MarketDataCoverage.IEX,
        required=MarketDataCoverage.SIP,
        policy_version="data-quality-v1",
    )
    transition = provider_health_transition(
        ProviderHealthSignals(
            provider="ALPACA",
            job_states=("FAILED",),
            cursor_lag=None,
            observations=(),
        ),
        observed_at=NOW,
        policy_version="data-quality-v1",
    )

    assert coverage.dimension is QualityDimension.COVERAGE
    assert coverage.status is QualityStatus.DEGRADED
    assert coverage.coverage == "IEX"
    assert coverage.conflict is False
    assert transition.dimension is QualityDimension.PROVIDER
    assert transition.status is QualityStatus.UNAVAILABLE


def test_reconciliation_finding_becomes_a_versioned_conflict_observation() -> None:
    bar = BarObservation(
        normalized_record_id=uuid4(),
        symbol="NVDA",
        event_time=NOW - timedelta(minutes=1),
        available_at=NOW,
        coverage=MarketDataCoverage.SIP,
        session=MarketSession.REGULAR,
        open=Decimal("100"),
        high=Decimal("99"),
        low=Decimal("98"),
        close=Decimal("101"),
        volume=Decimal("10"),
    )
    finding = reconcile_bars((bar,), expected_interval=timedelta(minutes=1))[0]
    assessment = assess_reconciliation(
        finding,
        provider="ALPACA",
        dataset="price_bars",
        observed_at=NOW,
        policy_version="data-quality-v1",
    )

    assert finding.kind is ReconciliationKind.OHLC_INVALID
    assert assessment.dimension is QualityDimension.RECONCILIATION
    assert assessment.status is QualityStatus.FAIL
    assert assessment.conflict is True
    assert assessment.details["kind"] == "OHLC_INVALID"
