#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/work_item"

: "${WORK_ITEM_DB_PATH:?WORK_ITEM_DB_PATH must point to the global Work Item SQLite database}"

exec uv run --project "$project" python "$project/cli.py" "$@"
