#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$workspace_root/mcp/qiqi_delegate"
server="$project_dir/server.py"

command -v uv >/dev/null 2>&1 || {
  printf 'ERROR: missing command: uv\n' >&2
  exit 69
}

[[ -f "$server" ]] || {
  printf 'ERROR: missing MCP server: %s\n' "$server" >&2
  exit 66
}

export QIQI_WORKSPACE_ROOT="$workspace_root"
exec uv run --project "$project_dir" python "$server"
