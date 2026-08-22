#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_project="${COMPOSE_PROJECT_NAME:-aistock}"
restore_db="stock_platform_restore_check_$$"
dump_file="$(mktemp "${TMPDIR:-/tmp}/stock-platform.XXXXXX.dump")"

cleanup() {
  docker compose -p "${compose_project}" exec -T postgres \
    dropdb -U postgres --if-exists "${restore_db}" >/dev/null 2>&1 || true
  rm -f "${dump_file}"
}
trap cleanup EXIT

cd "${repo_root}"
docker compose -p "${compose_project}" up -d
docker compose -p "${compose_project}" exec -T postgres \
  pg_dump -U postgres -d stock_platform -Fc >"${dump_file}"
docker compose -p "${compose_project}" exec -T postgres \
  createdb -U postgres "${restore_db}"
docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS timescaledb; SELECT timescaledb_pre_restore();"
docker compose -p "${compose_project}" exec -T postgres \
  pg_restore -U postgres -d "${restore_db}" --no-owner <"${dump_file}"
docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -v ON_ERROR_STOP=1 \
  -c "SELECT timescaledb_post_restore();"
DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:55432/${restore_db}" \
  .venv/bin/alembic -c backend/alembic.ini check

docker compose -p "${compose_project}" restart redis
docker compose -p "${compose_project}" exec -T redis redis-cli ping | grep -qx PONG
.venv/bin/pytest \
  backend/tests/integration/recovery \
  backend/tests/integration/api/test_worker_execution.py::test_worker_failure_is_bounded_and_releases_admission_capacity \
  backend/tests/integration/portfolio/test_paper_accounting_store.py::test_replay_persists_one_append_only_fill_and_balanced_ledger \
  -q
