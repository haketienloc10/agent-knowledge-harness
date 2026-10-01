#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$workspace_root/mcp/qiqi_delegate"
broker="$project_dir/supervisor_broker.py"

command -v uv >/dev/null 2>&1 || {
  printf 'ERROR: missing command: uv\n' >&2
  exit 69
}

[[ -f "$broker" ]] || {
  printf 'ERROR: missing Supervisor broker: %s\n' "$broker" >&2
  exit 66
}

export QIQI_WORKSPACE_ROOT="$workspace_root"
export QIQI_HERDR_SESSION="${QIQI_HERDR_SESSION:-qiqi-delegate}"

exec uv run --project "$project_dir" python "$broker" "$@"
