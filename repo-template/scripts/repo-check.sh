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
  docs/domain/README.md
  docs/specs/README.md
  docs/decisions/README.md
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
  rg -q '`ARCHITECTURE\.md`' "$agents" || fail 'AGENTS.md: must route to ARCHITECTURE.md'
  rg -q '`docs/VERIFY\.md`' "$agents" || fail 'AGENTS.md: must route to docs/VERIFY.md'
  rg -q 'Git root hiện tại' "$agents" || fail 'AGENTS.md: missing Git-root boundary'
  rg -q 'Không sửa repository anh em' "$agents" || fail 'AGENTS.md: missing sibling-repository boundary'
  rg -q 'exact result artifact' "$agents" || fail 'AGENTS.md: missing exact result-artifact exception'
  rg -q '`\.qiqi/runs/`' "$agents" || fail 'AGENTS.md: missing workspace result-artifact path'
  rg -q 'không tự suy đoán hoặc tìm artifact khác' "$agents" || \
    fail 'AGENTS.md: result artifact must come only from MCP handoff'
  rg -q '^## Tri thức Repo-local$' "$agents" || fail 'AGENTS.md: missing repo-local knowledge rules'
  rg -q '^## Ứng viên Tri thức Cross-repo$' "$agents" || fail 'AGENTS.md: missing cross-repo rules'
  rg -q '^## Final Result Contract$' "$agents" || fail 'AGENTS.md: missing final result contract'

  for heading in \
    '### Outcome' \
    '### Changes' \
    '### Verification' \
    '### Git State' \
    '### Blockers' \
    '### Repo-local Knowledge' \
    '### Cross-repo Impact'; do
    rg -q --fixed-strings "$heading" "$agents" || \
      fail "AGENTS.md: final result missing heading $heading"
  done

  rg -q 'completed.*blocked|blocked.*completed' "$agents" || \
    fail 'AGENTS.md: Outcome must define completed/blocked values'
  rg -q 'newest pending Result section' "$agents" || \
    fail 'AGENTS.md: missing newest Result-section finalization rule'
  rg -q 'Giữ nguyên toàn bộ history' "$agents" || \
    fail 'AGENTS.md: missing result-history preservation rule'
  rg -q 'chain-of-thought|working transcript' "$agents" || \
    fail 'AGENTS.md: missing no-reasoning/transcript result rule'
  rg -q 'Outcome `blocked`' "$agents" || \
    fail 'AGENTS.md: missing blocked-before-question handoff rule'

  if rg -q 'Caller có thể ép output bằng JSON Schema|final result missing field|`git_state`|`repo_local_knowledge`' "$agents"; then
    fail 'AGENTS.md: legacy logical JSON result contract found'
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
