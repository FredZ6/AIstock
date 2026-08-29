import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[3]


def test_fixture_demo_covers_the_interview_acceptance_scenario() -> None:
    environment = os.environ | {
        "PYTHONPATH": str(REPO_ROOT / "backend" / "src"),
        "UV_CACHE_DIR": str(REPO_ROOT / ".uv-cache"),
    }
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "demo_scenario.py")],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads(completed.stdout)
    assert manifest == {
        "alert": {
            "deterministic": True,
            "triggered": True,
        },
        "evaluation": {
            "artifact": "evals/reports/latest/summary.json",
        },
        "lesson_approval": {
            "action": "APPROVE",
            "actor_id": "demo-human-reviewer",
            "persistence": "ROLLBACK_PROBE",
        },
        "mode": "fixture",
        "policy": {
            "candidate_status": "CANDIDATE",
            "unapproved_activation_rejected": True,
        },
        "portfolio": {
            "benchmark_count": 4,
            "drawdown": "-0.018",
            "fill_count": 1,
            "nav": "100425.18",
            "risk_rejection": "REJECTED",
        },
        "product_boundary": "research and paper trading only",
        "research": {
            "conflict_count": 1,
            "opinion": "ABSTAIN",
            "symbol": "NVDA",
        },
        "weekly_review": {
            "candidate_lesson_count": 1,
            "matured_outcome_count": 1,
        },
    }


def test_smoke_script_emits_reproducible_scenario_and_eval_artifacts(tmp_path: Path) -> None:
    report_directory = tmp_path / "report"
    environment = os.environ | {
        "PYTHONPATH": str(REPO_ROOT / "backend" / "src"),
        "SMOKE_REPORT_DIR": str(report_directory),
        "SMOKE_SKIP_BROWSER": "1",
        "SMOKE_SKIP_SEED": "1",
        "UV_CACHE_DIR": str(REPO_ROOT / ".uv-cache"),
    }
    completed = subprocess.run(
        [str(REPO_ROOT / "scripts" / "smoke.sh")],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (
        json.loads((report_directory / "demo-manifest.json").read_text(encoding="utf-8"))[
            "product_boundary"
        ]
        == "research and paper trading only"
    )
    summary = json.loads((report_directory / "summary.json").read_text(encoding="utf-8"))
    assert summary["dataset"] == {
        "case_count": 200,
        "dataset_version": "eval-v0.2.0",
        "layers": {"L0": 20, "L1": 20, "L2": 40, "L3": 30, "L4": 20, "L5": 20, "L6": 20, "L7": 30},
        "mode": "fixture",
    }
    assert summary["release"]["passed"] is True
    assert (report_directory / "cases.jsonl").is_file()
    assert (report_directory / "junit.xml").is_file()
    assert (report_directory / "report.html").is_file()


def test_interview_dossier_is_complete_and_uses_only_measured_values(tmp_path: Path) -> None:
    required_documents = (
        "docs/product-requirements.md",
        "docs/architecture.md",
        "docs/testing.md",
        "docs/demo-script.md",
        "docs/interview-guide.md",
        "docs/resume-metrics.md",
    )
    for relative_path in required_documents:
        assert (REPO_ROOT / relative_path).is_file(), relative_path

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for heading in (
        "## Product boundary",
        "## Architecture",
        "## Quick start",
        "## Provider modes and data licensing",
        "## Security",
        "## Evaluation",
        "## Limitations",
    ):
        assert heading in readme

    demo = (REPO_ROOT / "docs" / "demo-script.md").read_text(encoding="utf-8")
    for phrase in (
        "Ten-minute walkthrough",
        "NVDA research",
        "evidence conflict",
        "deterministic alert",
        "Risk Reject",
        "NAV and drawdown",
        "Weekly Review",
        "unapproved activation",
        "Offline evaluation report",
        "01-research.png",
        "04-eval.png",
    ):
        assert phrase in demo

    report_directory = tmp_path / "measured"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_offline_eval.py"),
            "--dataset",
            "evals/datasets",
            "--baseline",
            "evals/baselines/eval-v0.2.0.json",
            "--output",
            str(report_directory),
        ],
        cwd=REPO_ROOT,
        env=os.environ
        | {
            "PYTHONPATH": str(REPO_ROOT / "backend" / "src"),
            "UV_CACHE_DIR": str(REPO_ROOT / ".uv-cache"),
        },
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads((report_directory / "summary.json").read_text(encoding="utf-8"))
    resume = (REPO_ROOT / "docs" / "resume-metrics.md").read_text(encoding="utf-8")
    assert "Source: `evals/reports/latest/summary.json`" in resume
    assert f"Dataset: `{summary['dataset']['dataset_version']}`" in resume
    assert f"Cases: `{summary['dataset']['case_count']}`" in resume
    assert f"Tool selection F1: `{summary['metrics']['tool_selection_f1']['value']}`" in resume
    assert (
        f"Research task success: `{summary['metrics']['research_task_success']['value']}`" in resume
    )
    assert f"Evidence coverage: `{summary['metrics']['evidence_coverage']['value']}`" in resume
    assert "Hardware: —" in resume
    assert "Model: —" in resume
    assert "not production performance" in resume


def test_seed_target_starts_required_stores_and_migrates_before_loading_fixtures() -> None:
    completed = subprocess.run(
        ["make", "--dry-run", "seed"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    commands = completed.stdout
    start = commands.index("docker compose up -d --wait postgres minio")
    migrate = commands.index("alembic -c backend/alembic.ini upgrade head")
    seed = commands.index("python scripts/seed_demo.py")
    assert start < migrate < seed
