#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$workspace_root/mcp/knowledge"
cli="$project_dir/cli.py"

command -v uv >/dev/null 2>&1 || {
  printf 'ERROR: missing command: uv\n' >&2
  exit 69
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

exec uv run --project "$project_dir" python "$cli" --root "$knowledge_root" "$@"
