#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$workspace_root/mcp/knowledge"
server="$project_dir/server.py"

command -v uv >/dev/null 2>&1 || {
  printf 'ERROR: missing command: uv\n' >&2
  exit 69
}

[[ -f "$server" ]] || {
  printf 'ERROR: missing Knowledge MCP server: %s\n' "$server" >&2
  exit 66
}

knowledge_root="${QIQI_KNOWLEDGE_ROOT:-}"
[[ -n "$knowledge_root" ]] || {
  printf 'ERROR: QIQI_KNOWLEDGE_ROOT is required\n' >&2
  exit 64
}
[[ "$knowledge_root" = /* ]] || {
  printf 'ERROR: QIQI_KNOWLEDGE_ROOT must be an absolute path: %s\n' "$knowledge_root" >&2
  exit 64
}
[[ -d "$knowledge_root" ]] || {
  printf 'ERROR: knowledge root does not exist: %s\n' "$knowledge_root" >&2
  exit 66
}
[[ -f "$knowledge_root/INDEX.md" ]] || {
  printf 'ERROR: knowledge root is not initialized (missing INDEX.md): %s\n' "$knowledge_root" >&2
  exit 66
}

exec uv run --project "$project_dir" python "$server"
