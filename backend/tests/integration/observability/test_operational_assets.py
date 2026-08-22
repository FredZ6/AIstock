import json
from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[4]


def test_compose_wires_otel_prometheus_and_grafana_with_pinned_configs() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]

    assert {"otel-collector", "prometheus", "grafana"} <= services.keys()
    assert services["otel-collector"]["volumes"]
    assert services["prometheus"]["volumes"]
    assert services["grafana"]["volumes"]
    for service in ("postgres", "redis", "minio", "otel-collector", "prometheus", "grafana"):
        assert all(str(port).startswith("127.0.0.1:") for port in services[service]["ports"])
    assert (ROOT / "infra/otel/collector.yml").is_file()
    assert (ROOT / "infra/prometheus/prometheus.yml").is_file()
    recovery_script = (ROOT / "scripts/verify-recovery.sh").read_text()
    assert "pg_dump" in recovery_script and "pg_restore" in recovery_script
    assert "timescaledb_pre_restore()" in recovery_script
    assert "timescaledb_post_restore()" in recovery_script
    assert "restart redis" in recovery_script
    assert "celery_app:celery_app worker" in recovery_script
    assert "before_agent_events" in recovery_script
    assert "after_agent_events" in recovery_script
    assert "before_paper_fills" in recovery_script
    assert "after_paper_fills" in recovery_script
    assert "test_replay_persists_one_append_only_fill" in recovery_script


def test_grafana_dashboard_covers_slos_and_failure_categories() -> None:
    dashboard = json.loads((ROOT / "infra/grafana/dashboards/platform-operations.json").read_text())
    titles = {panel["title"] for panel in dashboard["panels"]}

    assert {
        "API success rate",
        "Provider failures",
        "Tool failures",
        "Graph failures",
        "Alert failures",
        "Queue depth",
        "Cost",
        "Evaluation gates",
    } <= titles


def test_security_guide_and_each_recovery_runbook_state_commands_rpo_and_rto() -> None:
    security = (ROOT / "docs/security.md").read_text()
    assert "paper trading only" in security.lower()
    assert "redact" in security.lower()
    assert "live broker" in security.lower()

    for name in (
        "provider-outage.md",
        "stuck-run.md",
        "redis-loss.md",
        "db-restore.md",
        "policy-rollback.md",
    ):
        content = (ROOT / "docs/runbooks" / name).read_text()
        assert "## RPO" in content
        assert "## RTO" in content
        assert "```" in content
