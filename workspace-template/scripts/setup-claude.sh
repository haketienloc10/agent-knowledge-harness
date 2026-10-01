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

Machine-local absolute claudeMdExcludes entries are written only to each repository's
canonical Claude project-local settings file and excluded through Git's common info/exclude.
For linked worktrees, Claude reads the local settings file at the main checkout root.
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

for command in python3 yq git; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: missing command: %s\n' "$command" >&2
    exit 69
  }
done

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

  # Claude Code does not read AGENTS.md directly. Keep the coordinator adapter under
  # .claude/ so the workspace can still launch with a plain `claude` command. Nested
  # repositories explicitly exclude this file through machine-local settings below.
  if [[ ! -f "$claude_md" ]]; then
    printf '@../AGENTS.md\n' > "$claude_md"
  elif ! grep -Fxq '@../AGENTS.md' "$claude_md"; then
    printf '\n@../AGENTS.md\n' >> "$claude_md"
  fi

  # Preserve unrelated project settings while enforcing QiQi coordinator boundaries.
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

# Claude can discover the workspace coordinator CLAUDE.md from nested repositories.
# claudeMdExcludes matches absolute paths, so generate the exclusion machine-locally
# instead of committing a machine-specific path to any repository.
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
  [[ -n "$git_root" ]] || {
    printf 'ERROR: repository path is not a Git repository: %s\n' "$repo_root" >&2
    exit 66
  }
  git_root="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$git_root")"
  [[ "$git_root" == "$repo_root" ]] || {
    printf 'ERROR: repos.yaml path must resolve to exact Git root: %s\n' "$repo_root" >&2
    exit 66
  }

  child_settings_rel='.claude/settings.local.json'
  if git -C "$repo_root" ls-files --error-unmatch "$child_settings_rel" >/dev/null 2>&1; then
    printf 'ERROR: %s is tracked in repository %s; refusing to write machine-local absolute paths\n' \
      "$child_settings_rel" "$repo_root" >&2
    exit 78
  fi

  # Claude Code stores project-local settings at the main checkout root for linked
  # worktrees. --git-common-dir resolves to <main-checkout>/.git for both ordinary
  # repositories and linked worktrees, so its parent is the canonical settings root.
  git_common_dir="$(git -C "$repo_root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [[ -z "$git_common_dir" ]]; then
    git_common_dir="$(git -C "$repo_root" rev-parse --git-common-dir)"
    if [[ "$git_common_dir" != /* ]]; then
      git_common_dir="$repo_root/$git_common_dir"
    fi
  fi
  git_common_dir="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$git_common_dir")"
  settings_repo_root="$(python3 -c 'import os,sys; print(os.path.dirname(os.path.realpath(sys.argv[1])))' "$git_common_dir")"
  [[ -d "$settings_repo_root" ]] || {
    printf 'ERROR: canonical Claude settings root does not exist: %s\n' "$settings_repo_root" >&2
    exit 66
  }

  child_claude_dir="$settings_repo_root/.claude"
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

  info_exclude="$git_common_dir/info/exclude"
  mkdir -p "$(dirname "$info_exclude")"
  touch "$info_exclude"
  if ! grep -Fxq "$child_settings_rel" "$info_exclude"; then
    printf '%s\n' "$child_settings_rel" >> "$info_exclude"
  fi

  if [[ "$settings_repo_root" == "$repo_root" ]]; then
    printf 'Claude child isolation: %s\n' "$repo_root"
  else
    printf 'Claude child isolation: %s (local settings at main checkout %s)\n' \
      "$repo_root" "$settings_repo_root"
  fi
done < <(yq -r '.repositories[].path' "$repos_yaml")

if ((children_only)); then
  printf 'Claude Code child isolation configured for registered repositories.\n'
  exit 0
fi

cd "$workspace_root"

# qiqi_delegate belongs to the QiQi coordinator project only. Local scope keeps the
# orchestration tool out of independent repository child projects.
claude mcp remove qiqi_delegate --scope local >/dev/null 2>&1 || true
claude mcp add --scope local --transport stdio qiqi_delegate -- \
  bash "$server_wrapper"
claude mcp get qiqi_delegate >/dev/null

printf 'Claude Code workspace adapter configured. Start QiQi with: cd %q && claude\n' "$workspace_root"
