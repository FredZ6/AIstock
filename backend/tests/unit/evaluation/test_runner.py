from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest
from stock_platform.application.evaluation.runner import run_evaluation
from stock_platform.domain.evaluation import (
    case_payload_hash,
    corpus_sha256,
    file_sha256,
    load_cases,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DATASET_DIR = REPO_ROOT / "evals" / "datasets"
BASELINE_PATH = REPO_ROOT / "evals" / "baselines" / "eval-v0.2.0.json"
REPORT_NAMES = ("cases.jsonl", "junit.xml", "report.html", "summary.json")


def _reseal_manifest(dataset: Path) -> None:
    manifest_path = dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = {path.name: file_sha256(path) for path in sorted(dataset.glob("*.jsonl"))}
    manifest["file_sha256"] = hashes
    manifest["corpus_sha256"] = corpus_sha256(hashes)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_public_runner_rejects_an_incomplete_corpus(tmp_path: Path) -> None:
    dataset = tmp_path / "datasets"
    dataset.mkdir()
    for source in sorted(DATASET_DIR.glob("*.jsonl")):
        rows = source.read_text(encoding="utf-8").splitlines()
        selected = rows[1] if source.name == "tool.jsonl" else rows[0]
        (dataset / source.name).write_text(selected + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest"):
        run_evaluation(dataset, tmp_path / "reports")


def test_frozen_dataset_has_the_locked_200_case_distribution() -> None:
    cases = load_cases(sorted(DATASET_DIR.glob("*.jsonl")))

    assert len(cases) == 200
    assert Counter(case.category for case in cases) == {
        "alert": 20,
        "evidence": 30,
        "learning": 20,
        "portfolio": 20,
        "research": 40,
        "security": 30,
        "tool": 40,
    }
    assert all((DATASET_DIR / case.fixture_manifest).is_file() for case in cases)
    evidence = [case for case in cases if case.category == "evidence"]
    alerts = [case for case in cases if case.category == "alert"]
    assert sum(not case.raw_output["citation_expected"] for case in evidence) == 6
    assert sum(not case.raw_output["expected_trigger"] for case in alerts) == 5


def test_fixture_corpus_rejects_calibrated_llm_judges(tmp_path: Path) -> None:
    dataset = tmp_path / "datasets"
    shutil.copytree(DATASET_DIR, dataset)
    tool_path = dataset / "tool.jsonl"
    rows = [json.loads(line) for line in tool_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["judge_kind"] = "CALIBRATED_LLM"
    rows[0]["judge_calibration_version"] = "judge-calibration-v1"
    rows[0]["case_hash"] = case_payload_hash(rows[0])
    tool_path.write_text(
        "".join(f"{json.dumps(row, sort_keys=True, separators=(',', ':'))}\n" for row in rows),
        encoding="utf-8",
    )
    _reseal_manifest(dataset)

    with pytest.raises(ValueError, match="deterministic judge"):
        run_evaluation(dataset, tmp_path / "reports")


def test_runner_emits_four_byte_reproducible_reports_with_case_evidence(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_run = run_evaluation(DATASET_DIR, first, baseline_path=BASELINE_PATH)
    second_run = run_evaluation(DATASET_DIR, second, baseline_path=BASELINE_PATH)

    assert first_run.release_decision.passed is True
    assert second_run.release_decision.passed is True
    for name in REPORT_NAMES:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    summary = json.loads((first / "summary.json").read_text(encoding="utf-8"))
    assert summary["dataset"] == {
        "case_count": 200,
        "dataset_version": "eval-v0.2.0",
        "layers": {
            "L0": 20,
            "L1": 20,
            "L2": 40,
            "L3": 30,
            "L4": 20,
            "L5": 20,
            "L6": 20,
            "L7": 30,
        },
        "mode": "fixture",
    }
    assert summary["release"]["passed"] is True
    assert summary["baseline"]["baseline_version"] == "eval-baseline-v0.2.0"
    assert all(Decimal(item["delta"]) == 0 for item in summary["baseline"]["comparisons"].values())
    assert all(metric["case_ids"] for metric in summary["metrics"].values())
    assert all(metric["case_hashes"] for metric in summary["metrics"].values())
    checkpoint_ids = summary["metrics"]["checkpoint_recovery"]["case_ids"]
    assert {case_id.split("-", maxsplit=1)[0] for case_id in checkpoint_ids} == {
        "research",
        "security",
    }
    assert load_cases([first / "cases.jsonl"]) == first_run.cases


def test_dataset_generator_accepts_an_output_directory_and_is_idempotent(tmp_path: Path) -> None:
    output = tmp_path / "generated"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPO_ROOT / "backend" / "src")
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "generate_eval_datasets.py"),
        "--output",
        str(output),
    ]

    first = subprocess.run(command, env=environment, check=False, capture_output=True, text=True)
    first_bytes = {path.name: path.read_bytes() for path in sorted(output.glob("*.jsonl"))}
    second = subprocess.run(command, env=environment, check=False, capture_output=True, text=True)

    assert first.returncode == second.returncode == 0
    assert len(first_bytes) == 7
    assert first_bytes == {path.name: path.read_bytes() for path in sorted(output.glob("*.jsonl"))}


def test_cli_returns_non_zero_when_a_hard_gate_is_injected(tmp_path: Path) -> None:
    dataset = tmp_path / "datasets"
    output = tmp_path / "reports"
    shutil.copytree(DATASET_DIR, dataset)
    tool_path = dataset / "tool.jsonl"
    rows = [json.loads(line) for line in tool_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["raw_output"]["schema_valid"] = False
    rows[0]["case_hash"] = case_payload_hash(rows[0])
    tool_path.write_text(
        "".join(f"{json.dumps(row, sort_keys=True, separators=(',', ':'))}\n" for row in rows),
        encoding="utf-8",
    )
    _reseal_manifest(dataset)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPO_ROOT / "backend" / "src")

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_offline_eval.py"),
            "--dataset",
            str(dataset),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "tool_argument_schema_validity" in result.stdout
    assert (output / "summary.json").is_file()


def test_runner_derives_point_in_time_leakage_from_available_at(tmp_path: Path) -> None:
    dataset = tmp_path / "datasets"
    shutil.copytree(DATASET_DIR, dataset)
    evidence_path = dataset / "evidence.jsonl"
    rows = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["raw_output"]["available_at"] = ["2026-08-21T20:00:01Z"]
    rows[0]["case_hash"] = case_payload_hash(rows[0])
    evidence_path.write_text(
        "".join(f"{json.dumps(row, sort_keys=True, separators=(',', ':'))}\n" for row in rows),
        encoding="utf-8",
    )
    _reseal_manifest(dataset)

    run = run_evaluation(dataset, tmp_path / "reports")

    assert run.metrics.values["point_in_time_leakage_rate"] > 0
    assert "point_in_time_leakage_rate" in {
        finding.metric for finding in run.release_decision.failures
    }


def test_conflict_recall_uses_only_cases_with_expected_conflicts(tmp_path: Path) -> None:
    dataset = tmp_path / "datasets"
    shutil.copytree(DATASET_DIR, dataset)
    evidence_path = dataset / "evidence.jsonl"
    rows = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["raw_output"]["conflict_expected"] = False
    rows[0]["raw_output"]["conflict_detected"] = False
    rows[0]["case_hash"] = case_payload_hash(rows[0])
    evidence_path.write_text(
        "".join(f"{json.dumps(row, sort_keys=True, separators=(',', ':'))}\n" for row in rows),
        encoding="utf-8",
    )
    _reseal_manifest(dataset)

    run = run_evaluation(dataset, tmp_path / "reports")

    assert run.metrics.values["conflict_detection_recall"] == 1


def test_negative_citation_cases_detect_an_always_cite_regression(tmp_path: Path) -> None:
    dataset = tmp_path / "datasets"
    shutil.copytree(DATASET_DIR, dataset)
    evidence_path = dataset / "evidence.jsonl"
    rows = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if not row["raw_output"]["citation_expected"]:
            row["raw_output"]["citation_present"] = True
            row["case_hash"] = case_payload_hash(row)
    evidence_path.write_text(
        "".join(f"{json.dumps(row, sort_keys=True, separators=(',', ':'))}\n" for row in rows),
        encoding="utf-8",
    )
    _reseal_manifest(dataset)

    run = run_evaluation(dataset, tmp_path / "reports")

    assert run.metrics.values["citation_precision"] == Decimal("0.8")
    assert "citation_precision" in {finding.metric for finding in run.release_decision.failures}


def test_negative_alert_cases_measure_an_always_trigger_regression(tmp_path: Path) -> None:
    dataset = tmp_path / "datasets"
    shutil.copytree(DATASET_DIR, dataset)
    alert_path = dataset / "alert.jsonl"
    rows = [json.loads(line) for line in alert_path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if not row["raw_output"]["expected_trigger"]:
            row["raw_output"]["actual_trigger"] = True
            row["case_hash"] = case_payload_hash(row)
    alert_path.write_text(
        "".join(f"{json.dumps(row, sort_keys=True, separators=(',', ':'))}\n" for row in rows),
        encoding="utf-8",
    )
    _reseal_manifest(dataset)

    run = run_evaluation(dataset, tmp_path / "reports")

    assert run.metrics.values["alert_precision"] == Decimal("0.75")
