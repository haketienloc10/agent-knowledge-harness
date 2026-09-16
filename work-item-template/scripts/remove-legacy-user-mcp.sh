#!/usr/bin/env bash
set -euo pipefail

dry_run=0

usage() {
  cat <<'EOF'
Usage: remove-legacy-user-mcp.sh [--dry-run]

Removes the legacy user/global MCP registration named `work_item` that was created
by the old Work Item installer. The script refuses to remove a registration unless
its current definition points to the managed legacy `agent-work-item-mcp` wrapper
(or the deleted work-item-mcp-server.sh launcher).
EOF
}

while (($#)); do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

is_legacy_registration() {
  local output="$1"
  grep -Eq 'agent-work-item-mcp|work-item-mcp-server\.sh' <<<"$output"
}

remove_for_client() {
  local client="$1"
  local cli="$2"
  local output after

  if ! command -v "$cli" >/dev/null 2>&1; then
    printf 'WARN: %s CLI not found; cannot verify/remove its legacy work_item registration.\n' "$client" >&2
    return 0
  fi

  if ! output="$("$cli" mcp get work_item 2>&1)"; then
    printf '%s: no work_item MCP registration found.\n' "$client"
    return 0
  fi

  if ! is_legacy_registration "$output"; then
    printf 'ERROR: %s has a work_item MCP registration that does not point to the managed legacy wrapper.\n' "$client" >&2
    printf 'Refusing to remove an unrelated registration. Inspect `%s mcp get work_item` manually.\n' "$cli" >&2
    return 78
  fi

  if ((dry_run)); then
    printf '%s: would remove legacy work_item MCP registration.\n' "$client"
    return 0
  fi

  "$cli" mcp remove work_item

  if after="$("$cli" mcp get work_item 2>&1)"; then
    printf 'ERROR: %s still resolves a work_item MCP registration after removal.\n' "$client" >&2
    printf '%s\n' "$after" >&2
    return 78
  fi

  printf '%s: legacy work_item MCP registration removed and absence verified.\n' "$client"
}

remove_for_client 'Codex' codex
remove_for_client 'Claude' claude
