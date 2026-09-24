#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

skill="$home/skills/work-item"
phase_files=(
  phases/intake.md
  phases/investigation.md
  phases/planning.md
  phases/review.md
)

[[ -f "$skill/SKILL.md" ]] || fail 'missing work-item SKILL.md'
[[ -f "$skill/scripts/read.py" ]] || fail 'missing bounded Work Item reader'
for rel in "${phase_files[@]}"; do
  [[ -f "$skill/$rel" ]] || fail "missing Work Item phase protocol: $rel"
done

# Phase protocols are internal references of one workspace skill, not globally
# discoverable sibling skills.
for old in work-item-intake work-item-investigate work-item-plan work-item-review; do
  [[ ! -e "$home/skills/$old" ]] || fail "phase must not be a separate Agent Skill: skills/$old"
done

parent="$skill/SKILL.md"
for pattern in \
  'workspace/QiQi protocol' \
  'Repository child MUST NOT rewrite canonical dossier' \
  'phases/intake.md' \
  'phases/investigation.md' \
  'phases/planning.md' \
  'phases/review.md' \
  'ready' \
  'needs_user_clarification' \
  'needs_discovery' \
  'blocked' \
  'clarify meaning, not mechanics' \
  'Không load cả bốn phase references như startup ceremony' \
  'không tạo dossier directory mới trước intake gate' \
  'needs_user_clarification` → `status: waiting`' \
  'blocked` → `status: blocked`' \
  'không để lại empty/orphan dossier' \
  'Bounded hydration contract' \
  'current-turn objective/acceptance slice' \
  'truncation = incomplete coverage'; do
  grep -Fiq -- "$pattern" "$parent" || fail "work-item skill missing phase/role contract: $pattern"
done

for pattern in \
  'Requirement unknown' \
  'Domain/terminology unknown' \
  'Implementation unknown' \
  'Safe reversible assumption' \
  'exact repository/module **không phải** điều kiện' \
  'Gate không được tạo orphan directory' \
  'needs_user_clarification` → `status: waiting`' \
  'blocked` → `status: blocked`'; do
  grep -Fq -- "$pattern" "$skill/phases/intake.md" || fail "intake phase missing contract: $pattern"
done

for pattern in \
  'discovery over user questioning' \
  'repository/module/service ownership' \
  'Proposed investigation target' \
  'Không expand thành full implementation plan'; do
  grep -Fiq -- "$pattern" "$skill/phases/investigation.md" || fail "investigation phase missing contract: $pattern"
done

for pattern in \
  'Agent-owned technical choices should stay agent-owned' \
  'product behavior' \
  'Verification strategy' \
  'Không hỏi user chọn giữa implementation styles'; do
  grep -Fiq -- "$pattern" "$skill/phases/planning.md" || fail "planning phase missing contract: $pattern"
done

for pattern in \
  '**implemented**' \
  '**verified**' \
  '**accepted**' \
  'satisfied | not-satisfied | unresolved' \
  'actual evidence'; do
  grep -Fq -- "$pattern" "$skill/phases/review.md" || fail "review phase missing contract: $pattern"
done

installer="$home/scripts/install-workspace-skill.sh"
compat="$home/scripts/install-user-skill.sh"
[[ -f "$installer" ]] || fail 'missing workspace skill installer'
[[ -f "$compat" ]] || fail 'missing compatibility installer wrapper'
for pattern in \
  'WORKSPACE/.agents/skills/work-item' \
  'WORKSPACE/.claude/skills/work-item' \
  'repos.yaml' \
  'identity.md' \
  'Repository children do not' \
  'Preflight all workspace and legacy-global surfaces before the first mutation' \
  '[[ -L "$target" ]]' \
  'Removed legacy global harness-managed Work Item skill'; do
  grep -Fq -- "$pattern" "$installer" || fail "workspace installer missing contract: $pattern"
done

grep -Fq 'install-workspace-skill.sh' "$compat" || fail 'compat installer does not redirect to workspace installer'
grep -Fq '[[ -L "$target" || ( -e "$target" && ! -d "$target" ) ]]' "$compat" || \
  fail 'compat installer must reject dangling/symlink targets during preflight'
bash -n "$installer"
bash -n "$compat"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
source_skill="$home/skills/work-item"
marker='.agent-knowledge-harness-managed'

make_workspace() {
  local root="$1"
  mkdir -p "$root"
  printf 'repositories: []\n' > "$root/repos.yaml"
  printf 'name: test-workspace\n' > "$root/identity.md"
}

# Normal install is workspace-scoped for both parent clients and does not copy the
# lifecycle skill into a repository child.
workspace="$tmp/workspace"
home_dir="$tmp/home-normal"
mkdir -p "$home_dir"
make_workspace "$workspace"
mkdir -p "$workspace/repo-a"
(
  export HOME="$home_dir"
  unset CODEX_HOME
  bash "$installer" "$workspace" >/dev/null
)
for target in \
  "$workspace/.agents/skills/work-item" \
  "$workspace/.claude/skills/work-item"; do
  [[ -f "$target/SKILL.md" ]] || fail "workspace installer missed $target/SKILL.md"
  [[ -f "$target/scripts/read.py" ]] || fail "workspace installer missed $target/scripts/read.py"
  [[ -f "$target/$marker" ]] || fail "workspace managed marker missing: $target"
  if ! python3 - "$source_skill" "$target" "$marker" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
marker = sys.argv[3]

def snap(root):
    out = {}
    for p in root.rglob('*'):
        rel = p.relative_to(root).as_posix()
        if rel == marker:
            continue
        out[rel] = ('dir', None) if p.is_dir() else ('file', p.read_bytes())
    return out

raise SystemExit(0 if snap(source) == snap(target) else 1)
PY
  then
    fail "installed workspace skill tree drifted: $target"
  fi
done
[[ ! -e "$workspace/repo-a/.agents/skills/work-item" ]] || fail 'installer copied Work Item skill into repo child'
[[ ! -e "$workspace/repo-a/.claude/skills/work-item" ]] || fail 'installer copied Work Item skill into repo child'

# A dangling workspace skill symlink must fail in preflight before the other client
# is mutated. Bash -e/-d alone do not treat a dangling symlink as an existing target.
workspace_symlink="$tmp/workspace-symlink"
home_symlink="$tmp/home-symlink"
make_workspace "$workspace_symlink"
mkdir -p "$home_symlink" "$workspace_symlink/.agents/skills"
ln -s "$tmp/missing-work-item-target" "$workspace_symlink/.agents/skills/work-item"
if (
  export HOME="$home_symlink"
  unset CODEX_HOME
  bash "$installer" "$workspace_symlink" >/dev/null 2>&1
); then
  fail 'installer must reject dangling workspace skill symlink'
fi
[[ -L "$workspace_symlink/.agents/skills/work-item" ]] || fail 'installer mutated dangling workspace skill symlink'
[[ ! -e "$workspace_symlink/.claude/skills/work-item" ]] || fail 'dangling Codex symlink caused partial Claude workspace install'

# Historical harness-managed global copies are cleanup candidates only and are
# removed after successful workspace installation.
workspace_cleanup="$tmp/workspace-cleanup"
home_cleanup="$tmp/home-cleanup"
make_workspace "$workspace_cleanup"
for target in \
  "$home_cleanup/.agents/skills/work-item" \
  "$home_cleanup/.codex/skills/work-item" \
  "$home_cleanup/.claude/skills/work-item"; do
  mkdir -p "$(dirname "$target")"
  cp -R "$source_skill" "$target"
  : > "$target/$marker"
done
(
  export HOME="$home_cleanup"
  unset CODEX_HOME
  bash "$installer" "$workspace_cleanup" >/dev/null
)
for target in \
  "$home_cleanup/.agents/skills/work-item" \
  "$home_cleanup/.codex/skills/work-item" \
  "$home_cleanup/.claude/skills/work-item"; do
  [[ ! -e "$target" ]] || fail "legacy global managed copy was not removed: $target"
done
[[ -f "$workspace_cleanup/.agents/skills/work-item/SKILL.md" ]] || fail 'Codex workspace target missing after legacy cleanup'
[[ -f "$workspace_cleanup/.claude/skills/work-item/SKILL.md" ]] || fail 'Claude workspace target missing after legacy cleanup'

# Unmanaged global same-name skill fails before workspace mutation, preventing
# ambiguous discovery and avoiding deletion of user-owned content.
workspace_conflict="$tmp/workspace-conflict"
home_conflict="$tmp/home-conflict"
make_workspace "$workspace_conflict"
mkdir -p "$home_conflict/.agents/skills/work-item"
printf '%s\n' '---' 'name: unrelated-work-item' '---' > "$home_conflict/.agents/skills/work-item/SKILL.md"
if (
  export HOME="$home_conflict"
  unset CODEX_HOME
  bash "$installer" "$workspace_conflict" >/dev/null 2>&1
); then
  fail 'installer must reject unmanaged global same-name Work Item skill'
fi
[[ ! -e "$workspace_conflict/.agents/skills/work-item" ]] || fail 'global conflict caused partial Codex workspace install'
[[ ! -e "$workspace_conflict/.claude/skills/work-item" ]] || fail 'global conflict caused partial Claude workspace install'
grep -Fq 'name: unrelated-work-item' "$home_conflict/.agents/skills/work-item/SKILL.md" || fail 'installer mutated unmanaged global skill'

printf 'Work Item workspace skill + phase protocols: OK\n'
