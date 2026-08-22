from decimal import Decimal

from stock_platform.application.evaluation.gates import evaluate_release_gates


def test_investment_performance_is_measured_but_never_a_software_release_gate() -> None:
    hard_metrics = {
        "tool_selection_f1": Decimal("1"),
        "tool_argument_schema_validity": Decimal("1"),
        "research_task_success": Decimal("1"),
        "evidence_coverage": Decimal("1"),
        "citation_precision": Decimal("1"),
        "conflict_detection_recall": Decimal("1"),
        "critical_numeric_accuracy": Decimal("1"),
        "point_in_time_leakage_rate": Decimal("0"),
        "unauthorized_tool_success_count": Decimal("0"),
        "live_trading_call_count": Decimal("0"),
        "runaway_loop_rate": Decimal("0"),
        "recoverable_failure_recovery": Decimal("1"),
        "checkpoint_recovery": Decimal("1"),
        "audit_completeness": Decimal("1"),
        "accounting_accuracy": Decimal("1"),
        "research_p95_seconds": Decimal("299"),
        "portfolio_decision_p95_seconds": Decimal("59"),
        "alert_processing_p95_seconds": Decimal("1.9"),
    }
    hard_metrics.update(
        {
            "portfolio_total_return": Decimal("-0.99"),
            "portfolio_sharpe": Decimal("-12"),
            "portfolio_alpha": Decimal("-0.80"),
            "portfolio_win_rate": Decimal("0"),
        }
    )

    decision = evaluate_release_gates(hard_metrics)

    assert decision.passed is True
    investment_metrics = {
        "portfolio_alpha",
        "portfolio_sharpe",
        "portfolio_total_return",
        "portfolio_win_rate",
    }
    assert investment_metrics.isdisjoint(finding.metric for finding in decision.findings)
