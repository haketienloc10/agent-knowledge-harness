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
  'Global Work Item MCP' \
  'work_item_get' \
  'work_item_update' \
  'revision conflict' \
  'current Git root' \
  '^### Material session reconciliation$' \
  'current effective repo truth' \
  'accumulated material phase/milestone history' \
  'artifact creation does not substitute|artifact creation không thay thế' \
  'Implementation session.*MUST reconcile Work Item' \
  'Review code\.\.\.' \
  '^#### Report$' \
  '^## Shared Knowledge MCP$' \
  'knowledge_search' \
  'knowledge_read' \
  'knowledge_write' \
  '^### Search trước, read sau$' \
  'decision cards' \
  '3–8 discriminative concepts' \
  'không trả revision' \
  'expected_revision' \
  '^## Handoff với QiQi$' \
  '^### Closed-world context rule$' \
  '^### Output về QiQi$' \
  '^## Cross-repo Impact$' \
  'Native final assistant response là authoritative semantic handoff'; do
  rg -U -q "$pattern" "$agents" || fail "AGENTS.md: missing required policy: $pattern"
done

rg -U -q 'Work Item MCP và Knowledge MCP.*tool exceptions.*không phải filesystem exceptions' "$agents" || \
  fail 'AGENTS.md: MCP access must not widen filesystem boundary'
rg -q 'Không đọc/sửa repository anh em' "$agents" || \
  fail 'AGENTS.md: sibling repository boundary missing'
rg -U -q 'overall Work Item done|global Work Item complete' "$agents" || \
  fail 'AGENTS.md: child must not own overall task completion'
rg -U -q 'revision conflict.*reread.*reconcile' "$agents" || \
  fail 'AGENTS.md: stale Work Item update policy missing'
rg -U -q 'live owner source/test.*thắng|source/test thắng' "$agents" || \
  fail 'AGENTS.md: live implementation truth precedence missing'
rg -U -q 'required_context.*required premise' "$agents" || \
  fail 'AGENTS.md: TaskPacket required premise rule missing'
rg -U -q 'cross-repo impact: fact, affected boundary/repository, evidence, next action' "$agents" || \
  fail 'AGENTS.md: actionable cross-repo handoff shape missing'
rg -U -q 'Knowledge review.*knowledge_write|Knowledge review/write' "$agents" || \
  fail 'AGENTS.md: Knowledge finalization missing'
rg -U -q 'repos\[current_repo\]\.summary.*current effective repo truth' "$agents" || \
  fail 'AGENTS.md: repo summary must remain current snapshot, not latest-session narrative'
rg -U -q 'checkpoints\[\].*accumulated material phase/milestone history' "$agents" || \
  fail 'AGENTS.md: checkpoints must preserve material phase history'
rg -U -q 'Implementation session.*không tạo artifact' "$agents" || \
  fail 'AGENTS.md: implementation must reconcile even without artifact'

if rg -q 'knowledge_read\(keywords|workspace `knowledge/`|knowledge/INDEX\.md|result_path|fixed result schema' "$agents"; then
  fail 'AGENTS.md: legacy knowledge/result contract found'
fi

setup="$repo_root/docs/REPO_SETUP.md"
for pattern in 'Global Work Item MCP' 'work_item_get' 'work_item_update' 'knowledge_search' 'knowledge_read' 'TaskPacket' 'native final assistant response'; do
  rg -q "$pattern" "$setup" || fail "docs/REPO_SETUP.md: missing guidance: $pattern"
done

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
