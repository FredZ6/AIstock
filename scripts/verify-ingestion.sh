#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

UV_CACHE_DIR="${repo_root}/.uv-cache" uv run pytest -q \
  backend/tests/integration/ingestion/test_raw_replay.py \
  backend/tests/integration/ingestion/test_alpaca_recovery.py \
  backend/tests/integration/ingestion/test_quality_history.py \
  backend/tests/security/test_secret_redaction.py

run_live() {
  local provider="$1"
  local flag="$2"
  local test_path="$3"
  shift 3
  if [[ "${!flag:-0}" != "1" ]]; then
    echo "SKIP ${provider} live smoke: ${flag}=1 not set"
    return
  fi
  for secret_name in "$@"; do
    if [[ -z "${!secret_name:-}" ]]; then
      echo "SKIP ${provider} live smoke: missing ${secret_name}"
      return
    fi
  done
  LIVE_PROVIDER_TESTS=1 UV_CACHE_DIR="${repo_root}/.uv-cache" uv run pytest -q \
    "${test_path}" -k "${provider}_live_contract"
}

live_contracts="backend/tests/contract/providers/test_live_adapter_contracts.py"
run_live alpaca RUN_ALPACA_LIVE_SMOKE "${live_contracts}" ALPACA_DATA_KEY ALPACA_DATA_SECRET
run_live sec RUN_SEC_LIVE_SMOKE "${live_contracts}" SEC_USER_AGENT
run_live alpha RUN_ALPHA_LIVE_SMOKE \
  backend/tests/contract/providers/test_alpha_vantage_ingestion.py ALPHA_VANTAGE_API_KEY
