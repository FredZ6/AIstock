from decimal import Decimal

from stock_platform.application.evaluation.metrics import (
    BinaryCounts,
    CalibrationPoint,
    EvaluationFacts,
    RatioCounts,
    calculate_metrics,
    nearest_rank_percentile,
)


def test_classification_and_quality_metrics_use_exact_decimal_arithmetic() -> None:
    report = calculate_metrics(
        EvaluationFacts(
            tool_selection=BinaryCounts(true_positive=8, false_positive=2, false_negative=2),
            schema=RatioCounts(passed=10, total=10),
            research_success=RatioCounts(passed=9, total=10),
            evidence_coverage=RatioCounts(passed=9, total=10),
            freshness=RatioCounts(passed=8, total=10),
            citations=BinaryCounts(true_positive=19, false_positive=1, false_negative=1),
            conflicts=RatioCounts(passed=9, total=10),
            critical_numeric=RatioCounts(passed=10, total=10),
        )
    )

    assert report.values["tool_selection_precision"] == Decimal("0.8")
    assert report.values["tool_selection_recall"] == Decimal("0.8")
    assert report.values["tool_selection_f1"] == Decimal("0.8")
    assert report.values["tool_argument_schema_validity"] == Decimal("1")
    assert report.values["research_task_success"] == Decimal("0.9")
    assert report.values["evidence_coverage"] == Decimal("0.9")
    assert report.values["freshness_compliance"] == Decimal("0.8")
    assert report.values["citation_precision"] == Decimal("0.95")
    assert report.values["citation_recall"] == Decimal("0.95")
    assert report.values["conflict_detection_recall"] == Decimal("0.9")
    assert report.values["critical_numeric_accuracy"] == Decimal("1")


def test_calibration_direction_thesis_and_abstention_metrics_are_reproducible() -> None:
    report = calculate_metrics(
        EvaluationFacts(
            directional=RatioCounts(passed=3, total=4),
            thesis_hits=RatioCounts(passed=4, total=5),
            abstentions=RatioCounts(passed=2, total=2),
            calibration=(
                CalibrationPoint(confidence=Decimal("0.9"), outcome=Decimal("1")),
                CalibrationPoint(confidence=Decimal("0.8"), outcome=Decimal("1")),
                CalibrationPoint(confidence=Decimal("0.2"), outcome=Decimal("0")),
                CalibrationPoint(confidence=Decimal("0.1"), outcome=Decimal("0")),
            ),
        )
    )

    assert report.values["directional_accuracy"] == Decimal("0.75")
    assert report.values["thesis_hit_rate"] == Decimal("0.8")
    assert report.values["abstain_accuracy"] == Decimal("1")
    assert report.values["brier_score"] == Decimal("0.025")
    assert report.values["expected_calibration_error"] == Decimal("0.15")
    assert [(bucket.lower, bucket.upper, bucket.count) for bucket in report.reliability] == [
        (Decimal("0"), Decimal("0.2"), 1),
        (Decimal("0.2"), Decimal("0.4"), 1),
        (Decimal("0.8"), Decimal("1.0"), 2),
    ]


def test_safety_alert_portfolio_learning_and_latency_metrics_remain_separate() -> None:
    report = calculate_metrics(
        EvaluationFacts(
            point_in_time=RatioCounts(passed=100, total=100),
            unauthorized_tool_successes=0,
            live_trading_calls=0,
            runaway_loops=RatioCounts(passed=0, total=40),
            recoverable_failures=RatioCounts(passed=9, total=10),
            checkpoints=RatioCounts(passed=10, total=10),
            audit=RatioCounts(passed=10, total=10),
            alerts=BinaryCounts(true_positive=18, false_positive=2, false_negative=2),
            alert_deduplication=RatioCounts(passed=20, total=20),
            accounting=RatioCounts(passed=20, total=20),
            learning_replay=RatioCounts(passed=19, total=20),
            latency_ms={
                "alert_processing": tuple(range(1, 21)),
                "portfolio_decision": (59_000, 60_000),
                "research": (299_000, 300_000),
            },
            portfolio_measurements={
                "portfolio_total_return": Decimal("-0.12"),
                "portfolio_sharpe": Decimal("-0.8"),
            },
        )
    )

    assert report.values["point_in_time_leakage_rate"] == Decimal("0")
    assert report.values["unauthorized_tool_success_count"] == Decimal("0")
    assert report.values["live_trading_call_count"] == Decimal("0")
    assert report.values["runaway_loop_rate"] == Decimal("0")
    assert report.values["recoverable_failure_recovery"] == Decimal("0.9")
    assert report.values["checkpoint_recovery"] == Decimal("1")
    assert report.values["audit_completeness"] == Decimal("1")
    assert report.values["alert_precision"] == Decimal("0.9")
    assert report.values["alert_recall"] == Decimal("0.9")
    assert report.values["alert_deduplication"] == Decimal("1")
    assert report.values["accounting_accuracy"] == Decimal("1")
    assert report.values["learning_replay_success"] == Decimal("0.95")
    assert report.values["alert_processing_p95_seconds"] == Decimal("0.019")
    assert report.values["portfolio_decision_p95_seconds"] == Decimal("60")
    assert report.values["research_p95_seconds"] == Decimal("300")
    assert report.values["portfolio_total_return"] == Decimal("-0.12")
    assert report.values["portfolio_sharpe"] == Decimal("-0.8")


def test_nearest_rank_percentile_is_defined_for_empty_and_unsorted_samples() -> None:
    assert nearest_rank_percentile((), Decimal("0.95")) == 0
    assert nearest_rank_percentile((5, 1, 4, 2, 3), Decimal("0.8")) == 4
