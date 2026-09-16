#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

skills=(
  work-item
  work-item-intake
  work-item-investigate
  work-item-plan
  work-item-review
)

for skill in "${skills[@]}"; do
  [[ -f "$home/skills/$skill/SKILL.md" ]] || fail "missing phase skill: skills/$skill/SKILL.md"
done

parent="$home/skills/work-item/SKILL.md"
for pattern in \
  '$work-item-intake' \
  '$work-item-investigate' \
  '$work-item-plan' \
  '$work-item-review' \
  'ready' \
  'needs_user_clarification' \
  'needs_discovery' \
  'blocked' \
  'clarify meaning, not mechanics'; do
  grep -Fiq -- "$pattern" "$parent" || fail "parent Work Item skill missing phase-gate contract: $pattern"
done

intake="$home/skills/work-item-intake/SKILL.md"
for pattern in \
  'mandatory semantic gate' \
  'Requirement unknown' \
  'Domain/terminology unknown' \
  'Implementation unknown' \
  'Safe reversible assumption' \
  'Knowing the exact repository/module is **not** required'; do
  grep -Fq -- "$pattern" "$intake" || fail "intake skill missing contract: $pattern"
done

investigate="$home/skills/work-item-investigate/SKILL.md"
for pattern in \
  'Prefer **discovery over user questioning**' \
  'repository/module/service ownership' \
  'Proposed investigation target' \
  'Do not expand into a full implementation plan'; do
  grep -Fq -- "$pattern" "$investigate" || fail "investigation skill missing contract: $pattern"
done

plan="$home/skills/work-item-plan/SKILL.md"
for pattern in \
  '**Agent-owned technical choices should stay agent-owned.**' \
  'product behavior' \
  'Verification strategy' \
  'Do not ask the user to choose between implementation styles'; do
  grep -Fq -- "$pattern" "$plan" || fail "plan skill missing contract: $pattern"
done

review="$home/skills/work-item-review/SKILL.md"
for pattern in \
  '**mandatory completion gate**' \
  '**implemented**' \
  '**verified**' \
  '**accepted**' \
  'satisfied | not-satisfied | unresolved' \
  'actual evidence'; do
  grep -Fq -- "$pattern" "$review" || fail "review skill missing contract: $pattern"
done

installer="$home/scripts/install-user-skill.sh"
for skill in "${skills[@]}"; do
  grep -Fq -- "$skill" "$installer" || fail "installer does not manage skill: $skill"
done
grep -Fq -- 'before the first mutation' "$installer" || fail 'installer must preflight bundle before mutation'

bash -n "$installer"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

codex_root="$tmp/codex"
claude_root="$tmp/claude"
bash "$installer" --codex-root "$codex_root" --claude-root "$claude_root" >/dev/null
for root in "$codex_root" "$claude_root"; do
  for skill in "${skills[@]}"; do
    [[ -f "$root/$skill/SKILL.md" ]] || fail "installer missed $root/$skill/SKILL.md"
    [[ -f "$root/$skill/.agent-knowledge-harness-managed" ]] || fail "managed marker missing for $root/$skill"
  done
done

# A conflict in a later client/skill must fail during preflight, before Codex or any
# other non-conflicting target is installed.
conflict_codex="$tmp/conflict-codex"
conflict_claude="$tmp/conflict-claude"
mkdir -p "$conflict_claude/work-item-plan"
printf '%s\n' '---' 'name: unrelated-plan' '---' > "$conflict_claude/work-item-plan/SKILL.md"
if bash "$installer" --codex-root "$conflict_codex" --claude-root "$conflict_claude" >/dev/null 2>&1; then
  fail 'installer must reject unrelated same-name phase skill'
fi
for skill in "${skills[@]}"; do
  [[ ! -e "$conflict_codex/$skill" ]] || fail 'bundle conflict caused partial Codex installation'
done
grep -Fq 'name: unrelated-plan' "$conflict_claude/work-item-plan/SKILL.md" || \
  fail 'installer mutated unrelated same-name skill'

printf 'Work Item phase skills: OK\n'
