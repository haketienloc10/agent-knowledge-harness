#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/google_sheets"

command -v uv >/dev/null 2>&1 || {
  printf 'ERROR: missing command: uv\n' >&2
  exit 69
}

bash -n "$home/scripts/google-sheets-mcp-server.sh"
bash -n "$home/scripts/install-user-mcp.sh"
uv sync --project "$project"
uv run --project "$project" python -m unittest discover -s "$project/tests" -v
