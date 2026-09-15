#!/usr/bin/env bash
set -euo pipefail

: "${QIQI_WORK_ITEMS_DIR:?QIQI_WORK_ITEMS_DIR must be set by qiqi-mcp-server.sh}"
[[ -d "$QIQI_WORK_ITEMS_DIR" ]] || {
  printf 'ERROR: Work Items directory does not exist: %s\n' "$QIQI_WORK_ITEMS_DIR" >&2
  exit 66
}

exec codex --add-dir "$QIQI_WORK_ITEMS_DIR" "$@"
