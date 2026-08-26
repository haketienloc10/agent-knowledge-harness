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
  fail 'Work Item core/artifact/CLI unit tests failed'
python3 -m py_compile \
  "$project/core.py" \
  "$project/artifacts.py" \
  "$project/server.py" \
  "$project/cli.py" || \
  fail 'Work Item Python syntax check failed'
bash -n "$home/scripts/work-item-mcp-server.sh" || \
  fail 'work-item-mcp-server.sh: invalid Bash syntax'
bash -n "$home/scripts/work-item-cli.sh" || \
  fail 'work-item-cli.sh: invalid Bash syntax'
bash -n "$home/scripts/install-user-mcp.sh" || \
  fail 'install-user-mcp.sh: invalid Bash syntax'

server="$project/server.py"
core="$project/core.py"
artifacts="$project/artifacts.py"
cli="$project/cli.py"
installer="$home/scripts/install-user-mcp.sh"
cli_launcher="$home/scripts/work-item-cli.sh"

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
  'work_item_not_found' \
  'work_item_artifact_list' \
  'work_item_artifact_get' \
  'work_item_artifact_create' \
  'work_item_artifact_append' \
  'work_item_artifact_read' \
  'work_item_artifact_finalize' \
  'artifact_revision_conflict' \
  'artifact_chunk_too_large' \
  'Do not create.*artifact unless the user explicitly requests' \
  'RESERVED_WORK_ITEM_VIEW_FIELDS'; do
  rg -U -q "$pattern" "$server" || fail "server.py: missing contract: $pattern"
done

tool_count="$(rg -c '^@mcp\.tool\(\)$' "$server" || true)"
[[ "$tool_count" == "10" ]] || \
  fail "server.py: expected exactly ten public MCP tools (4 task + 6 artifact), found $tool_count"

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
  'ARTIFACT_TYPES = \{"intake", "investigation", "plan", "review", "report"\}' \
  'ARTIFACT_STATES = \{"draft", "complete"\}' \
  'ARTIFACT_APPEND_MAX_BYTES = 16 \* 1024' \
  'ARTIFACT_READ_MAX_CHUNKS = 2' \
  'ARTIFACT_INDEX_LIMIT = 20' \
  'CREATE TABLE IF NOT EXISTS work_item_artifacts' \
  'CREATE TABLE IF NOT EXISTS work_item_artifact_sections' \
  'CREATE TABLE IF NOT EXISTS work_item_artifact_chunks' \
  'based_on_work_item_revision' \
  'artifact revision conflict' \
  'BEGIN IMMEDIATE' \
  'only draft artifacts accept append' \
  'cannot finalize an artifact with no content chunks' \
  'split the content into smaller append calls' \
  'next_cursor' \
  'limit_chunks'; do
  rg -q "$pattern" "$artifacts" || fail "artifacts.py: missing bounded artifact contract: $pattern"
done

# CRITICAL PAYLOAD/CONCURRENCY INVARIANTS — DO NOT REMOVE OR WEAKEN THESE CHECKS
# merely to make a change pass. Artifact bodies may be very large. Agent-facing MCP
# must stay progressive and bounded, and artifact writes must never consume Work Item
# revision numbers.
if rg -q 'content_json|full_content|body_json' "$artifacts"; then
  fail 'artifacts.py: full artifact body must not be stored as one metadata payload'
fi
if rg -q 'update_work_item|work_items.*SET revision' "$artifacts"; then
  fail 'artifacts.py: artifact mutation must not modify canonical Work Item revision/state'
fi
rg -q 'Field\(min_length=1, max_length=ARTIFACT_APPEND_MAX_BYTES\)' "$server" || \
  fail 'server.py: MCP artifact append schema must advertise a bounded content length'
rg -q 'Field\(ge=1, le=ARTIFACT_READ_MAX_CHUNKS\)' "$server" || \
  fail 'server.py: MCP artifact read schema must enforce bounded chunk windows'
rg -q 'artifact_get returns metadata plus section manifest only' "$server" || \
  fail 'server.py: progressive artifact read instructions missing'

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
  'ARTIFACTS' \
  'SECTION MANIFEST' \
  'work_item_artifact_chunks' \
  'sub.add_parser\(.*artifact' \
  'revision='; do
  rg -U -q "$pattern" "$cli" || fail "cli.py: missing human-view contract: $pattern"
done

# CRITICAL READ-ONLY INVARIANT — DO NOT REMOVE OR WEAKEN THIS CHECK merely to
# make a change pass. The human CLI is an observer of canonical Work Item/artifact
# state, never a second mutation path. Writes belong only to MCP storage functions.
if rg -i -q '\b(insert|update|delete|replace|alter|drop|create|pragma|vacuum|reindex)\b[^\n]*(work_items|work_item_artifact|table|index|journal|synchronous)' "$cli"; then
  fail 'cli.py: human CLI must remain strictly read-only; SQL mutation/schema/PRAGMA path detected'
fi
if rg -q 'from (core|artifacts) import .*\b(update|create|append|finalize)' "$cli"; then
  fail 'cli.py: human CLI must not import Work Item/artifact mutation functions'
fi

rg -q 'command = f"exec bash ' "$installer" || \
  fail 'installer: wrappers must execute source launchers through bash'
rg -q 'write_wrapper\(mcp_wrapper, "/scripts/work-item-mcp-server\.sh", False\)' "$installer" || \
  fail 'installer: MCP wrapper must target work-item-mcp-server.sh'
rg -q 'write_wrapper\(cli_wrapper, "/scripts/work-item-cli\.sh", True\)' "$installer" || \
  fail 'installer: human CLI wrapper must target work-item-cli.sh and forward arguments'
rg -q 'cli_wrapper=.*agent-work-item' "$installer" || \
  fail 'installer: missing agent-work-item human CLI wrapper path'
rg -q 'python .*cli\.py.*"\$@"' "$cli_launcher" || \
  fail 'work-item-cli.sh: must forward all user arguments to cli.py'

if ! PYTHONPATH="$project" uv run --project "$project" python -c \
  'from mcp.server import MCPServer; import pydantic; from artifacts import ARTIFACT_APPEND_MAX_BYTES, ARTIFACT_READ_MAX_CHUNKS; from core import NotFoundError; from server import _not_found_result; assert ARTIFACT_APPEND_MAX_BYTES == 16384 and ARTIFACT_READ_MAX_CHUNKS == 2; r = _not_found_result("redmine:1", NotFoundError("missing")); assert r["found"] is False and r["error"]["code"] == "work_item_not_found"; print("work-item-mcp-runtime: PASS")' \
  >/dev/null; then
  fail 'Work Item MCP runtime/control-flow import failed; run uv sync --project mcp/work_item'
fi

if ((errors > 0)); then
  printf 'work-item-template-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi
printf 'work-item-template-check: PASS\n'
