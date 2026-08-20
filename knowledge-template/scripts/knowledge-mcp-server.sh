#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/knowledge"
server="$project/server.py"

command -v uv >/dev/null 2>&1 || {
  printf 'ERROR: missing command: uv\n' >&2
  exit 69
}

[[ -f "$server" ]] || {
  printf 'ERROR: missing knowledge MCP server: %s\n' "$server" >&2
  exit 66
}

: "${KNOWLEDGE_STORE_ROOT:=$home/store}"
export KNOWLEDGE_STORE_ROOT

exec uv run --project "$project" python "$server"
