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

agents="$repo_root/AGENTS.md"
if [[ -f "$agents" ]]; then
  for pattern in \
    '`ARCHITECTURE\.md`' \
    '`docs/VERIFY\.md`' \
    'Git root hiện tại' \
    'Không đọc/sửa repository anh em' \
    '^## Handoff với QiQi$' \
    '^### Closed-world context rule$' \
    '^### Output về QiQi$' \
    '^## Shared Knowledge MCP$' \
    '^## Cross-repo Impact$' \
    'TaskPacket' \
    'required_context' \
    'Native final assistant response là authoritative semantic handoff' \
    'không tạo hoặc cập nhật QiQi result' \
    'Không có result schema hoặc fixed headings' \
    'knowledge_read' \
    'knowledge_write' \
    'entries=\[\]' \
    'expected_revision'; do
    rg -q "$pattern" "$agents" || fail "AGENTS.md: missing required policy: $pattern"
  done

  rg -U -q 'Knowledge MCP là tool exception.*không phải filesystem exception' "$agents" || \
    fail 'AGENTS.md: shared knowledge must not become an external filesystem exception'
  rg -U -q 'không chia sẻ hidden conversation.*sibling-repository state' "$agents" || \
    fail 'AGENTS.md: child must treat QiQi live context as closed-world input'
  rg -U -q 'required_context.*required premise' "$agents" || \
    fail 'AGENTS.md: QiQi-used task premises must be explicit required_context'
  rg -q 'Không tự đọc/sửa repository anh em' "$agents" || \
    fail 'AGENTS.md: child must not modify sibling repositories'
  rg -U -q 'Không tự mở source,[[:space:]]+result history hoặc runtime state của repository khác' "$agents" || \
    fail 'AGENTS.md: child must not read sibling live result/source/runtime state'
  rg -q 'QiQi là handoff broker' "$agents" || \
    fail 'AGENTS.md: QiQi must broker live cross-repo handoff'
  rg -U -q 'context\.repo.*context\.domain.*ranking hint|context\.repo.*ranking hint' "$agents" || \
    fail 'AGENTS.md: repo/domain context must be ranking-only for shared knowledge'
  rg -U -q '(?s)(live source/test|source/test).*?thắng' "$agents" || \
    fail 'AGENTS.md: live owner source/test must override stale shared knowledge'
  rg -U -q 'không truyền filename, path,[[:space:]]+directory' "$agents" || \
    fail 'AGENTS.md: agent must not own knowledge filesystem layout'
  rg -q 'Không tạo field `language`' "$agents" || \
    fail 'AGENTS.md: language field must not be part of shared knowledge schema'
  rg -U -q 'cross-repo impact: fact, affected boundary/repository, evidence và next action' "$agents" || \
    fail 'AGENTS.md: native handoff must preserve actionable cross-repo impact'
  rg -U -q 'knowledge review.*gọi `knowledge_write`' "$agents" || \
    fail 'AGENTS.md: Definition of Done must include knowledge review/write'

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
    '### Changes' \
    '### Git State' \
    '### Blockers' \
    '### Repo-local Knowledge' \
    '### Cross-repo Impact'; do
    if rg -q "$forbidden" "$agents"; then
      fail "AGENTS.md: legacy fixed-result contract found: $forbidden"
    fi
  done

  if rg -q 'workspace `knowledge/`|knowledge/INDEX\.md' "$agents"; then
    fail 'AGENTS.md: legacy workspace-local knowledge store reference found'
  fi
fi

setup="$repo_root/docs/REPO_SETUP.md"
if [[ -f "$setup" ]]; then
  rg -q 'TaskPacket' "$setup" || fail 'docs/REPO_SETUP.md: missing TaskPacket handoff guidance'
  rg -q 'native final assistant response' "$setup" || \
    fail 'docs/REPO_SETUP.md: missing native final-response guidance'
  if rg -q '### Repo-local Knowledge|### Cross-repo Impact|fixed headings|result_path' "$setup"; then
    fail 'docs/REPO_SETUP.md: legacy fixed-result contract found'
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

if ((errors > 0)); then
  printf 'repo-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi

printf 'repo-check: PASS\n'
