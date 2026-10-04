#!/usr/bin/env bash
set -euo pipefail

eval_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "$eval_root/.." && pwd)"
project_dir="$workspace_root/mcp/qiqi_delegate"

command -v uv >/dev/null 2>&1 || {
  printf 'ERROR: missing command: uv\n' >&2
  exit 69
}

exec uv run --project "$project_dir" python "$eval_root/run.py" "$@"
