#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
impl="$home/scripts/work-item-template-check-impl.sh"
phase_check="$home/scripts/work-item-phase-skills-check.sh"

[[ -x "$impl" ]] || {
  printf 'FAIL: missing executable checker: %s\n' "$impl" >&2
  exit 1
}
[[ -f "$phase_check" ]] || {
  printf 'FAIL: missing phase skill checker: %s\n' "$phase_check" >&2
  exit 1
}

bash "$phase_check"
exec bash "$impl" "$@"
