#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/knowledge"
python_runtime="$project/.venv/bin/python"

if [[ ! -x "$python_runtime" ]]; then
  printf 'ERROR: knowledge runtime is not synced: %s\n' "$project" >&2
  printf 'Run: uv sync --project %q\n' "$project" >&2
  exit 69
fi

exec "$python_runtime" "$home/scripts/knowledge.py" "$@"
