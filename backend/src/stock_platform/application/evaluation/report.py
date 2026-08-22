"""Deterministic, machine- and human-readable offline evaluation reports."""

from __future__ import annotations

import html
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from pydantic import BaseModel, ConfigDict, StrictStr

from stock_platform.application.evaluation.gates import ReleaseDecision
from stock_platform.application.evaluation.metrics import MetricReport
from stock_platform.domain.evaluation import EvalCase


class EvaluationBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_version: StrictStr
    dataset_version: StrictStr
    metrics: dict[StrictStr, StrictStr]
    provenance: StrictStr

    def decimal_metrics(self) -> dict[str, Decimal]:
        values = {name: Decimal(value) for name, value in self.metrics.items()}
        if any(not value.is_finite() for value in values.values()):
            raise ValueError("baseline metrics must be finite Decimal strings")
        return values


def load_baseline(path: Path) -> EvaluationBaseline:
    return EvaluationBaseline.model_validate_json(path.read_text(encoding="utf-8"))


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def build_summary(
    cases: Sequence[EvalCase],
    metrics: MetricReport,
    decision: ReleaseDecision,
    evidence: Mapping[str, Sequence[EvalCase]],
    baseline: EvaluationBaseline | None,
) -> dict[str, object]:
    versions = {case.dataset_version for case in cases}
    if len(versions) != 1:
        raise ValueError("evaluation dataset must have exactly one version")
    summary: dict[str, object] = {
        "dataset": {
            "case_count": len(cases),
            "dataset_version": next(iter(versions)),
            "layers": dict(sorted(Counter(case.layer.value for case in cases).items())),
            "mode": "fixture",
        },
        "release": {
            "passed": decision.passed,
            "policy_version": decision.policy_version,
            "findings": [
                {
                    "comparison": finding.comparison.value,
                    "metric": finding.metric,
                    "observed": (
                        _decimal(finding.observed) if finding.observed is not None else None
                    ),
                    "passed": finding.passed,
                    "reason": finding.reason,
                    "threshold": _decimal(finding.threshold),
                }
                for finding in decision.findings
            ],
        },
        "metrics": {
            name: {
                "case_hashes": [case.case_hash for case in evidence[name]],
                "case_ids": [case.case_id for case in evidence[name]],
                "value": _decimal(value),
            }
            for name, value in sorted(metrics.values.items())
        },
        "reliability": [
            {
                "average_confidence": _decimal(bucket.average_confidence),
                "count": bucket.count,
                "lower": _decimal(bucket.lower),
                "observed_frequency": _decimal(bucket.observed_frequency),
                "upper": _decimal(bucket.upper),
            }
            for bucket in metrics.reliability
        ],
    }
    if baseline is not None:
        if baseline.dataset_version != next(iter(versions)):
            raise ValueError("baseline dataset version does not match current corpus")
        baseline_metrics = baseline.decimal_metrics()
        if set(baseline_metrics) != set(metrics.values):
            raise ValueError("baseline metrics do not match current metric contract")
        summary["baseline"] = {
            "baseline_version": baseline.baseline_version,
            "dataset_version": baseline.dataset_version,
            "provenance": baseline.provenance,
            "comparisons": {
                name: {
                    "baseline": _decimal(baseline_metrics[name]),
                    "current": _decimal(metrics.values[name]),
                    "delta": _decimal(metrics.values[name] - baseline_metrics[name]),
                }
                for name in sorted(metrics.values)
            },
        }
    return summary


def _write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def write_reports(
    output_dir: Path,
    cases: Sequence[EvalCase],
    metrics: MetricReport,
    decision: ReleaseDecision,
    evidence: Mapping[str, Sequence[EvalCase]],
    baseline: EvaluationBaseline | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(cases, metrics, decision, evidence, baseline)
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    cases_text = "".join(
        json.dumps(case.hashed_payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
        for case in cases
    )

    suite = Element(
        "testsuite",
        name="offline-release-gates",
        tests=str(len(decision.findings)),
        failures=str(len(decision.failures)),
    )
    for finding in decision.findings:
        test = SubElement(suite, "testcase", classname="release.gate", name=finding.metric)
        if not finding.passed:
            failure = SubElement(test, "failure", message=finding.reason)
            failure.text = (
                f"observed={finding.observed}; {finding.comparison.value} "
                f"threshold={finding.threshold}"
            )
    junit_text = tostring(suite, encoding="unicode", short_empty_elements=True) + "\n"
    report_text = (
        '<!doctype html><html><head><meta charset="utf-8">'
        "<title>M7 offline evaluation</title></head><body>"
        f"<h1>Release gates: {'PASS' if decision.passed else 'FAIL'}</h1>"
        "<p>Frozen fixture evaluation; investment returns are measurements, not gates.</p>"
        f"<pre>{html.escape(summary_text)}</pre></body></html>\n"
    )

    _write(output_dir / "summary.json", summary_text)
    _write(output_dir / "cases.jsonl", cases_text)
    _write(output_dir / "junit.xml", junit_text)
    _write(output_dir / "report.html", report_text)
