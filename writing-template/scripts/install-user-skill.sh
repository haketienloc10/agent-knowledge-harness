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
silently overwritten. A same-name symlink is rejected explicitly.
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

preflight_root() {
  local client="$1" root="$2"
  local probe="$root"
  local parent

  # Existing roots must resolve to directories. For a missing root, walk upward
  # to the nearest existing ancestor so mkdir -p cannot later fail on a file.
  while [[ ! -e "$probe" && ! -L "$probe" ]]; do
    parent="$(dirname "$probe")"
    [[ "$parent" != "$probe" ]] || break
    probe="$parent"
  done

  if [[ -L "$probe" && ! -d "$probe" ]]; then
    printf 'ERROR: %s skill root has an unusable symlink ancestor: %s\n' "$client" "$probe" >&2
    return 78
  fi

  if [[ -e "$probe" && ! -d "$probe" ]]; then
    printf 'ERROR: %s skill root has a non-directory ancestor: %s\n' "$client" "$probe" >&2
    return 78
  fi
}

preflight_skill() {
  local client="$1" root="$2"
  local target="$root/$name"
  local marker="$target/.agent-knowledge-harness-managed"

  # Test -L before -e/-d because a dangling symlink is neither -e nor -d.
  if [[ -L "$target" ]]; then
    printf 'ERROR: %s skill target is a symlink and will not be replaced: %s\n' "$client" "$target" >&2
    printf 'Move/remove the symlink explicitly, then rerun installer.\n' >&2
    return 78
  fi

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

stage_skill() {
  local client="$1" root="$2" result_var="$3"
  local temp_parent

  mkdir -p "$root" || {
    printf 'ERROR: cannot create %s skill root: %s\n' "$client" "$root" >&2
    return 78
  }

  temp_parent="$(mktemp -d "$root/.$name.XXXXXX")" || {
    printf 'ERROR: cannot create staging directory in %s skill root: %s\n' "$client" "$root" >&2
    return 78
  }

  if ! cp -R "$source_skill" "$temp_parent/$name"; then
    rm -rf "$temp_parent"
    return 1
  fi

  if ! : > "$temp_parent/$name/.agent-knowledge-harness-managed"; then
    rm -rf "$temp_parent"
    return 1
  fi

  printf -v "$result_var" '%s' "$temp_parent"
}

reserve_backup_path() {
  local root="$1" result_var="$2"
  local placeholder

  placeholder="$(mktemp -d "$root/.$name.backup.XXXXXX")" || return 1
  rmdir "$placeholder" || return 1
  printf -v "$result_var" '%s' "$placeholder"
}

rollback_target() {
  local target="$1" backup="$2" had_original="$3"

  if [[ -e "$target" || -L "$target" ]]; then
    rm -rf "$target" || true
  fi
  if [[ "$had_original" == "1" && -n "$backup" && -d "$backup" ]]; then
    mv "$backup" "$target" || true
  fi
}

commit_staged() {
  local client="$1" root="$2" stage="$3" backup="$4" had_original="$5"
  local target="$root/$name"

  if [[ "$had_original" == "1" ]]; then
    if ! mv "$target" "$backup"; then
      printf 'ERROR: cannot move existing %s skill aside: %s\n' "$client" "$target" >&2
      return 1
    fi
  fi

  if ! mv "$stage/$name" "$target"; then
    printf 'ERROR: cannot install staged %s skill: %s\n' "$client" "$target" >&2
    if [[ "$had_original" == "1" && -d "$backup" ]]; then
      mv "$backup" "$target" || true
    fi
    return 1
  fi

  rmdir "$stage" || true
}

# Validate both roots and destinations before preparing either target.
preflight_root 'Codex' "$codex_root"
preflight_root 'Claude' "$claude_root"
preflight_skill 'Codex' "$codex_root"
preflight_skill 'Claude' "$claude_root"

codex_stage=""
claude_stage=""
codex_backup=""
claude_backup=""
codex_had_original=0
claude_had_original=0

cleanup() {
  if [[ -n "$codex_stage" && -d "$codex_stage" ]]; then
    rm -rf "$codex_stage"
  fi
  if [[ -n "$claude_stage" && -d "$claude_stage" ]]; then
    rm -rf "$claude_stage"
  fi
  if [[ -n "$codex_backup" && -d "$codex_backup" ]]; then
    rm -rf "$codex_backup"
  fi
  if [[ -n "$claude_backup" && -d "$claude_backup" ]]; then
    rm -rf "$claude_backup"
  fi
}
trap cleanup EXIT

# Stage both complete copies first. This verifies that both roots are writable
# before either installed skill is touched.
stage_skill 'Codex' "$codex_root" codex_stage
stage_skill 'Claude' "$claude_root" claude_stage

if [[ -d "$codex_root/$name" ]]; then
  codex_had_original=1
  reserve_backup_path "$codex_root" codex_backup
fi
if [[ -d "$claude_root/$name" ]]; then
  claude_had_original=1
  reserve_backup_path "$claude_root" claude_backup
fi

# Commit Codex, then Claude. Keep Codex backup until Claude succeeds so a
# second-client failure can roll back the first client.
if ! commit_staged 'Codex' "$codex_root" "$codex_stage" "$codex_backup" "$codex_had_original"; then
  exit 1
fi
codex_stage=""

if ! commit_staged 'Claude' "$claude_root" "$claude_stage" "$claude_backup" "$claude_had_original"; then
  rollback_target "$codex_root/$name" "$codex_backup" "$codex_had_original"
  exit 1
fi
claude_stage=""

if [[ -n "$codex_backup" && -d "$codex_backup" ]]; then
  rm -rf "$codex_backup"
fi
if [[ -n "$claude_backup" && -d "$claude_backup" ]]; then
  rm -rf "$claude_backup"
fi
codex_backup=""
claude_backup=""

trap - EXIT
printf 'Codex skill installed: %s/SKILL.md\n' "$codex_root/$name"
printf 'Claude skill installed: %s/SKILL.md\n' "$claude_root/$name"
printf 'Open a fresh agent session if the skill is not already visible in the skills list.\n'
