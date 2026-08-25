#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/work_item"

command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: missing command: python3\n' >&2
  exit 69
}

PYTHONPATH="$project" python3 -m unittest discover -s "$project/tests" -v
python3 -m py_compile "$project/core.py" "$project/server.py"
bash -n "$home/scripts/work-item-mcp-server.sh"
bash -n "$home/scripts/install-user-mcp.sh"

printf 'Work Item template checks passed.\n'
