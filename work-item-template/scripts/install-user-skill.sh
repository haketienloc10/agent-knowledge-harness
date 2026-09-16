#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_skill="$home/skills/work-item"
marker='.agent-knowledge-harness-managed'

# Historical checker/automation may still pass explicit custom roots. Preserve that
# narrow compatibility surface without restoring any user-global default location.
if [[ "${1:-}" == '--codex-root' || "${1:-}" == '--claude-root' ]]; then
  codex_root=''
  claude_root=''
  while (($#)); do
    case "$1" in
      --codex-root)
        [[ $# -ge 2 ]] || { printf 'ERROR: --codex-root requires PATH\n' >&2; exit 64; }
        codex_root="$2"
        shift 2
        ;;
      --claude-root)
        [[ $# -ge 2 ]] || { printf 'ERROR: --claude-root requires PATH\n' >&2; exit 64; }
        claude_root="$2"
        shift 2
        ;;
      *)
        printf 'ERROR: unknown legacy installer argument: %s\n' "$1" >&2
        exit 64
        ;;
    esac
  done
  [[ -n "$codex_root" && -n "$claude_root" ]] || {
    printf 'ERROR: legacy custom-root compatibility requires both --codex-root and --claude-root\n' >&2
    exit 64
  }

  command -v python3 >/dev/null 2>&1 || { printf 'ERROR: missing command: python3\n' >&2; exit 69; }
  normalize_path() {
    python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$1"
  }
  tree_matches() {
    python3 - "$source_skill" "$1" "$marker" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1])
target = Path(sys.argv[2])
marker = sys.argv[3]

def snap(root):
    if root.is_symlink():
        return None
    out = {}
    for p in root.rglob('*'):
        rel = p.relative_to(root).as_posix()
        if rel == marker:
            continue
        if p.is_symlink():
            return None
        out[rel] = ('dir', None) if p.is_dir() else ('file', p.read_bytes())
    return out
raise SystemExit(0 if snap(source) == snap(target) else 1)
PY
  }
  codex_root="$(normalize_path "$codex_root")"
  claude_root="$(normalize_path "$claude_root")"

  for root in "$codex_root" "$claude_root"; do
    target="$root/work-item"
    if [[ -L "$target" || ( -e "$target" && ! -d "$target" ) ]]; then
      printf 'ERROR: legacy custom skill target is not a normal directory: %s\n' "$target" >&2
      exit 78
    fi
    if [[ -d "$target" && ! -f "$target/$marker" ]] && ! tree_matches "$target"; then
      printf 'ERROR: legacy custom skill target is not an identical managed tree: %s\n' "$target" >&2
      exit 78
    fi
  done

  for pair in "Codex:$codex_root" "Claude:$claude_root"; do
    client="${pair%%:*}"
    root="${pair#*:}"
    target="$root/work-item"
    mkdir -p "$root"
    if [[ -d "$target" && ! -f "$target/$marker" ]]; then
      : > "$target/$marker"
    else
      temp_parent="$(mktemp -d "$root/.work-item.XXXXXX")"
      temp="$temp_parent/work-item"
      cp -R "$source_skill" "$temp"
      : > "$temp/$marker"
      [[ ! -d "$target" ]] || rm -rf "$target"
      mv "$temp" "$target"
      rmdir "$temp_parent"
    fi
    printf 'WARNING: installed %s Work Item skill through deprecated explicit custom-root compatibility: %s/SKILL.md\n' "$client" "$target" >&2
  done
  exit 0
fi

printf 'WARNING: install-user-skill.sh is deprecated; Work Item is workspace-scoped. Use install-workspace-skill.sh WORKSPACE.\n' >&2
exec bash "$home/scripts/install-workspace-skill.sh" "$@"
