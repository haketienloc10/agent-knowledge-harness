#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/work_item"
impl="$home/scripts/work-item-template-check-impl.sh"

if ! command -v uv >/dev/null 2>&1; then
  printf 'FAIL: missing command: uv\n' >&2
  exit 1
fi

exec uv run --project "$project" -- bash "$impl" "$@"
