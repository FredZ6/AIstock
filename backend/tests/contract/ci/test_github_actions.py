import json
from pathlib import Path

WORKFLOW = Path(__file__).parents[4] / ".github" / "workflows" / "ci.yml"
PACKAGE_JSON = Path(__file__).parents[4] / "package.json"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_ci_runs_for_main_changes_with_least_privilege() -> None:
    content = workflow_text()

    assert "pull_request:" in content
    assert "push:" in content
    assert "workflow_dispatch:" in content
    assert content.count("branches: [main]") == 2
    assert "contents: read" in content
    assert "cancel-in-progress: true" in content
    assert "runs-on: ubuntu-latest" in content


def test_ci_uses_locked_toolchains_and_fixture_services() -> None:
    content = workflow_text()
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))

    assert 'python-version: "3.12"' in content
    assert 'node-version: "22"' in content
    assert package["packageManager"] == "pnpm@11.19.0"
    assert 'version: "11"' not in content
    assert "DATABASE_URL:" not in content
    assert "astral-sh/setup-uv@" in content
    assert "ENVIRONMENT: fixture" in content
    assert "docker compose up -d --wait postgres redis minio" in content
    assert "LIVE_PROVIDER_TESTS" not in content
    assert "LIVE_BROKER" not in content.upper()


def test_ci_upgrades_fresh_database_and_runs_authoritative_gate() -> None:
    content = workflow_text()

    bootstrap = content.index("make bootstrap")
    services = content.index("docker compose up -d --wait postgres redis minio")
    migrate = content.index("uv run alembic -c backend/alembic.ini upgrade head")
    verify = content.index("make verify")

    assert bootstrap < services < migrate < verify
    assert "docker compose ps" in content
    assert "docker compose logs --no-color" in content
    assert "docker compose down --volumes --remove-orphans" in content
