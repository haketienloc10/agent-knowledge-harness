#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
agents="$repo_root/AGENTS.md"
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "$agents" ]] || fail 'missing AGENTS.md'
for pattern in \
  'mounted Work Item' \
  'work_item=<id>; revision=<n>' \
  'TaskPacket vẫn phải semantically sufficient' \
  'Child MAY read mounted Work Item' \
  'trực tiếp rewrite canonical Work Item' \
  'Không tạo execution diary'; do
  rg -q "$pattern" "$agents" || fail "AGENTS.md missing policy: $pattern"
done

if rg -q 'Global Work Item MCP|work_item_get|work_item_update|Child không cần Work Item|MUST NOT.*Work Item.*reconstruct' "$agents"; then
  fail 'legacy child Work Item isolation contract remains'
fi

bash -n "$repo_root/scripts/repo-check.sh"
printf 'Repository execution policy: OK\n'
