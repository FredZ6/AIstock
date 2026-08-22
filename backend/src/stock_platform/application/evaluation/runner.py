"""Offline evaluation runner over frozen, point-in-time-safe fixture cases."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

from stock_platform.application.evaluation.gates import ReleaseDecision, evaluate_release_gates
from stock_platform.application.evaluation.metrics import (
    BinaryCounts,
    CalibrationPoint,
    EvaluationFacts,
    MetricReport,
    RatioCounts,
    calculate_metrics,
)
from stock_platform.application.evaluation.report import load_baseline, write_reports
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.evaluation import EvalCase, load_corpus


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    cases: tuple[EvalCase, ...]
    metrics: MetricReport
    release_decision: ReleaseDecision


def _required_bool(output: Mapping[str, Any], name: str) -> bool:
    value = output.get(name)
    if type(value) is not bool:
        raise ValueError(f"raw_output.{name} must be a boolean")
    return value


def _binary(cases: tuple[EvalCase, ...], expected: str, actual: str) -> BinaryCounts:
    counts = [0, 0, 0, 0]
    for case in cases:
        wanted = _required_bool(case.raw_output, expected)
        observed = _required_bool(case.raw_output, actual)
        index = {(True, True): 0, (False, True): 1, (True, False): 2, (False, False): 3}[
            (wanted, observed)
        ]
        counts[index] += 1
    return BinaryCounts(*counts)


def _ratio(cases: tuple[EvalCase, ...], field: str) -> RatioCounts:
    return RatioCounts(
        passed=sum(_required_bool(case.raw_output, field) for case in cases),
        total=len(cases),
    )


def _point_in_time(cases: tuple[EvalCase, ...]) -> RatioCounts:
    passed = 0
    for case in cases:
        values = case.raw_output.get("available_at")
        if not isinstance(values, tuple) or not values:
            raise ValueError("raw_output.available_at must be a non-empty frozen sequence")
        available_at: list[datetime] = []
        for value in values:
            if not isinstance(value, str):
                raise ValueError("raw_output.available_at values must be aware ISO strings")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            available_at.append(require_aware(parsed))
        passed += all(timestamp <= case.as_of for timestamp in available_at)
    return RatioCounts(passed=passed, total=len(cases))


def _average_measurements(cases: tuple[EvalCase, ...]) -> dict[str, Decimal]:
    if not cases:
        return {}
    names = tuple(sorted(cases[0].raw_output.get("portfolio_metrics", {})))
    values: dict[str, Decimal] = {}
    for name in names:
        samples = [Decimal(str(case.raw_output["portfolio_metrics"][name])) for case in cases]
        values[name] = sum(samples) / Decimal(len(samples))
    return values


def _facts(cases: tuple[EvalCase, ...]) -> EvaluationFacts:
    by_category = {
        category: tuple(case for case in cases if case.category == category)
        for category in (
            "tool",
            "research",
            "evidence",
            "security",
            "alert",
            "portfolio",
            "learning",
        )
    }
    tool = by_category["tool"]
    research = by_category["research"]
    evidence = by_category["evidence"]
    security = by_category["security"]
    alerts = by_category["alert"]
    portfolio = by_category["portfolio"]
    learning = by_category["learning"]
    abstentions = tuple(
        case for case in research if _required_bool(case.raw_output, "abstain_required")
    )
    recoveries = tuple(
        case for case in security if _required_bool(case.raw_output, "recoverable_failure")
    )
    checkpoints = tuple(
        case
        for case in research + security
        if _required_bool(case.raw_output, "checkpoint_expected")
    )
    return EvaluationFacts(
        tool_selection=_binary(tool, "expected_positive", "predicted_positive"),
        schema=_ratio(tool, "schema_valid"),
        research_success=_ratio(research, "success"),
        evidence_coverage=_ratio(evidence, "evidence_present"),
        freshness=_ratio(evidence, "freshness_valid"),
        citations=_binary(evidence, "citation_expected", "citation_present"),
        conflicts=_ratio(
            tuple(
                case for case in evidence if _required_bool(case.raw_output, "conflict_expected")
            ),
            "conflict_detected",
        ),
        critical_numeric=_ratio(evidence, "numeric_correct"),
        directional=_ratio(research, "direction_correct"),
        thesis_hits=_ratio(research, "thesis_hit"),
        abstentions=_ratio(abstentions, "abstained"),
        calibration=tuple(
            CalibrationPoint(
                confidence=Decimal(str(case.raw_output["confidence"])),
                outcome=Decimal(str(case.raw_output["outcome"])),
            )
            for case in research
        ),
        point_in_time=_point_in_time(cases),
        unauthorized_tool_successes=sum(
            _required_bool(case.raw_output, "unauthorized_tool_succeeded") for case in security
        ),
        live_trading_calls=sum(
            _required_bool(case.raw_output, "live_trading_called") for case in security
        ),
        runaway_loops=RatioCounts(
            passed=sum(_required_bool(case.raw_output, "runaway_loop") for case in research),
            total=len(research),
        ),
        recoverable_failures=_ratio(recoveries, "recovered"),
        checkpoints=_ratio(checkpoints, "checkpoint_recovered"),
        audit=_ratio(cases, "audit_complete"),
        alerts=_binary(alerts, "expected_trigger", "actual_trigger"),
        alert_deduplication=_ratio(alerts, "dedup_ok"),
        accounting=_ratio(portfolio, "accounting_ok"),
        learning_replay=_ratio(learning, "replay_passed"),
        latency_ms=MappingProxyType(
            {
                "alert_processing": tuple(case.latency_ms for case in alerts),
                "portfolio_decision": tuple(case.latency_ms for case in portfolio),
                "research": tuple(case.latency_ms for case in research),
            }
        ),
        portfolio_measurements=MappingProxyType(_average_measurements(portfolio)),
    )


def _metric_evidence(
    cases: tuple[EvalCase, ...], metrics: MetricReport
) -> dict[str, tuple[EvalCase, ...]]:
    category_by_metric = {
        "tool_selection_precision": "tool",
        "tool_selection_recall": "tool",
        "tool_selection_f1": "tool",
        "tool_argument_schema_validity": "tool",
        "research_task_success": "research",
        "directional_accuracy": "research",
        "thesis_hit_rate": "research",
        "abstain_accuracy": "research",
        "brier_score": "research",
        "expected_calibration_error": "research",
        "research_p95_seconds": "research",
        "evidence_coverage": "evidence",
        "freshness_compliance": "evidence",
        "citation_precision": "evidence",
        "citation_recall": "evidence",
        "conflict_detection_recall": "evidence",
        "critical_numeric_accuracy": "evidence",
        "unauthorized_tool_success_count": "security",
        "live_trading_call_count": "security",
        "recoverable_failure_recovery": "security",
        "checkpoint_recovery": ("research", "security"),
        "alert_precision": "alert",
        "alert_recall": "alert",
        "alert_deduplication": "alert",
        "alert_processing_p95_seconds": "alert",
        "accounting_accuracy": "portfolio",
        "portfolio_decision_p95_seconds": "portfolio",
        "learning_replay_success": "learning",
    }
    portfolio_measurements = (
        set(metrics.values)
        - set(category_by_metric)
        - {
            "audit_completeness",
            "point_in_time_leakage_rate",
            "runaway_loop_rate",
        }
    )
    category_by_metric.update({name: "portfolio" for name in portfolio_measurements})
    evidence: dict[str, tuple[EvalCase, ...]] = {}
    for metric in metrics.values:
        category = category_by_metric.get(metric)
        if metric == "runaway_loop_rate":
            category = "research"
        selected = tuple(
            case
            for case in cases
            if category is None
            or case.category == category
            or isinstance(category, tuple)
            and case.category in category
        )
        if not selected:
            raise ValueError(f"metric {metric} has no supporting cases")
        evidence[metric] = selected
    return evidence


def run_evaluation(
    dataset_dir: Path, output_dir: Path, *, baseline_path: Path | None = None
) -> EvaluationRun:
    _, cases = load_corpus(dataset_dir)
    metrics = calculate_metrics(_facts(cases))
    decision = evaluate_release_gates(metrics.values)
    evidence = _metric_evidence(cases, metrics)
    baseline = load_baseline(baseline_path) if baseline_path is not None else None
    write_reports(output_dir, cases, metrics, decision, evidence, baseline)
    return EvaluationRun(cases=cases, metrics=metrics, release_decision=decision)
