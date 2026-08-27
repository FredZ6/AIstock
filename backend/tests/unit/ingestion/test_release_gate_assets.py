from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_ingestion_gate_covers_every_durable_recovery_boundary() -> None:
    gate = (REPO_ROOT / "scripts" / "verify-ingestion.sh").read_text(encoding="utf-8")
    for required in (
        "test_raw_replay.py",
        "test_raw_dispatch.py",
        "test_alpaca_job_e2e.py",
        "test_quality_history.py",
        "test_job_store.py",
        "test_secret_redaction.py",
    ):
        assert required in gate


def test_ingestion_recovery_runbook_names_each_commit_boundary() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "ingestion-recovery.md").read_text(
        encoding="utf-8"
    )
    for boundary in ("MinIO", "raw", "outbox", "normalize", "fact", "quality", "cursor"):
        assert boundary in runbook
    assert "scripts/verify-ingestion.sh" in runbook
    assert "ingestion-leases" in runbook
    probe = (REPO_ROOT / "scripts" / "recovery_probe.py").read_text(encoding="utf-8")
    assert "recover_ingestion_leases" in probe
