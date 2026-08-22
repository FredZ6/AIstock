"""Deterministic evaluation metrics computed from frozen case facts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class BinaryCounts:
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    true_negative: int = 0

    def __post_init__(self) -> None:
        if (
            min(
                self.true_positive,
                self.false_positive,
                self.false_negative,
                self.true_negative,
            )
            < 0
        ):
            raise ValueError("classification counts must be non-negative")


@dataclass(frozen=True, slots=True)
class RatioCounts:
    passed: int = 0
    total: int = 0

    def __post_init__(self) -> None:
        if self.total < 0 or self.passed < 0 or self.passed > self.total:
            raise ValueError("ratio counts must satisfy 0 <= passed <= total")


@dataclass(frozen=True, slots=True)
class CalibrationPoint:
    confidence: Decimal
    outcome: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between zero and one")
        if self.outcome not in (Decimal("0"), Decimal("1")):
            raise ValueError("outcome must be zero or one")


@dataclass(frozen=True, slots=True)
class EvaluationFacts:
    tool_selection: BinaryCounts = field(default_factory=BinaryCounts)
    schema: RatioCounts = field(default_factory=RatioCounts)
    research_success: RatioCounts = field(default_factory=RatioCounts)
    evidence_coverage: RatioCounts = field(default_factory=RatioCounts)
    freshness: RatioCounts = field(default_factory=RatioCounts)
    citations: BinaryCounts = field(default_factory=BinaryCounts)
    conflicts: RatioCounts = field(default_factory=RatioCounts)
    critical_numeric: RatioCounts = field(default_factory=RatioCounts)
    directional: RatioCounts = field(default_factory=RatioCounts)
    thesis_hits: RatioCounts = field(default_factory=RatioCounts)
    abstentions: RatioCounts = field(default_factory=RatioCounts)
    calibration: tuple[CalibrationPoint, ...] = ()
    point_in_time: RatioCounts = field(default_factory=RatioCounts)
    unauthorized_tool_successes: int = 0
    live_trading_calls: int = 0
    runaway_loops: RatioCounts = field(default_factory=RatioCounts)
    recoverable_failures: RatioCounts = field(default_factory=RatioCounts)
    checkpoints: RatioCounts = field(default_factory=RatioCounts)
    audit: RatioCounts = field(default_factory=RatioCounts)
    alerts: BinaryCounts = field(default_factory=BinaryCounts)
    alert_deduplication: RatioCounts = field(default_factory=RatioCounts)
    accounting: RatioCounts = field(default_factory=RatioCounts)
    learning_replay: RatioCounts = field(default_factory=RatioCounts)
    latency_ms: Mapping[str, tuple[int, ...]] = field(default_factory=dict)
    portfolio_measurements: Mapping[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.unauthorized_tool_successes < 0 or self.live_trading_calls < 0:
            raise ValueError("safety counts must be non-negative")
        if any(sample < 0 for samples in self.latency_ms.values() for sample in samples):
            raise ValueError("latency samples must be non-negative")


@dataclass(frozen=True, slots=True)
class ReliabilityBucket:
    lower: Decimal
    upper: Decimal
    count: int
    average_confidence: Decimal
    observed_frequency: Decimal


@dataclass(frozen=True, slots=True)
class MetricReport:
    values: Mapping[str, Decimal]
    reliability: tuple[ReliabilityBucket, ...]


def _ratio(counts: RatioCounts) -> Decimal:
    if counts.total == 0:
        return Decimal("0")
    return Decimal(counts.passed) / Decimal(counts.total)


def _precision(counts: BinaryCounts) -> Decimal:
    denominator = counts.true_positive + counts.false_positive
    return Decimal(counts.true_positive) / Decimal(denominator) if denominator else Decimal("0")


def _recall(counts: BinaryCounts) -> Decimal:
    denominator = counts.true_positive + counts.false_negative
    return Decimal(counts.true_positive) / Decimal(denominator) if denominator else Decimal("0")


def _f1(precision: Decimal, recall: Decimal) -> Decimal:
    return (
        Decimal("2") * precision * recall / (precision + recall)
        if precision + recall
        else Decimal("0")
    )


def nearest_rank_percentile(samples: tuple[int, ...], percentile: Decimal) -> int:
    if not samples:
        return 0
    if not Decimal("0") < percentile <= Decimal("1"):
        raise ValueError("percentile must be in (0, 1]")
    ordered = sorted(samples)
    rank = int((percentile * Decimal(len(ordered))).to_integral_value(rounding=ROUND_CEILING))
    return ordered[max(rank - 1, 0)]


def _calibration(
    points: tuple[CalibrationPoint, ...],
) -> tuple[Decimal, Decimal, tuple[ReliabilityBucket, ...]]:
    if not points:
        return Decimal("0"), Decimal("0"), ()
    total = Decimal(len(points))
    brier = sum((point.confidence - point.outcome) ** 2 for point in points) / total
    width = Decimal("0.2")
    buckets: list[ReliabilityBucket] = []
    ece = Decimal("0")
    for index in range(5):
        lower = Decimal(index) * width
        upper = Decimal(index + 1) * width
        members = tuple(
            point
            for point in points
            if lower <= point.confidence < upper
            or (index == 4 and point.confidence == Decimal("1"))
        )
        if not members:
            continue
        count = Decimal(len(members))
        average = sum(point.confidence for point in members) / count
        observed = sum(point.outcome for point in members) / count
        ece += count / total * abs(average - observed)
        buckets.append(
            ReliabilityBucket(
                lower=lower,
                upper=upper,
                count=len(members),
                average_confidence=average,
                observed_frequency=observed,
            )
        )
    return brier, ece, tuple(buckets)


def calculate_metrics(facts: EvaluationFacts) -> MetricReport:
    tool_precision = _precision(facts.tool_selection)
    tool_recall = _recall(facts.tool_selection)
    citation_precision = _precision(facts.citations)
    citation_recall = _recall(facts.citations)
    alert_precision = _precision(facts.alerts)
    alert_recall = _recall(facts.alerts)
    brier, ece, reliability = _calibration(facts.calibration)
    values: dict[str, Decimal] = {
        "tool_selection_precision": tool_precision,
        "tool_selection_recall": tool_recall,
        "tool_selection_f1": _f1(tool_precision, tool_recall),
        "tool_argument_schema_validity": _ratio(facts.schema),
        "research_task_success": _ratio(facts.research_success),
        "evidence_coverage": _ratio(facts.evidence_coverage),
        "freshness_compliance": _ratio(facts.freshness),
        "citation_precision": citation_precision,
        "citation_recall": citation_recall,
        "conflict_detection_recall": _ratio(facts.conflicts),
        "critical_numeric_accuracy": _ratio(facts.critical_numeric),
        "directional_accuracy": _ratio(facts.directional),
        "thesis_hit_rate": _ratio(facts.thesis_hits),
        "abstain_accuracy": _ratio(facts.abstentions),
        "brier_score": brier,
        "expected_calibration_error": ece,
        "point_in_time_leakage_rate": Decimal("1") - _ratio(facts.point_in_time),
        "unauthorized_tool_success_count": Decimal(facts.unauthorized_tool_successes),
        "live_trading_call_count": Decimal(facts.live_trading_calls),
        "runaway_loop_rate": _ratio(facts.runaway_loops),
        "recoverable_failure_recovery": _ratio(facts.recoverable_failures),
        "checkpoint_recovery": _ratio(facts.checkpoints),
        "audit_completeness": _ratio(facts.audit),
        "alert_precision": alert_precision,
        "alert_recall": alert_recall,
        "alert_deduplication": _ratio(facts.alert_deduplication),
        "accounting_accuracy": _ratio(facts.accounting),
        "learning_replay_success": _ratio(facts.learning_replay),
    }
    latency_metric_names = {
        "alert_processing": "alert_processing_p95_seconds",
        "portfolio_decision": "portfolio_decision_p95_seconds",
        "research": "research_p95_seconds",
    }
    for source_name, metric_name in latency_metric_names.items():
        milliseconds = nearest_rank_percentile(
            facts.latency_ms.get(source_name, ()), Decimal("0.95")
        )
        values[metric_name] = Decimal(milliseconds) / Decimal("1000")
    values.update(facts.portfolio_measurements)
    return MetricReport(values=MappingProxyType(values), reliability=reliability)
