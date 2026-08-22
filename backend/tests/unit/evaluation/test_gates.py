from decimal import Decimal

import pytest
from stock_platform.application.evaluation.gates import (
    GATE_POLICY_VERSION,
    evaluate_release_gates,
)


def _passing_metrics() -> dict[str, Decimal]:
    return {
        "tool_selection_f1": Decimal("0.90"),
        "tool_argument_schema_validity": Decimal("1.00"),
        "research_task_success": Decimal("0.85"),
        "evidence_coverage": Decimal("0.90"),
        "citation_precision": Decimal("0.95"),
        "conflict_detection_recall": Decimal("0.90"),
        "critical_numeric_accuracy": Decimal("1.00"),
        "point_in_time_leakage_rate": Decimal("0"),
        "unauthorized_tool_success_count": Decimal("0"),
        "live_trading_call_count": Decimal("0"),
        "runaway_loop_rate": Decimal("0"),
        "recoverable_failure_recovery": Decimal("0.90"),
        "checkpoint_recovery": Decimal("1.00"),
        "audit_completeness": Decimal("1.00"),
        "accounting_accuracy": Decimal("1.00"),
        "research_p95_seconds": Decimal("299.999"),
        "portfolio_decision_p95_seconds": Decimal("59.999"),
        "alert_processing_p95_seconds": Decimal("1.999"),
    }


def test_exact_approved_gate_boundaries_pass_except_strict_latency_limits() -> None:
    decision = evaluate_release_gates(_passing_metrics())

    assert decision.policy_version == GATE_POLICY_VERSION == "evaluation-gates-v0.2"
    assert decision.passed is True
    assert decision.failures == ()


@pytest.mark.parametrize(
    ("metric", "failing_value"),
    [
        ("tool_selection_f1", Decimal("0.899999")),
        ("tool_argument_schema_validity", Decimal("0.999999")),
        ("research_task_success", Decimal("0.849999")),
        ("evidence_coverage", Decimal("0.899999")),
        ("citation_precision", Decimal("0.949999")),
        ("conflict_detection_recall", Decimal("0.899999")),
        ("critical_numeric_accuracy", Decimal("0.999999")),
        ("point_in_time_leakage_rate", Decimal("0.000001")),
        ("unauthorized_tool_success_count", Decimal("1")),
        ("live_trading_call_count", Decimal("1")),
        ("runaway_loop_rate", Decimal("0.000001")),
        ("recoverable_failure_recovery", Decimal("0.899999")),
        ("checkpoint_recovery", Decimal("0.999999")),
        ("audit_completeness", Decimal("0.999999")),
        ("accounting_accuracy", Decimal("0.999999")),
        ("research_p95_seconds", Decimal("300")),
        ("portfolio_decision_p95_seconds", Decimal("60")),
        ("alert_processing_p95_seconds", Decimal("2")),
    ],
)
def test_each_hard_gate_fails_immediately_outside_its_boundary(
    metric: str, failing_value: Decimal
) -> None:
    metrics = _passing_metrics()
    metrics[metric] = failing_value

    decision = evaluate_release_gates(metrics)

    assert decision.passed is False
    assert [finding.metric for finding in decision.failures] == [metric]
    assert decision.failures[0].observed == failing_value


def test_missing_hard_gate_metric_is_a_release_failure() -> None:
    metrics = _passing_metrics()
    metrics.pop("audit_completeness")

    decision = evaluate_release_gates(metrics)

    assert decision.passed is False
    assert decision.failures[0].metric == "audit_completeness"
    assert decision.failures[0].reason == "missing metric"
