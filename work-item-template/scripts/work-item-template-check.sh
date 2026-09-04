#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/work_item"
impl="$home/scripts/work-item-template-check-impl.sh"

if ! command -v uv >/dev/null 2>&1; then
  printf 'FAIL: missing command: uv\n' >&2
  exit 1
fi

project_python="$(uv run --project "$project" python -c 'import sys; print(sys.executable)')"
shim_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$shim_dir"
}
trap cleanup EXIT INT TERM
ln -s "$project_python" "$shim_dir/python3"

PATH="$shim_dir:$PATH" "$impl" "$@"
