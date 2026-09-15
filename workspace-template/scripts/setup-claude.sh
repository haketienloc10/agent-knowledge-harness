#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
server_wrapper="$workspace_root/scripts/qiqi-mcp-server.sh"

command -v claude >/dev/null 2>&1 || {
  printf 'ERROR: missing command: claude\n' >&2
  exit 69
}

[[ -f "$server_wrapper" ]] || {
  printf 'ERROR: missing qiqi_delegate wrapper: %s\n' "$server_wrapper" >&2
  exit 66
}

cd "$workspace_root"

# qiqi_delegate belongs to the QiQi coordinator project only. Keep it local-scope
# so repository child sessions do not inherit the orchestration MCP capability.
claude mcp remove qiqi_delegate --scope local >/dev/null 2>&1 || true
claude mcp add --scope local --transport stdio qiqi_delegate -- \
  bash "$server_wrapper"

claude mcp get qiqi_delegate >/dev/null

printf 'Claude Code workspace adapter configured. Start QiQi with: cd %q && claude\n' "$workspace_root"
