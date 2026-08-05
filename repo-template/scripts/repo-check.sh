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
  ARCHITECTURE.md
  docs/VERIFY.md
  docs/REPO_SETUP.md
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

agents="$repo_root/AGENTS.md"
if [[ -f "$agents" ]]; then
  rg -q '`ARCHITECTURE\.md`' "$agents" || \
    fail 'AGENTS.md: must route agent to ARCHITECTURE.md'
  rg -q '`docs/VERIFY\.md`' "$agents" || \
    fail 'AGENTS.md: must route agent to docs/VERIFY.md'
  rg -q 'Git root hiện tại' "$agents" || \
    fail 'AGENTS.md: missing current Git-root boundary'
  rg -q 'Không sửa repository anh em' "$agents" || \
    fail 'AGENTS.md: missing sibling-repository boundary'
  rg -q '^## Tri thức Repo-local$' "$agents" || \
    fail 'AGENTS.md: missing repo-local knowledge rules'
  rg -q '^## Ứng viên Tri thức Cross-repo$' "$agents" || \
    fail 'AGENTS.md: missing cross-repo candidate rules'
  rg -q '^## Repo-local knowledge$' "$agents" || \
    fail 'AGENTS.md: final-report template must include repo-local knowledge'
  rg -q '^## Cross-repo knowledge candidate$' "$agents" || \
    fail 'AGENTS.md: final-report template must include cross-repo candidate'
fi

architecture="$repo_root/ARCHITECTURE.md"
if [[ -f "$architecture" ]]; then
  rg -q '^## Repository responsibility$' "$architecture" || \
    fail 'ARCHITECTURE.md: missing repository responsibility'
  rg -q '^## Module map$' "$architecture" || \
    fail 'ARCHITECTURE.md: missing module map'
  rg -q '^## External boundaries$' "$architecture" || \
    fail 'ARCHITECTURE.md: missing external boundaries'
  rg -q '^## Constraints$' "$architecture" || \
    fail 'ARCHITECTURE.md: missing constraints'
fi

verify="$repo_root/docs/VERIFY.md"
if [[ -f "$verify" ]]; then
  rg -q '^## Bootstrap$' "$verify" || \
    fail 'docs/VERIFY.md: missing bootstrap command'
  rg -q '^## Kiểm tra nhanh$' "$verify" || \
    fail 'docs/VERIFY.md: missing focused check'
  rg -q '^## Test liên quan$' "$verify" || \
    fail 'docs/VERIFY.md: missing related test command'
  rg -q '^## Build hoặc kiểm tra đầy đủ$' "$verify" || \
    fail 'docs/VERIFY.md: missing full verification command'
  rg -q '^## Side effects$' "$verify" || \
    fail 'docs/VERIFY.md: missing side-effect documentation'
fi

if ((errors > 0)); then
  printf 'repo-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi

printf 'repo-check: PASS\n'
