#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
errors=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  errors=$((errors + 1))
}

require_file() {
  [[ -f "$repo_root/$1" ]] || fail "missing file: $1"
}

command -v git >/dev/null 2>&1 || fail 'missing required command: git'
command -v rg >/dev/null 2>&1 || fail 'missing required command: rg'

for path in AGENTS.md CLAUDE.md ARCHITECTURE.md docs/VERIFY.md docs/REPO_SETUP.md docs/friction/README.md scripts/repo-check.sh; do
  require_file "$path"
done

if git_root="$(git -C "$repo_root" rev-parse --show-toplevel 2>/dev/null)"; then
  [[ "$(cd "$git_root" && pwd)" == "$repo_root" ]] || fail "template must be installed at Git root: expected $git_root"
else
  fail "target is not a Git repository: $repo_root"
fi

if [[ -f "$repo_root/CLAUDE.md" ]]; then
  rg -qx '@AGENTS\.md' "$repo_root/CLAUDE.md" || fail 'CLAUDE.md: expected @AGENTS.md'
fi

agents="$repo_root/AGENTS.md"
for pattern in \
  '`ARCHITECTURE\.md`' \
  '`docs/VERIFY\.md`' \
  'current Git root' \
  '^## TaskPacket contract$' \
  'immutable semantic snapshot' \
  'objective' \
  'acceptance_criteria' \
  'trusted_facts' \
  'claims_to_investigate' \
  'trusted-for-execution' \
  '^### Task-semantic closed-world rule$' \
  'MUST NOT.*Work Item.*Shared Knowledge.*reconstruct missing task semantics' \
  'không `work_item_get`/`work_item_update`' \
  'stale detection' \
  '^## Shared Knowledge MCP$' \
  'reusable repo/domain implementation knowledge' \
  'knowledge_search' \
  'knowledge_read' \
  'knowledge_read_metadata' \
  'knowledge_read_section' \
  'knowledge_write' \
  'knowledge_update' \
  'Live owner source/test thắng' \
  '^## Handoff với QiQi$' \
  'Native final assistant response là authoritative semantic handoff' \
  'Runtime state là lifecycle truth' \
  '^## Greenfield technical authority$' \
  '^## Cross-repo Impact$'; do
  rg -U -q "$pattern" "$agents" || fail "AGENTS.md: missing required policy: $pattern"
done

rg -q 'Không đọc/sửa repository anh em' "$agents" || \
  fail 'AGENTS.md: sibling repository boundary missing'
rg -U -q 'Missing task semantics.*Work Item/Knowledge|không recover từ Work Item/Knowledge' "$agents" || \
  fail 'AGENTS.md: incomplete TaskPacket must not trigger orchestration-context recovery'
rg -U -q 'Shared Knowledge.*không phải fallback.*incomplete TaskPacket' "$agents" || \
  fail 'AGENTS.md: Knowledge task-semantic boundary missing'
for pattern in \
  'observable product semantics' \
  'external/public contract' \
  'security/compliance' \
  'cost/operational envelope'; do
  rg -q "$pattern" "$agents" || \
    fail "AGENTS.md: greenfield technical authority boundary missing: $pattern"
done
rg -U -q 'cross-repo impact:.*fact.*affected.*evidence.*next action' "$agents" || \
  fail 'AGENTS.md: actionable cross-repo handoff shape missing'

if rg -q 'TaskPacket `required_context`|original user request, repo-local objective|MUST apply `\$work-item`|Child được đọc toàn task' "$agents"; then
  fail 'AGENTS.md: legacy Work Item/user_request/required_context child contract found'
fi

if rg -q 'existing update target phải full-read|knowledge_read\(keywords|workspace `knowledge/`|knowledge/INDEX\.md|result_path|fixed result schema' "$agents"; then
  fail 'AGENTS.md: legacy knowledge/result contract found'
fi

setup="$repo_root/docs/REPO_SETUP.md"
for pattern in \
  'TaskPacket' \
  'immutable' \
  'Work Item.*QiQi' \
  'knowledge_search' \
  'knowledge_read' \
  'knowledge_read_metadata' \
  'knowledge_read_section' \
  'native final assistant response'; do
  rg -U -q "$pattern" "$setup" || fail "docs/REPO_SETUP.md: missing guidance: $pattern"
done
rg -qi 'task-semantic' "$setup" || \
  fail 'docs/REPO_SETUP.md: missing guidance: task-semantic'

for file in "$repo_root/AGENTS.md" "$repo_root/ARCHITECTURE.md" "$repo_root/docs/VERIFY.md"; do
  [[ -f "$file" ]] || continue
  rg -n '\{\{[^}]+\}\}' "$file" && fail "unresolved placeholder in ${file#$repo_root/}"
done

architecture="$repo_root/ARCHITECTURE.md"
rg -q '^## Repository responsibility$' "$architecture" || fail 'ARCHITECTURE.md: missing repository responsibility'
rg -q '^## Module map$' "$architecture" || fail 'ARCHITECTURE.md: missing module map'
rg -q '^## External boundaries$' "$architecture" || fail 'ARCHITECTURE.md: missing external boundaries'
rg -q '^## Constraints$' "$architecture" || fail 'ARCHITECTURE.md: missing constraints'

verify="$repo_root/docs/VERIFY.md"
rg -q '^## Bootstrap$' "$verify" || fail 'docs/VERIFY.md: missing bootstrap command'
rg -q '^## Kiểm tra nhanh$' "$verify" || fail 'docs/VERIFY.md: missing focused check'
rg -q '^## Test liên quan$' "$verify" || fail 'docs/VERIFY.md: missing related test command'
rg -q '^## Build hoặc kiểm tra đầy đủ$' "$verify" || fail 'docs/VERIFY.md: missing full verification command'
rg -q '^## Side effects$' "$verify" || fail 'docs/VERIFY.md: missing side-effect documentation'

bash -n "$repo_root/scripts/repo-check.sh" || fail 'scripts/repo-check.sh: invalid Bash syntax'

if ((errors > 0)); then
  printf 'repo-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi
printf 'repo-check: PASS\n'
