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
    'exact result artifact' \
    'Không tự suy đoán, tìm hoặc mở result artifact khác' \
    '^## Handoff với QiQi$' \
    '^## Shared Knowledge MCP$' \
    '^## Cross-repo Impact$' \
    'knowledge_read' \
    'knowledge_write' \
    'entries=\[\]' \
    'expected_revision' \
    'legacy heading name' \
    'MCP footer là source of truth duy nhất'; do
    rg -q "$pattern" "$agents" || fail "AGENTS.md: missing required policy: $pattern"
  done

  rg -U -q 'Knowledge MCP là tool exception.*không phải filesystem exception' "$agents" || \
    fail 'AGENTS.md: shared knowledge must not become an external filesystem exception'
  rg -q 'không tự mở result/source của repository khác' "$agents" || \
    fail 'AGENTS.md: child must not read sibling repository results or source'
  rg -q 'QiQi là handoff broker' "$agents" || \
    fail 'AGENTS.md: QiQi must broker live cross-repo handoff'
  rg -U -q 'context\.repo.*context\.domain.*ranking hint|context\.repo.*ranking hint' "$agents" || \
    fail 'AGENTS.md: repo/domain context must be ranking-only for shared knowledge'
  rg -U -q 'live source/test.*thắng|source/test.*thắng' "$agents" || \
    fail 'AGENTS.md: live owner source/test must override stale shared knowledge'
  rg -U -q 'không truyền filename, path,[[:space:]]+directory' "$agents" || \
    fail 'AGENTS.md: agent must not own knowledge filesystem layout'
  rg -q 'Không tạo field `language`' "$agents" || \
    fail 'AGENTS.md: language field must not be part of shared knowledge schema'
  rg -q 'repository/boundary nào bị ảnh hưởng' "$agents" || \
    fail 'AGENTS.md: Cross-repo Impact must identify affected boundary'
  rg -q 'evidence chính từ repository hiện tại' "$agents" || \
    fail 'AGENTS.md: Cross-repo Impact must carry evidence'
  rg -q 'next action nếu đã rõ' "$agents" || \
    fail 'AGENTS.md: Cross-repo Impact must carry next action when known'
  rg -U -q 'knowledge review.*gọi `knowledge_write`' "$agents" || \
    fail 'AGENTS.md: Definition of Done must include knowledge review/write'

  if rg -q '^## Final Result Contract$' "$agents"; then
    fail 'AGENTS.md: must not duplicate MCP-owned final result protocol'
  fi
  if rg -q 'Newest Result section bắt buộc|Giữ nguyên toàn bộ history|newest pending Result section' "$agents"; then
    fail 'AGENTS.md: MCP-owned marker/history/finalization mechanics are duplicated'
  fi
  if rg -q 'Caller có thể ép output bằng JSON Schema|final result missing field|`git_state`|`repo_local_knowledge`' "$agents"; then
    fail 'AGENTS.md: legacy logical JSON result contract found'
  fi
  if rg -q 'workspace `knowledge/`|knowledge/INDEX\.md' "$agents"; then
    fail 'AGENTS.md: legacy workspace-local knowledge store reference found'
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
