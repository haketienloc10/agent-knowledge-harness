#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
printf 'WARNING: install-user-skill.sh is deprecated; Work Item is workspace-scoped. Use install-workspace-skill.sh WORKSPACE.\n' >&2
exec bash "$home/scripts/install-workspace-skill.sh" "$@"
