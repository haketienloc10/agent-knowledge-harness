#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
server_wrapper="$workspace_root/scripts/qiqi-mcp-server.sh"
claude_dir="$workspace_root/.claude"
claude_md="$claude_dir/CLAUDE.md"
settings_path="$claude_dir/settings.json"
repos_yaml="$workspace_root/repos.yaml"
children_only=0

usage() {
  cat <<'EOF'
Usage: bash scripts/setup-claude.sh [--children-only]

Default mode configures Claude Code as a QiQi coordinator and provisions nested
repository child isolation. --children-only provisions only repo-local isolation
for Claude execution agents without enabling Claude as a workspace coordinator.
EOF
}

while (($#)); do
  case "$1" in
    --children-only)
      children_only=1
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

command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: missing command: python3\n' >&2
  exit 69
}
command -v yq >/dev/null 2>&1 || {
  printf 'ERROR: missing command: yq v4\n' >&2
  exit 69
}
command -v git >/dev/null 2>&1 || {
  printf 'ERROR: missing command: git\n' >&2
  exit 69
}

[[ -f "$repos_yaml" ]] || {
  printf 'ERROR: missing workspace registry: %s\n' "$repos_yaml" >&2
  exit 66
}

if ((children_only == 0)); then
  command -v claude >/dev/null 2>&1 || {
    printf 'ERROR: missing command: claude\n' >&2
    exit 69
  }
  [[ -f "$server_wrapper" ]] || {
    printf 'ERROR: missing qiqi_delegate wrapper: %s\n' "$server_wrapper" >&2
    exit 66
  }

  mkdir -p "$claude_dir"

  # Keep coordinator policy in .claude/CLAUDE.md instead of workspace/CLAUDE.md.
  # Claude can discover ancestor .claude/CLAUDE.md from nested repositories, so each
  # registered child repository receives a machine-local claudeMdExcludes entry below.
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
fi

# Nested repo Claude sessions must not inherit the workspace coordinator policy.
# The exclusion requires an absolute path, so generate it machine-locally instead of
# committing it to any repository. settings.local.json is also excluded through
# .git/info/exclude to keep repository worktrees clean.
workspace_claude_md=""
if [[ -f "$claude_md" ]]; then
  workspace_claude_md="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$claude_md")"
fi

while IFS= read -r relative_repo; do
  [[ -n "$relative_repo" && "$relative_repo" != "null" ]] || continue
  repo_root="$(python3 -c 'import os,sys; print(os.path.realpath(os.path.join(sys.argv[1], sys.argv[2])))' "$workspace_root" "$relative_repo")"
  [[ -d "$repo_root" ]] || {
    printf 'ERROR: repository path does not exist: %s\n' "$repo_root" >&2
    exit 66
  }
  git_root="$(git -C "$repo_root" rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "$git_root" && "$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$git_root")" == "$repo_root" ]] || {
    printf 'ERROR: repos.yaml path must resolve to exact Git root: %s\n' "$repo_root" >&2
    exit 66
  }

  child_claude_dir="$repo_root/.claude"
  child_settings="$child_claude_dir/settings.local.json"
  mkdir -p "$child_claude_dir"

  python3 - "$child_settings" "$workspace_claude_md" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
workspace_claude_md = sys.argv[2]
if path.exists():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: invalid Claude child settings JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: Claude child settings must be a JSON object: {path}")
else:
    data = {}

if workspace_claude_md:
    excludes = data.setdefault("claudeMdExcludes", [])
    if not isinstance(excludes, list) or not all(isinstance(item, str) for item in excludes):
        raise SystemExit(f"ERROR: claudeMdExcludes must be a string list: {path}")
    if workspace_claude_md not in excludes:
        excludes.append(workspace_claude_md)

data["autoMemoryEnabled"] = False
env = data.setdefault("env", {})
if not isinstance(env, dict):
    raise SystemExit(f"ERROR: Claude child settings env must be an object: {path}")
env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"

path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

  info_exclude="$repo_root/.git/info/exclude"
  mkdir -p "$(dirname "$info_exclude")"
  touch "$info_exclude"
  if ! grep -Fxq '.claude/settings.local.json' "$info_exclude"; then
    printf '.claude/settings.local.json\n' >> "$info_exclude"
  fi
  printf 'Claude child isolation: %s\n' "$repo_root"
done < <(yq -r '.repositories[].path' "$repos_yaml")

if ((children_only)); then
  printf 'Claude Code child isolation configured for registered repositories.\n'
  exit 0
fi

cd "$workspace_root"

# qiqi_delegate belongs to the QiQi coordinator project only. Keep it local-scope
# so repository child sessions do not inherit the orchestration MCP capability.
claude mcp remove qiqi_delegate --scope local >/dev/null 2>&1 || true
claude mcp add --scope local --transport stdio qiqi_delegate -- \
  bash "$server_wrapper"

claude mcp get qiqi_delegate >/dev/null

printf 'Claude Code workspace adapter configured. Start QiQi with: cd %q && claude\n' "$workspace_root"
