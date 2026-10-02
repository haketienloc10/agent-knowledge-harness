#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
name="ste-vi"
source_skill="$home/skills/$name"
codex_root="${CODEX_HOME:-${HOME}/.codex}/skills"
claude_root="${HOME}/.claude/skills"

usage() {
  cat <<'USAGE'
Usage: install-user-skill.sh [--codex-root PATH] [--claude-root PATH]

Installs the managed `ste-vi` Agent Skill for user-scope discovery by
Codex and Claude Code. Existing unrelated skills with the same name are not
silently overwritten.
USAGE
}

while (($#)); do
  case "$1" in
    --codex-root) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; codex_root="$2"; shift 2 ;;
    --claude-root) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; claude_root="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: unknown argument: %s\n' "$1" >&2; usage >&2; exit 64 ;;
  esac
done

[[ -f "$source_skill/SKILL.md" ]] || {
  printf 'ERROR: missing source skill: %s/SKILL.md\n' "$source_skill" >&2
  exit 66
}

preflight_skill() {
  local client="$1" root="$2"
  local target="$root/$name"
  local marker="$target/.agent-knowledge-harness-managed"

  if [[ -e "$target" && ! -d "$target" ]]; then
    printf 'ERROR: %s skill target exists and is not a directory: %s\n' "$client" "$target" >&2
    return 78
  fi

  if [[ -d "$target" && ! -f "$marker" ]]; then
    printf 'ERROR: %s skill `%s` already exists and is not managed by this harness: %s\n' \
      "$client" "$name" "$target" >&2
    printf 'Move/remove that skill explicitly, then rerun installer.\n' >&2
    return 78
  fi
}

install_skill() {
  local client="$1" root="$2"
  local target="$root/$name"
  local temp_parent

  mkdir -p "$root"
  temp_parent="$(mktemp -d "$root/.$name.XXXXXX")"
  cp -R "$source_skill" "$temp_parent/$name"
  : > "$temp_parent/$name/.agent-knowledge-harness-managed"
  if [[ -d "$target" ]]; then
    rm -rf "$target"
  fi
  mv "$temp_parent/$name" "$target"
  rmdir "$temp_parent"

  printf '%s skill installed: %s/SKILL.md\n' "$client" "$target"
}

# Validate both destinations before mutating either one.
preflight_skill 'Codex' "$codex_root"
preflight_skill 'Claude' "$claude_root"

install_skill 'Codex' "$codex_root"
install_skill 'Claude' "$claude_root"

printf 'Open a fresh agent session if the skill is not already visible in the skills list.\n'
