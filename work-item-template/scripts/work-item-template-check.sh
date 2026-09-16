#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
impl="$home/scripts/work-item-template-check-impl.sh"

[[ -x "$impl" ]] || {
  printf 'FAIL: missing executable checker: %s\n' "$impl" >&2
  exit 1
}

exec bash "$impl" "$@"
