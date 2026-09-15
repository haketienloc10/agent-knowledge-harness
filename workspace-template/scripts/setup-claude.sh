#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
server_wrapper="$workspace_root/scripts/qiqi-mcp-server.sh"
claude_dir="$workspace_root/.claude"
claude_md="$claude_dir/CLAUDE.md"
settings_path="$claude_dir/settings.json"

command -v claude >/dev/null 2>&1 || {
  printf 'ERROR: missing command: claude\n' >&2
  exit 69
}
command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: missing command: python3\n' >&2
  exit 69
}

[[ -f "$server_wrapper" ]] || {
  printf 'ERROR: missing qiqi_delegate wrapper: %s\n' "$server_wrapper" >&2
  exit 66
}

mkdir -p "$claude_dir"

# Keep coordinator policy in .claude/CLAUDE.md instead of workspace/CLAUDE.md.
# A root CLAUDE.md would be an ancestor memory file for nested repository children.
if [[ ! -f "$claude_md" ]]; then
  printf '@../AGENTS.md\n' > "$claude_md"
elif ! grep -Fxq '@../AGENTS.md' "$claude_md"; then
  printf '\n@../AGENTS.md\n' >> "$claude_md"
fi

# Preserve existing shared Claude settings while enforcing the QiQi boundaries.
python3 - "$settings_path" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if path.exists():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: invalid Claude settings JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: Claude settings must be a JSON object: {path}")
else:
    data = {}

# Keep the documented setting for visibility, and also set the environment variable
# because Claude Code treats CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 as the hard runtime guard.
data["autoMemoryEnabled"] = False
env = data.setdefault("env", {})
if not isinstance(env, dict):
    raise SystemExit(f"ERROR: Claude settings env must be an object: {path}")
env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"

permissions = data.setdefault("permissions", {})
if not isinstance(permissions, dict):
    raise SystemExit(f"ERROR: Claude settings permissions must be an object: {path}")
allow = permissions.setdefault("allow", [])
if not isinstance(allow, list) or not all(isinstance(item, str) for item in allow):
    raise SystemExit(f"ERROR: Claude settings permissions.allow must be a string list: {path}")
tool = "mcp__qiqi_delegate__delegate_repo_task"
if tool not in allow:
    allow.append(tool)

path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

cd "$workspace_root"

# qiqi_delegate belongs to the QiQi coordinator project only. Keep it local-scope
# so repository child sessions do not inherit the orchestration MCP capability.
claude mcp remove qiqi_delegate --scope local >/dev/null 2>&1 || true
claude mcp add --scope local --transport stdio qiqi_delegate -- \
  bash "$server_wrapper"

claude mcp get qiqi_delegate >/dev/null

printf 'Claude Code workspace adapter configured. Start QiQi with: cd %q && claude\n' "$workspace_root"
