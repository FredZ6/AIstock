#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_project="${COMPOSE_PROJECT_NAME:-aistock}"
runtime_id="agent_runtime_$$_${RANDOM}"
database_name="stock_platform_isolated_${runtime_id}"
database_url="postgresql+psycopg://postgres:postgres@127.0.0.1:55432/${database_name}"
redis_url="redis://127.0.0.1:56379/15"
runtime_control_queue="${runtime_id}.control"
runtime_research_queue="${runtime_id}.agent-research"
redis_key_prefix="${runtime_id}:"
log_dir="${repo_root}/output/agent-runtime/${runtime_id}"
worker_log="${log_dir}/worker.log"
beat_log="${log_dir}/beat.log"
worker_pid=""
beat_pid=""
worker_name="${runtime_id}@localhost"
web_port="$((32000 + ($$ % 1000)))"
api_port="$("${repo_root}/.venv/bin/python" -c 'import socket; listener=socket.socket(); listener.bind(("127.0.0.1", 0)); print(listener.getsockname()[1]); listener.close()')"

mkdir -p "${log_dir}"

celery_environment=(
  "PYTHONPATH=${repo_root}/backend/src:${repo_root}"
  "ENVIRONMENT=test"
  "DATABASE_URL=${database_url}"
  "REDIS_URL=${redis_url}"
  "MINIO_ENDPOINT=http://127.0.0.1:59000"
  "MAX_ACTIVE_AGENT_RUNS=1"
  "AGENT_RUNTIME_CONTROL_QUEUE=${runtime_control_queue}"
  "AGENT_RUNTIME_RESEARCH_QUEUE=${runtime_research_queue}"
  "AGENT_RUNTIME_REDIS_KEY_PREFIX=${redis_key_prefix}"
)

stop_process() {
  local pid="$1"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    kill -TERM "${pid}"
    wait "${pid}" || true
  fi
}

cleanup_redis_keys() {
  while IFS= read -r key; do
    if [[ -n "${key}" ]]; then
      docker compose -p "${compose_project}" exec -T redis \
        redis-cli -n 15 UNLINK "${key}" >/dev/null 2>&1 || true
    fi
  done < <(
    docker compose -p "${compose_project}" exec -T redis \
      redis-cli -n 15 --raw --scan --pattern "${redis_key_prefix}*" 2>/dev/null || true
  )
}

cleanup() {
  stop_process "${beat_pid}"
  stop_process "${worker_pid}"
  cleanup_redis_keys
  docker compose -p "${compose_project}" exec -T postgres \
    dropdb -U postgres --if-exists "${database_name}" >/dev/null 2>&1 || true
}

failure_evidence() {
  local exit_code=$?
  if [[ "${exit_code}" -ne 0 ]]; then
    echo "agent runtime acceptance failed; logs: ${log_dir}" >&2
    tail -n 80 "${worker_log}" 2>/dev/null || true
    tail -n 80 "${beat_log}" 2>/dev/null || true
  fi
  cleanup
  exit "${exit_code}"
}
trap failure_evidence EXIT

cd "${repo_root}"
docker compose -p "${compose_project}" up -d --wait postgres redis minio
test -z "$(docker compose -p "${compose_project}" exec -T redis \
  redis-cli -n 15 --raw --scan --pattern "${redis_key_prefix}*")"
docker compose -p "${compose_project}" exec -T postgres createdb -U postgres "${database_name}"
DATABASE_URL="${database_url}" .venv/bin/alembic -c backend/alembic.ini upgrade head
PYTHONPATH="${repo_root}/backend/src" DATABASE_URL="${database_url}" \
  .venv/bin/python -c \
  'from sqlalchemy import create_engine; from stock_platform.infrastructure.db.security_seed import seed_security_master; import os; engine=create_engine(os.environ["DATABASE_URL"]); connection=engine.connect(); transaction=connection.begin(); seed_security_master(connection); transaction.commit(); connection.close(); engine.dispose()'

env "${celery_environment[@]}" \
  .venv/bin/celery -A scripts.agent_runtime_celery:celery_app worker \
    --pool=solo --concurrency=1 --loglevel=INFO \
    --queues="${runtime_control_queue},${runtime_research_queue}" \
    --hostname="${worker_name}" --pidfile= >"${worker_log}" 2>&1 &
worker_pid=$!

for _attempt in {1..30}; do
  if env "${celery_environment[@]}" .venv/bin/celery \
    -A scripts.agent_runtime_celery:celery_app inspect ping \
    --destination="${worker_name}" --timeout=1 2>/dev/null | rg "pong" >/dev/null; then
    break
  fi
  if ! kill -0 "${worker_pid}" >/dev/null 2>&1; then
    echo "Celery worker exited before readiness" >&2
    exit 1
  fi
  sleep 1
done
env "${celery_environment[@]}" .venv/bin/celery \
  -A scripts.agent_runtime_celery:celery_app inspect ping \
  --destination="${worker_name}" --timeout=2 | rg "pong" >/dev/null

beat_schedule="${log_dir}/celerybeat-schedule"
env "${celery_environment[@]}" BEAT_SCHEDULE="${beat_schedule}" \
  .venv/bin/python -c \
  'import os; from scripts.agent_runtime_celery import celery_app; celery_app.conf.beat_schedule={"runtime-recover":{"task":"stock_platform.workers.schedules.recover_queued","schedule":10.0}}; celery_app.Beat(loglevel="INFO", schedule_filename=os.environ["BEAT_SCHEDULE"], pidfile=None).run()' \
  >"${beat_log}" 2>&1 &
beat_pid=$!

run_id="$(PYTHONPATH="${repo_root}/backend/src" .venv/bin/python \
  scripts/recovery_probe.py prepare --database-url "${database_url}")"
PYTHONPATH="${repo_root}/backend/src" .venv/bin/python scripts/recovery_probe.py wait \
  --database-url "${database_url}" --run-id "${run_id}" --timeout 45
stop_process "${beat_pid}"
beat_pid=""

sql() {
  docker compose -p "${compose_project}" exec -T postgres \
    psql -U postgres -d "${database_name}" -Atc "$1"
}

event_count="$(sql "SELECT count(*) FROM agent_event WHERE run_id = '${run_id}'")"
tool_count="$(sql "SELECT count(*) FROM tool_call WHERE run_id = '${run_id}'")"
checkpoint_count="$(sql "SELECT count(*) FROM checkpoints WHERE thread_id = '${run_id}'")"
decision_count="$(sql "SELECT count(*) FROM decision_snapshot d JOIN investment_thesis t ON t.id = d.thesis_id WHERE t.run_id = '${run_id}'")"
sequence_ok="$(sql "SELECT count(*) = max(sequence) AND min(sequence) = 1 AND count(*) = count(DISTINCT sequence) FROM agent_event WHERE run_id = '${run_id}'")"
test "${event_count}" -gt 2
test "${tool_count}" -gt 0
test "${checkpoint_count}" -gt 0
test "${decision_count}" = "1"
test "${sequence_ok}" = "t"
rg "recover_queued" "${beat_log}" >/dev/null
rg -F "Task stock_platform.workers.research_tasks.run_research[${run_id}] received" \
  "${worker_log}" >/dev/null
rg -F "Task stock_platform.workers.research_tasks.run_research[${run_id}] succeeded" \
  "${worker_log}" >/dev/null

replay_task_id="$(.venv/bin/python -c 'from uuid import uuid4; print(uuid4())')"
call_output="$(env "${celery_environment[@]}" REPLAY_TASK_ID="${replay_task_id}" RUN_ID="${run_id}" \
  .venv/bin/python -c \
  'import os; from scripts.agent_runtime_celery import celery_app; result=celery_app.send_task("stock_platform.workers.research_tasks.run_research", args=[os.environ["RUN_ID"]], task_id=os.environ["REPLAY_TASK_ID"]); print(result.id)')"
printf '%s\n' "${call_output}" | rg -x "${replay_task_id}" >/dev/null
replay_completed="false"
for _attempt in {1..60}; do
  if rg -F "Task stock_platform.workers.research_tasks.run_research[${replay_task_id}] succeeded" \
    "${worker_log}" >/dev/null; then
    replay_completed="true"
    break
  fi
  sleep 0.2
done
test "${replay_completed}" = "true"
rg -F "Task stock_platform.workers.research_tasks.run_research[${replay_task_id}] received" \
  "${worker_log}" >/dev/null
test "${event_count}" = "$(sql "SELECT count(*) FROM agent_event WHERE run_id = '${run_id}'")"
test "${tool_count}" = "$(sql "SELECT count(*) FROM tool_call WHERE run_id = '${run_id}'")"
test "${checkpoint_count}" = "$(sql "SELECT count(*) FROM checkpoints WHERE thread_id = '${run_id}'")"
test "${decision_count}" = "$(sql "SELECT count(*) FROM decision_snapshot d JOIN investment_thesis t ON t.id = d.thesis_id WHERE t.run_id = '${run_id}'")"
research_received_count="$(rg -c 'Task stock_platform\.workers\.research_tasks\.run_research\[[^]]+\] received' "${worker_log}")"
received_count="$(rg -c 'Task stock_platform\..* received' "${worker_log}")"
succeeded_count="$(rg -c 'Task stock_platform\..* succeeded' "${worker_log}")"
test "${research_received_count}" = "2"
test "${received_count}" = "3"
test "${received_count}" = "${succeeded_count}"
echo "runtime task evidence: received=${received_count} succeeded=${succeeded_count} research=2 replay_task_id=${replay_task_id}"
stop_process "${worker_pid}"
worker_pid=""

PYTHONPATH="${repo_root}/backend/src" .venv/bin/python scripts/seed_browser_today.py \
  --database-url "${database_url}"

event_ids="$(sql "SELECT string_agg(id::text, ',' ORDER BY sequence) FROM agent_event WHERE run_id = '${run_id}'")"
RUN_API_BROWSER=1 WEB_DATA_MODE=api API_BASE_URL="http://127.0.0.1:${api_port}" \
  PLAYWRIGHT_WEB_PORT="${web_port}" DATABASE_URL="${database_url}" \
  BROWSER_API_PORT="${api_port}" \
  BROWSER_RUN_ID="${run_id}" BROWSER_EVENT_IDS="${event_ids}" \
  pnpm --dir web exec playwright test e2e/api-runtime.spec.ts --workers=1

UV_CACHE_DIR="${repo_root}/.uv-cache" uv run pytest \
  backend/tests/integration/api/test_worker_execution.py \
  backend/tests/integration/api/test_sse_resume.py -q

echo "agent runtime acceptance passed; logs: ${log_dir}"
