#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
errors=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  errors=$((errors + 1))
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

require_file() {
  local relative="$1"
  [[ -f "$repo_root/$relative" ]] || fail "missing file: $relative"
}

require_command git
require_command rg

required_files=(
  AGENTS.md
  CLAUDE.md
  ARCHITECTURE.md
  docs/VERIFY.md
  docs/REPO_SETUP.md
  docs/friction/README.md
  scripts/repo-check.sh
)
for path in "${required_files[@]}"; do
  require_file "$path"
done

if git_root="$(git -C "$repo_root" rev-parse --show-toplevel 2>/dev/null)"; then
  if [[ "$(cd "$git_root" && pwd)" != "$repo_root" ]]; then
    fail "template must be installed at Git root: expected $git_root"
  fi
else
  fail "target is not a Git repository: $repo_root"
fi

managed_files=(
  "$repo_root/AGENTS.md"
  "$repo_root/ARCHITECTURE.md"
  "$repo_root/docs/VERIFY.md"
)
existing_managed_files=()
for path in "${managed_files[@]}"; do
  [[ -f "$path" ]] && existing_managed_files+=("$path")
done
if ((${#existing_managed_files[@]} > 0)) && \
  rg -n '\{\{[^}]+\}\}' "${existing_managed_files[@]}"; then
  fail 'unresolved placeholder(s) found in required artifact'
fi

claude_md="$repo_root/CLAUDE.md"
if [[ -f "$claude_md" ]]; then
  rg -qx '@AGENTS\.md' "$claude_md" || \
    fail 'CLAUDE.md: expected forwarding instruction @AGENTS.md'
fi

# A repository must not grow a local copy of global product-task state.
if [[ -e "$repo_root/.qiqi/tasks" || -e "$repo_root/work-items.sqlite3" ]]; then
  fail 'repo-local task store found; product-task truth must remain in Global Work Item MCP'
fi

agents="$repo_root/AGENTS.md"
if [[ -f "$agents" ]]; then
  for pattern in \
    '`ARCHITECTURE\.md`' \
    '`docs/VERIFY\.md`' \
    'Git root hiện tại' \
    'Global Work Item MCP' \
    'work_item_get' \
    'work_item_update' \
    'canonical Work Item' \
    'current Git root' \
    'revision conflict' \
    'questions' \
    'decisions' \
    'handoff' \
    '^## Handoff với QiQi$' \
    '^### Closed-world context rule$' \
    '^### Output về QiQi$' \
    '^## Shared Knowledge MCP$' \
    '^## Cross-repo Impact$' \
    'TaskPacket' \
    'required_context' \
    'Native final assistant response là authoritative semantic handoff' \
    'knowledge_read' \
    'knowledge_write' \
    'entries=\[\]' \
    'expected_revision'; do
    rg -q "$pattern" "$agents" || fail "AGENTS.md: missing required policy: $pattern"
  done

  rg -U -q 'Work Item MCP và Knowledge MCP.*tool exceptions.*không phải filesystem' "$agents" || \
    fail 'AGENTS.md: MCP access must not become an external filesystem exception'
  rg -U -q 'không chia sẻ hidden conversation.*sibling source/runtime state' "$agents" || \
    fail 'AGENTS.md: child must keep hidden QiQi/sibling state outside its context'
  rg -U -q 'current Git root.*không.*sibling|không sửa repository khác' "$agents" || \
    fail 'AGENTS.md: child execution authority must remain current-repo only'
  rg -U -q 'mark.*overall Work Item.*done|không.*overall Work Item.*done' "$agents" || \
    fail 'AGENTS.md: child must not own overall Work Item completion'
  rg -U -q 'revision conflict.*reread|Revision conflict.*reread' "$agents" || \
    fail 'AGENTS.md: stale Work Item updates must reread/reconcile'
  rg -U -q '(live owner source/test|source/test).*thắng' "$agents" || \
    fail 'AGENTS.md: live owner source/test must override stale shared knowledge'
  rg -U -q 'Task-specific status|task status' "$agents" || \
    fail 'AGENTS.md: task state must be distinguished from reusable knowledge'
  rg -U -q 'Work Item handoff|handoff.*Work Item' "$agents" || \
    fail 'AGENTS.md: cross-repo remaining work must use canonical Work Item handoff when available'

  for forbidden in \
    '^## Final Result Contract$' \
    'MCP footer là source of truth duy nhất' \
    'Newest Result section bắt buộc' \
    'newest pending Result section' \
    'Caller có thể ép output bằng JSON Schema' \
    'final result missing field' \
    '`git_state`' \
    '`repo_local_knowledge`' \
    '### Outcome' \
    '### Git State' \
    '### Repo-local Knowledge'; do
    if rg -q "$forbidden" "$agents"; then
      fail "AGENTS.md: legacy fixed-result contract found: $forbidden"
    fi
  done

  if rg -q 'workspace `knowledge/`|knowledge/INDEX\.md|repo-local task store' "$agents"; then
    fail 'AGENTS.md: local duplicate truth-store reference found'
  fi
fi

setup="$repo_root/docs/REPO_SETUP.md"
if [[ -f "$setup" ]]; then
  for pattern in \
    'Global Work Item MCP' \
    'work_item_get' \
    'work_item_update' \
    'TaskPacket' \
    'native final assistant response' \
    'Knowledge MCP'; do
    rg -q "$pattern" "$setup" || fail "docs/REPO_SETUP.md: missing guidance: $pattern"
  done
  if rg -q 'fixed headings|result_path|repo-local task store' "$setup"; then
    fail 'docs/REPO_SETUP.md: legacy/duplicate task-result contract found'
  fi
fi

architecture="$repo_root/ARCHITECTURE.md"
if [[ -f "$architecture" ]]; then
  rg -q '^## Repository responsibility$' "$architecture" || fail 'ARCHITECTURE.md: missing repository responsibility'
  rg -q '^## Module map$' "$architecture" || fail 'ARCHITECTURE.md: missing module map'
  rg -q '^## External boundaries$' "$architecture" || fail 'ARCHITECTURE.md: missing external boundaries'
  rg -q '^## Constraints$' "$architecture" || fail 'ARCHITECTURE.md: missing constraints'
fi

verify="$repo_root/docs/VERIFY.md"
if [[ -f "$verify" ]]; then
  rg -q '^## Bootstrap$' "$verify" || fail 'docs/VERIFY.md: missing bootstrap command'
  rg -q '^## Kiểm tra nhanh$' "$verify" || fail 'docs/VERIFY.md: missing focused check'
  rg -q '^## Test liên quan$' "$verify" || fail 'docs/VERIFY.md: missing related test command'
  rg -q '^## Build hoặc kiểm tra đầy đủ$' "$verify" || fail 'docs/VERIFY.md: missing full verification command'
  rg -q '^## Side effects$' "$verify" || fail 'docs/VERIFY.md: missing side-effect documentation'
fi

bash -n "$repo_root/scripts/repo-check.sh" || fail 'scripts/repo-check.sh: invalid Bash syntax'

if ((errors > 0)); then
  printf 'repo-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi
printf 'repo-check: PASS\n'
