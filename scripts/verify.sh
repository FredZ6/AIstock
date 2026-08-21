#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_CACHE_DIR="${repo_root}/.uv-cache"
export NEXT_TELEMETRY_DISABLED=1

cd "${repo_root}"
uv run ruff format --check backend scripts/export_mcp_contracts.py scripts/export_openapi.py
uv run ruff check backend scripts/export_mcp_contracts.py scripts/export_openapi.py
uv run mypy
uv run alembic -c backend/alembic.ini check
PYTHONPATH="${repo_root}/backend/src" uv run python scripts/export_mcp_contracts.py --check
PYTHONPATH="${repo_root}/backend/src" uv run python scripts/export_openapi.py --check
uv run pytest -q
CI=true pnpm --dir web typecheck
CI=true pnpm --dir web lint
CI=true pnpm --dir web test -- --run
CI=true pnpm --dir web build
