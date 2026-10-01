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

command -v flock >/dev/null 2>&1 || {
  printf 'ERROR: missing command: flock\n' >&2
  exit 69
}

lock_file="$workspace_root/.qiqi/state/qiqi-supervisor-broker.lock"
mkdir -p "$(dirname "$lock_file")"
exec 9>"$lock_file"
if ! flock -n 9; then
  printf 'ERROR: Supervisor broker already running for state DB: %s\n' \
    "$workspace_root/.qiqi/state/qiqi_delegate.sqlite3" >&2
  exit 75
fi

# fd 9 remains open across exec, so the advisory lock is held for the full broker
# process lifetime and released automatically on exit.
exec uv run --project "$project_dir" python "$broker" "$@"
