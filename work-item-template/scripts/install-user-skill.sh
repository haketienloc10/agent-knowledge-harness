#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_skill="$home/skills/work-item"
codex_root="${HOME}/.agents/skills"
claude_root="${HOME}/.claude/skills"

usage() {
  cat <<'EOF'
Usage: install-user-skill.sh [--codex-root PATH] [--claude-root PATH]

Installs the managed `work-item` Agent Skill for user-scope discovery by Codex and
Claude Code. Existing unrelated skills with the same name are not silently overwritten.
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

[[ -f "$source_skill/SKILL.md" ]] || {
  printf 'ERROR: missing source skill: %s/SKILL.md\n' "$source_skill" >&2
  exit 66
}

command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: missing command: python3\n' >&2
  exit 69
}

normalize_path() {
  python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$1"
}

skill_tree_matches() {
  python3 - "$source_skill" "$1" <<'PY'
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

install_skill() {
  local client="$1"
  local root="$2"
  local target="$root/work-item"
  local marker="$target/.agent-knowledge-harness-managed"
  local temp_parent temp

  mkdir -p "$root"

  if [[ -e "$target" && ! -d "$target" ]]; then
    printf 'ERROR: %s skill target exists and is not a directory: %s\n' "$client" "$target" >&2
    return 78
  fi

  if [[ -d "$target" && ! -f "$marker" ]]; then
    # The filesystem Work Item protocol depends on SKILL.md plus its templates.
    # Adopt only an exact unmanaged tree; matching SKILL.md alone can hide missing
    # or stale templates and would make a broken install look harness-managed.
    if skill_tree_matches "$target"; then
      printf 'Adopting existing identical %s skill tree: %s\n' "$client" "$target"
      : > "$marker"
      return 0
    fi
    printf 'ERROR: %s skill `work-item` already exists and is not an identical managed tree: %s\n' \
      "$client" "$target" >&2
    printf 'Move/remove that skill explicitly, then rerun installer.\n' >&2
    return 78
  fi

  temp_parent="$(mktemp -d "$root/.work-item.XXXXXX")"
  temp="$temp_parent/work-item"
  cp -R "$source_skill" "$temp"
  : > "$temp/.agent-knowledge-harness-managed"

  if [[ -d "$target" ]]; then
    rm -rf "$target"
  fi
  mv "$temp" "$target"
  rmdir "$temp_parent"

  printf '%s skill installed: %s/SKILL.md\n' "$client" "$target"
}

install_skill 'Codex' "$codex_root"
install_skill 'Claude' "$claude_root"

printf 'Open a fresh agent session if the skill is not already visible in the skills list.\n'