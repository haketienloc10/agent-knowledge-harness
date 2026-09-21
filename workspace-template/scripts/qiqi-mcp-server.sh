#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$workspace_root/mcp/qiqi_delegate"
server="$project_dir/task_graph_mcp.py"
work_items_dir="$workspace_root/work-items"

command -v uv >/dev/null 2>&1 || {
  printf 'ERROR: missing command: uv\n' >&2
  exit 69
}

[[ -f "$server" ]] || {
  printf 'ERROR: missing MCP server: %s\n' "$server" >&2
  exit 66
}

mkdir -p "$work_items_dir"

export QIQI_WORKSPACE_ROOT="$workspace_root"
# Delegated-runtime mount alias. Parent QiQi/$work-item resolves
# <workspace>/work-items directly and does not depend on this child export.
export QIQI_WORK_ITEMS_DIR="$work_items_dir"

exec uv run --project "$project_dir" python "$server"
