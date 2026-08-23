#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_project="${COMPOSE_PROJECT_NAME:-aistock}"
restore_db="stock_platform_restore_check_$$"
dump_file="$(mktemp "${TMPDIR:-/tmp}/stock-platform.XXXXXX.dump")"
worker_log="$(mktemp "${TMPDIR:-/tmp}/stock-platform-worker.XXXXXX.log")"
worker_pid=""
worker_name=""
worker_generation=0

stop_worker() {
  if [[ -n "${worker_pid}" ]] && kill -0 "${worker_pid}" >/dev/null 2>&1; then
    kill -TERM "${worker_pid}"
    wait "${worker_pid}" || true
  fi
  worker_pid=""
}

start_worker() {
  worker_generation=$((worker_generation + 1))
  worker_name="recovery-check-${worker_generation}@localhost"
  PYTHONPATH="${repo_root}/backend/src" \
    DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:55432/${restore_db}" \
    REDIS_URL="redis://localhost:56379/0" \
    .venv/bin/celery -A stock_platform.workers.celery_app:celery_app worker \
      --pool=solo --concurrency=1 --loglevel=WARNING \
      --hostname="${worker_name}" --pidfile= >"${worker_log}" 2>&1 &
  worker_pid=$!
  for _attempt in {1..30}; do
    if PYTHONPATH="${repo_root}/backend/src" REDIS_URL="redis://localhost:56379/0" \
      .venv/bin/celery -A stock_platform.workers.celery_app:celery_app inspect ping \
      --destination="${worker_name}" --timeout=1 2>/dev/null | rg "pong" >/dev/null; then
      return
    fi
    if ! kill -0 "${worker_pid}" >/dev/null 2>&1; then
      tail -n 40 "${worker_log}"
      return 1
    fi
    sleep 1
  done
  tail -n 40 "${worker_log}"
  return 1
}

cleanup() {
  stop_worker
  docker compose -p "${compose_project}" exec -T postgres \
    dropdb -U postgres --if-exists "${restore_db}" >/dev/null 2>&1 || true
  rm -f "${dump_file}" "${worker_log}"
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

probe_database_url="postgresql+psycopg://postgres:postgres@localhost:55432/${restore_db}"
probe_fill_id="$(PYTHONPATH="${repo_root}/backend/src" .venv/bin/python \
  scripts/recovery_probe.py paper-fill --database-url "${probe_database_url}")"
probe_fill_count="$(docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -Atc \
  "SELECT count(*) FROM paper_fill WHERE id = '${probe_fill_id}'")"
probe_ledger_count="$(docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -Atc \
  "SELECT count(*) FROM cash_ledger WHERE source_id = '${probe_fill_id}'")"
test "${probe_fill_count}" = "1"
test "${probe_ledger_count}" = "3"
probe_run_id="$(PYTHONPATH="${repo_root}/backend/src" .venv/bin/python \
  scripts/recovery_probe.py prepare --database-url "${probe_database_url}")"
start_worker
PYTHONPATH="${repo_root}/backend/src" REDIS_URL="redis://localhost:56379/0" \
  .venv/bin/celery -A stock_platform.workers.celery_app:celery_app call \
  stock_platform.workers.research_tasks.run_research \
  --args="[\"${probe_run_id}\"]" >/dev/null
PYTHONPATH="${repo_root}/backend/src" .venv/bin/python scripts/recovery_probe.py wait \
  --database-url "${probe_database_url}" --run-id "${probe_run_id}"
probe_event_count="$(docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -Atc \
  "SELECT count(*) FROM agent_event WHERE run_id = '${probe_run_id}'")"
probe_tool_count="$(docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -Atc \
  "SELECT count(*) FROM tool_call WHERE run_id = '${probe_run_id}'")"
test "${probe_event_count}" -gt 0
test "${probe_tool_count}" -gt 0
before_agent_events="$(docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -Atc "SELECT count(*) FROM agent_event")"
test "${before_agent_events}" -gt 0
docker compose -p "${compose_project}" restart redis
docker compose -p "${compose_project}" exec -T redis redis-cli ping | rg -x PONG
stop_worker
start_worker
PYTHONPATH="${repo_root}/backend/src" REDIS_URL="redis://localhost:56379/0" \
  .venv/bin/celery -A stock_platform.workers.celery_app:celery_app call \
  stock_platform.workers.research_tasks.run_research \
  --args="[\"${probe_run_id}\"]" >/dev/null
for _attempt in {1..30}; do
  replay_queue_depth="$(docker compose -p "${compose_project}" exec -T redis \
    redis-cli llen celery)"
  if [[ "${replay_queue_depth}" == "0" ]]; then
    break
  fi
  sleep 0.2
done
test "${replay_queue_depth}" = "0"
sleep 1
replayed_fill_id="$(PYTHONPATH="${repo_root}/backend/src" .venv/bin/python \
  scripts/recovery_probe.py paper-fill --database-url "${probe_database_url}")"
after_agent_events="$(docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -Atc "SELECT count(*) FROM agent_event")"
test "${before_agent_events}" = "${after_agent_events}"
test "${replayed_fill_id}" = "${probe_fill_id}"
test "${probe_fill_count}" = "$(docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -Atc \
  "SELECT count(*) FROM paper_fill WHERE id = '${probe_fill_id}'")"
test "${probe_ledger_count}" = "$(docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -Atc \
  "SELECT count(*) FROM cash_ledger WHERE source_id = '${probe_fill_id}'")"
test "${probe_event_count}" = "$(docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -Atc \
  "SELECT count(*) FROM agent_event WHERE run_id = '${probe_run_id}'")"
test "${probe_tool_count}" = "$(docker compose -p "${compose_project}" exec -T postgres \
  psql -U postgres -d "${restore_db}" -Atc \
  "SELECT count(*) FROM tool_call WHERE run_id = '${probe_run_id}'")"
stop_worker
.venv/bin/pytest \
  backend/tests/integration/recovery \
  backend/tests/integration/api/test_worker_execution.py::test_worker_failure_is_bounded_and_releases_admission_capacity \
  backend/tests/integration/portfolio/test_paper_accounting_store.py::test_replay_persists_one_append_only_fill_and_balanced_ledger \
  -q
