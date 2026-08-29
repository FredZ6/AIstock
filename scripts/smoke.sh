#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
report_dir="${SMOKE_REPORT_DIR:-${repo_root}/evals/reports/latest}"
export PYTHONPATH="${repo_root}/backend/src"
export UV_CACHE_DIR="${repo_root}/.uv-cache"
export WEB_DATA_MODE=fixture

cd "${repo_root}"
mkdir -p "${report_dir}"

if [[ "${SMOKE_SKIP_SEED:-0}" != "1" ]]; then
  make seed
fi
uv run python scripts/demo_scenario.py > "${report_dir}/demo-manifest.json"
uv run python scripts/run_offline_eval.py \
  --dataset evals/datasets \
  --baseline evals/baselines/eval-v0.2.0.json \
  --output "${report_dir}"

if [[ "${SMOKE_SKIP_BROWSER:-0}" != "1" ]]; then
  DEMO_REPORT_DIR="${report_dir}" pnpm --dir web exec playwright test e2e/demo.spec.ts
fi

for artifact in demo-manifest.json summary.json cases.jsonl junit.xml report.html; do
  test -s "${report_dir}/${artifact}"
done

echo "M8 fixture demo: PASS"
echo "Evidence: ${report_dir}"
