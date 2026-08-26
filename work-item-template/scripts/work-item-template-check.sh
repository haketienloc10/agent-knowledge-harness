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
  fail 'Work Item core/CLI unit tests failed'
python3 -m py_compile "$project/core.py" "$project/server.py" "$project/cli.py" || \
  fail 'Work Item Python syntax check failed'
bash -n "$home/scripts/work-item-mcp-server.sh" || \
  fail 'work-item-mcp-server.sh: invalid Bash syntax'
bash -n "$home/scripts/work-item-cli.sh" || \
  fail 'work-item-cli.sh: invalid Bash syntax'
bash -n "$home/scripts/install-user-mcp.sh" || \
  fail 'install-user-mcp.sh: invalid Bash syntax'

server="$project/server.py"
core="$project/core.py"
cli="$project/cli.py"
installer="$home/scripts/install-user-mcp.sh"

for pattern in \
  'MCPServer' \
  'WORK_ITEM_DB_PATH' \
  'work_item_get' \
  'work_item_list' \
  'work_item_create' \
  'work_item_update' \
  'expected_revision' \
  'except NotFoundError as exc' \
  '"found": False' \
  'work_item_not_found'; do
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

for pattern in \
  'prog="agent-work-item"' \
  'mode=ro' \
  'SELECT status, COUNT\(\*\)' \
  'SELECT \* FROM work_items' \
  'CURRENT REQUIREMENTS' \
  'REPOSITORIES' \
  'QUESTIONS' \
  'DECISIONS' \
  'CHANGES' \
  'BLOCKERS' \
  'HANDOFFS' \
  'NEXT ACTIONS' \
  'CHECKPOINTS' \
  'revision='; do
  rg -q "$pattern" "$cli" || fail "cli.py: missing human-view contract: $pattern"
done

# CRITICAL READ-ONLY INVARIANT — DO NOT REMOVE OR WEAKEN THIS CHECK merely to
# make a change pass. The human CLI is an observer of canonical Work Item state,
# never a second mutation path. Writes belong only to the MCP/core workflow.
if rg -i -q '\b(insert|update|delete|replace|alter|drop|create|pragma|vacuum|reindex)\b[^\n]*(work_items|table|index|journal|synchronous)' "$cli"; then
  fail 'cli.py: human CLI must remain strictly read-only; SQL mutation/schema/PRAGMA path detected'
fi
if rg -q 'from core import .*update_work_item|create_work_item\(' "$cli"; then
  fail 'cli.py: human CLI must not import/call Work Item mutation functions'
fi

rg -q 'exec bash .*work-item-mcp-server\.sh' "$installer" || \
  fail 'installer: generated MCP wrapper must not depend on source script executable bit'
rg -q 'agent-work-item' "$installer" || \
  fail 'installer: missing human CLI wrapper installation'
rg -q 'work-item-cli\.sh' "$installer" || \
  fail 'installer: human CLI wrapper must launch work-item-cli.sh'
rg -q 'exec bash .*work-item-cli\.sh' "$installer" || \
  fail 'installer: generated human CLI wrapper must not depend on source script executable bit'

if ! PYTHONPATH="$project" uv run --project "$project" python -c \
  'from mcp.server import MCPServer; import pydantic; from core import NotFoundError; from server import _not_found_result; r = _not_found_result("redmine:1", NotFoundError("missing")); assert r["found"] is False and r["error"]["code"] == "work_item_not_found"; print("work-item-mcp-runtime: PASS")' \
  >/dev/null; then
  fail 'Work Item MCP runtime/control-flow import failed; run uv sync --project mcp/work_item'
fi

if ((errors > 0)); then
  printf 'work-item-template-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi
printf 'work-item-template-check: PASS\n'
