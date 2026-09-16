#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_skill="$home/skills/work-item"
marker_name='.agent-knowledge-harness-managed'

usage() {
  cat <<'EOF'
Usage: install-workspace-skill.sh WORKSPACE

Installs the managed `work-item` skill at workspace scope for both supported parent
agents:

  WORKSPACE/.agents/skills/work-item   (Codex workspace skill)
  WORKSPACE/.claude/skills/work-item   (Claude workspace skill)

The workspace must contain repos.yaml and identity.md. Repository children do not
receive their own copy; they use TaskPacket + read-only mounted Work Item context.

After both workspace targets install successfully, old user/global harness-managed
`work-item` copies are removed. Same-name global entries without the harness managed
marker are never deleted and cause a fail-closed error to avoid ambiguous discovery.
EOF
}

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 64
fi

command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: missing command: python3\n' >&2
  exit 69
}

normalize_path() {
  python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$1"
}

workspace="$(normalize_path "$1")"
[[ -d "$workspace" ]] || {
  printf 'ERROR: workspace does not exist: %s\n' "$workspace" >&2
  exit 66
}
[[ -f "$workspace/repos.yaml" && -f "$workspace/identity.md" ]] || {
  printf 'ERROR: workspace must contain repos.yaml and identity.md: %s\n' "$workspace" >&2
  exit 65
}
[[ -f "$source_skill/SKILL.md" ]] || {
  printf 'ERROR: missing source skill: %s/SKILL.md\n' "$source_skill" >&2
  exit 66
}

skill_tree_matches() {
  python3 - "$1" "$2" "$marker_name" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
marker = sys.argv[3]


def snapshot(root: Path):
    if root.is_symlink():
        return None
    result = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if rel == marker:
            continue
        if path.is_symlink():
            return None
        if path.is_dir():
            result[rel] = ("dir", None)
        elif path.is_file():
            result[rel] = ("file", path.read_bytes())
        else:
            return None
    return result


raise SystemExit(0 if snapshot(source) == snapshot(target) else 1)
PY
}

codex_root="$workspace/.agents/skills"
claude_root="$workspace/.claude/skills"
codex_target="$codex_root/work-item"
claude_target="$claude_root/work-item"
workspace_targets=("$codex_target" "$claude_target")

preflight_workspace_target() {
  local client="$1"
  local target="$2"
  local marker="$target/$marker_name"

  if [[ -L "$target" ]]; then
    printf 'ERROR: %s workspace skill target is a symlink: %s\n' "$client" "$target" >&2
    return 78
  fi
  if [[ -e "$target" && ! -d "$target" ]]; then
    printf 'ERROR: %s workspace skill target exists and is not a directory: %s\n' "$client" "$target" >&2
    return 78
  fi
  if [[ -d "$target" && ! -f "$marker" ]] && ! skill_tree_matches "$source_skill" "$target"; then
    printf 'ERROR: %s workspace skill `work-item` already exists and is not an identical managed tree: %s\n' \
      "$client" "$target" >&2
    printf 'Move/remove that workspace skill explicitly, then rerun installer.\n' >&2
    return 78
  fi
}

same_path() {
  [[ "$(normalize_path "$1")" == "$(normalize_path "$2")" ]]
}

legacy_global_targets=()
add_legacy_target() {
  local candidate="$1"
  local target
  target="$(normalize_path "$candidate")"
  local workspace_target
  for workspace_target in "${workspace_targets[@]}"; do
    if same_path "$target" "$workspace_target"; then
      return 0
    fi
  done
  local existing
  for existing in "${legacy_global_targets[@]:-}"; do
    [[ -n "$existing" ]] || continue
    if same_path "$target" "$existing"; then
      return 0
    fi
  done
  legacy_global_targets+=("$target")
}

# Historical harness releases used user/global skill roots. Keep these only as
# cleanup candidates; the runtime installation is workspace-scoped.
add_legacy_target "$HOME/.agents/skills/work-item"
add_legacy_target "${CODEX_HOME:-$HOME/.codex}/skills/work-item"
add_legacy_target "$HOME/.claude/skills/work-item"

preflight_legacy_global() {
  local target="$1"
  local marker="$target/$marker_name"

  [[ -e "$target" || -L "$target" ]] || return 0
  if [[ -L "$target" || ! -d "$target" ]]; then
    printf 'ERROR: legacy global `work-item` target is not a managed directory: %s\n' "$target" >&2
    return 78
  fi
  if [[ ! -f "$marker" ]]; then
    printf 'ERROR: unmanaged global `work-item` skill may shadow/duplicate workspace discovery: %s\n' "$target" >&2
    printf 'Move/remove it explicitly, then rerun installer. It will not be deleted automatically.\n' >&2
    return 78
  fi
}

# Preflight all workspace and legacy-global surfaces before the first mutation.
preflight_workspace_target 'Codex' "$codex_target"
preflight_workspace_target 'Claude' "$claude_target"
for target in "${legacy_global_targets[@]:-}"; do
  [[ -n "$target" ]] || continue
  preflight_legacy_global "$target"
done

install_target() {
  local client="$1"
  local target="$2"
  local root marker temp_parent temp
  root="$(dirname "$target")"
  marker="$target/$marker_name"

  mkdir -p "$root"

  if [[ -d "$target" && ! -f "$marker" ]]; then
    # Preflight proved this unmanaged workspace tree is byte-identical to source.
    printf 'Adopting existing identical %s workspace skill tree: %s\n' "$client" "$target"
    : > "$marker"
    return 0
  fi

  temp_parent="$(mktemp -d "$root/.work-item.XXXXXX")"
  temp="$temp_parent/work-item"
  cp -R "$source_skill" "$temp"
  : > "$temp/$marker_name"

  if [[ -d "$target" ]]; then
    rm -rf "$target"
  fi
  mv "$temp" "$target"
  rmdir "$temp_parent"

  printf '%s workspace skill installed: %s/SKILL.md\n' "$client" "$target"
}

install_target 'Codex' "$codex_target"
install_target 'Claude' "$claude_target"

# Cleanup happens only after both workspace installs succeed, and only for copies
# explicitly marked as harness-managed.
for target in "${legacy_global_targets[@]:-}"; do
  [[ -n "$target" ]] || continue
  if [[ -d "$target" && -f "$target/$marker_name" ]]; then
    rm -rf "$target"
    printf 'Removed legacy global harness-managed Work Item skill: %s\n' "$target"
  fi
done

printf 'Open a fresh QiQi parent session from the workspace root so workspace skill discovery refreshes.\n'
