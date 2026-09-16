#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_root="$home/skills"
codex_root="${HOME}/.agents/skills"
claude_root="${HOME}/.claude/skills"
skills=(
  work-item
  work-item-intake
  work-item-investigate
  work-item-plan
  work-item-review
)

usage() {
  cat <<'EOF'
Usage: install-user-skill.sh [--codex-root PATH] [--claude-root PATH]

Installs the managed Work Item Agent Skill bundle (`work-item` plus phase
clarification skills) for user-scope discovery by Codex and Claude Code. Existing
unrelated skills with the same names are not silently overwritten.
EOF
}

while (($#)); do
  case "$1" in
    --codex-root)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      codex_root="$2"
      shift 2
      ;;
    --claude-root)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      claude_root="$2"
      shift 2
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

for skill in "${skills[@]}"; do
  [[ -f "$source_root/$skill/SKILL.md" ]] || {
    printf 'ERROR: missing source skill: %s/%s/SKILL.md\n' "$source_root" "$skill" >&2
    exit 66
  }
done

command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: missing command: python3\n' >&2
  exit 69
}

normalize_path() {
  python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$1"
}

skill_tree_matches() {
  python3 - "$1" "$2" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
marker = ".agent-knowledge-harness-managed"


def snapshot(root: Path):
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

codex_root="$(normalize_path "$codex_root")"
claude_root="$(normalize_path "$claude_root")"

preflight_skill() {
  local client="$1"
  local root="$2"
  local skill="$3"
  local source="$source_root/$skill"
  local target="$root/$skill"
  local marker="$target/.agent-knowledge-harness-managed"

  if [[ -e "$target" && ! -d "$target" ]]; then
    printf 'ERROR: %s skill target exists and is not a directory: %s\n' "$client" "$target" >&2
    return 78
  fi

  if [[ -d "$target" && ! -f "$marker" ]] && ! skill_tree_matches "$source" "$target"; then
    printf 'ERROR: %s skill `%s` already exists and is not an identical managed tree: %s\n' \
      "$client" "$skill" "$target" >&2
    printf 'Move/remove that skill explicitly, then rerun installer.\n' >&2
    return 78
  fi
}

# Preflight the complete bundle for both clients before the first mutation. A conflict
# in one phase skill must not leave a partially updated Work Item skill set behind.
for client in Codex Claude; do
  if [[ "$client" == Codex ]]; then
    root="$codex_root"
  else
    root="$claude_root"
  fi
  for skill in "${skills[@]}"; do
    preflight_skill "$client" "$root" "$skill"
  done
done

install_skill() {
  local client="$1"
  local root="$2"
  local skill="$3"
  local source="$source_root/$skill"
  local target="$root/$skill"
  local marker="$target/.agent-knowledge-harness-managed"
  local temp_parent temp

  mkdir -p "$root"

  if [[ -d "$target" && ! -f "$marker" ]]; then
    # Preflight already proved this is an exact unmanaged tree. Adopt it without
    # replacing user bytes, but only after the entire bundle has passed preflight.
    printf 'Adopting existing identical %s skill tree: %s\n' "$client" "$target"
    : > "$marker"
    return 0
  fi

  temp_parent="$(mktemp -d "$root/.${skill}.XXXXXX")"
  temp="$temp_parent/$skill"
  cp -R "$source" "$temp"
  : > "$temp/.agent-knowledge-harness-managed"

  if [[ -d "$target" ]]; then
    rm -rf "$target"
  fi
  mv "$temp" "$target"
  rmdir "$temp_parent"

  printf '%s skill installed: %s/SKILL.md\n' "$client" "$target"
}

for client in Codex Claude; do
  if [[ "$client" == Codex ]]; then
    root="$codex_root"
  else
    root="$claude_root"
  fi
  for skill in "${skills[@]}"; do
    install_skill "$client" "$root" "$skill"
  done
done

printf 'Open a fresh agent session if the skills are not already visible in the skills list.\n'
