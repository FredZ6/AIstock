#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_CACHE_DIR="${repo_root}/.uv-cache"

cd "${repo_root}"
uv sync --all-groups --locked
CI=true pnpm install --frozen-lockfile
