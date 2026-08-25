#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/work_item"
errors=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  errors=$((errors + 1))
}

for command in python3 uv rg; do
  command -v "$command" >/dev/null 2>&1 || fail "missing command: $command"
done

PYTHONPATH="$project" python3 -m unittest discover -s "$project/tests" -v || \
  fail 'Work Item core unit tests failed'
python3 -m py_compile "$project/core.py" "$project/server.py" || \
  fail 'Work Item Python syntax check failed'
bash -n "$home/scripts/work-item-mcp-server.sh" || \
  fail 'work-item-mcp-server.sh: invalid Bash syntax'
bash -n "$home/scripts/install-user-mcp.sh" || \
  fail 'install-user-mcp.sh: invalid Bash syntax'

server="$project/server.py"
core="$project/core.py"

for pattern in \
  'MCPServer' \
  'WORK_ITEM_DB_PATH' \
  'work_item_get' \
  'work_item_list' \
  'work_item_create' \
  'work_item_update' \
  'expected_revision'; do
  rg -q "$pattern" "$server" || fail "server.py: missing contract: $pattern"
done

tool_count="$(rg -c '^@mcp\.tool\(\)$' "$server" || true)"
[[ "$tool_count" == "4" ]] || \
  fail "server.py: expected exactly four public MCP tools, found $tool_count"

for pattern in \
  'CREATE TABLE IF NOT EXISTS work_items' \
  'PRAGMA journal_mode=WAL' \
  'BEGIN IMMEDIATE' \
  'revision conflict' \
  'current_requirements' \
  'questions' \
  'decisions' \
  'changes' \
  'handoffs' \
  'next_actions' \
  'checkpoints'; do
  rg -q "$pattern" "$core" || fail "core.py: missing contract: $pattern"
done

rg -q 'exec bash .*work-item-mcp-server\.sh' "$home/scripts/install-user-mcp.sh" || \
  fail 'installer: generated wrapper must not depend on source script executable bit'

if ! uv run --project "$project" python -c \
  'from mcp.server import MCPServer; import pydantic; print("work-item-mcp-runtime: PASS")' \
  >/dev/null; then
  fail 'Work Item MCP runtime import failed; run uv sync --project mcp/work_item'
fi

if ((errors > 0)); then
  printf 'work-item-template-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi
printf 'work-item-template-check: PASS\n'
