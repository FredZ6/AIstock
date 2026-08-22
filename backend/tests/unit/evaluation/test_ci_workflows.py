from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


def _workflow(name: str) -> str:
    return (WORKFLOW_DIR / name).read_text(encoding="utf-8")


def test_pr_workflow_is_read_only_fast_and_runs_fixture_evaluation_once() -> None:
    text = _workflow("pr.yml")

    assert "permissions:\n  contents: read" in text
    assert "timeout-minutes: 10" in text
    assert text.count("scripts/run_offline_eval.py") == 1
    assert "ENVIRONMENT: fixture" in text
    assert "if: always()" in text
    repository_gate = _workflow("ci.yml")
    assert "pull_request:" in repository_gate
    assert "run: make verify" in repository_gate


def test_nightly_runs_the_full_fixture_suite_three_times_and_uploads_reports() -> None:
    text = _workflow("nightly.yml")

    assert "schedule:" in text
    assert "permissions:\n  contents: read" in text
    assert text.count("scripts/run_offline_eval.py") == 3
    assert text.count("continue-on-error: true") == 3
    assert "Enforce all nightly evaluations" in text
    assert "if: always()" in text
    assert "actions/upload-artifact@" in text


def test_weekly_live_provider_smoke_is_explicitly_credential_gated() -> None:
    text = _workflow("weekly.yml")

    assert "schedule:" in text
    assert "permissions:\n  contents: read" in text
    assert "scripts/run_offline_eval.py" in text
    assert "LIVE_PROVIDER_TESTS" in text
    assert "secrets.ALPACA_DATA_KEY" in text
    assert "if:" in text
    assert "if: always()" in text
    lowered = text.lower()
    assert "live_broker" not in lowered
    assert "broker_url" not in lowered


def test_every_external_action_is_pinned_to_a_commit_sha() -> None:
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "uses:" not in line:
                continue
            reference = line.split("uses:", maxsplit=1)[1].split("#", maxsplit=1)[0].strip()
            assert "@" in reference
            revision = reference.rsplit("@", maxsplit=1)[1]
            assert len(revision) == 40
            assert all(character in "0123456789abcdef" for character in revision)
