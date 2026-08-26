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

for file in "$home/CLI.md" "$home/ARTIFACTS.md"; do
  [[ -f "$file" ]] || fail "missing documentation: ${file#$home/}"
done

PYTHONPATH="$project" python3 -m unittest discover -s "$project/tests" -v || \
  fail 'Work Item core/CLI/artifact unit tests failed'
python3 -m py_compile "$project/core.py" "$project/server.py" "$project/artifacts.py" "$project/cli.py" || \
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
  'ArtifactContent' \
  'ArtifactReadLimit' \
  'ARTIFACT_LIST_MAX' \
  'ARTIFACT_READ_MIN_BYTES' \
  'artifacts is derived metadata' \
  'Do not create artifacts merely as normal progress bookkeeping' \
  'Artifact mutations never advance the Work Item revision'; do
  rg -q "$pattern" "$server" || fail "server.py: missing contract: $pattern"
done

tool_count="$(rg -c '^@mcp\.tool\(\)$' "$server" || true)"
[[ "$tool_count" == "10" ]] || \
  fail "server.py: expected exactly ten public MCP tools (4 Work Item + 6 artifact), found $tool_count"

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
  'ARTIFACT_TYPES = .*intake.*investigation.*plan.*review.*report' \
  'ARTIFACT_CHUNK_MAX_BYTES = 32_000' \
  'ARTIFACT_READ_MIN_BYTES = 4' \
  'ARTIFACT_READ_MAX_BYTES = 32_000' \
  'ARTIFACT_PER_WORK_ITEM_MAX = 50' \
  'ARTIFACT_SECTION_MAX = 100' \
  '_connect as _connect_work_items' \
  'CREATE TABLE IF NOT EXISTS work_item_artifacts' \
  'CREATE TABLE IF NOT EXISTS work_item_artifact_sections' \
  'CREATE TABLE IF NOT EXISTS work_item_artifact_chunks' \
  'based_on_work_item_revision' \
  'artifact revision conflict' \
  'artifact is complete and immutable' \
  'split it into smaller chunks' \
  'cursor is invalid' \
  'cannot finalize an artifact without content' \
  'ON DELETE CASCADE'; do
  rg -q "$pattern" "$artifacts" || fail "artifacts.py: missing bounded artifact contract: $pattern"
done

# CRITICAL PAYLOAD/REVISION INVARIANTS — DO NOT REMOVE OR WEAKEN THESE CHECKS
# merely to make a change pass. Artifact bodies must never become an unbounded
# MCP request/response, and artifact writes must remain independently revisioned
# from canonical Work Item state.
rg -q 'len\(encoded\) > ARTIFACT_CHUNK_MAX_BYTES' "$artifacts" || \
  fail 'artifacts.py: append must enforce UTF-8 byte limit server-side'
rg -q 'limit_bytes.*ARTIFACT_READ_MAX_BYTES' "$artifacts" || \
  fail 'artifacts.py: read must enforce bounded response size server-side'
rg -q 'return value' "$artifacts" || \
  fail 'artifacts.py: chunk content must be preserved rather than stripped/reformatted'
rg -q 'SET revision = \?, updated_at = \?' "$artifacts" || \
  fail 'artifacts.py: artifact append/finalize must advance artifact revision'
if rg -q 'UPDATE work_items|SET revision = .*work_items' "$artifacts"; then
  fail 'artifacts.py: artifact mutations must never update Work Item revision/state'
fi

for pattern in \
  'prog="agent-work-item"' \
  'mode=ro' \
  'SELECT status, COUNT\(\*\)' \
  'SELECT \* FROM work_items' \
  'CURRENT REQUIREMENTS' \
  'REPOSITORIES' \
  'ARTIFACTS' \
  'artifact_parser' \
  '_list_artifacts_readonly' \
  '_get_artifact_readonly' \
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
if rg -i -q '\b(insert|update|delete|replace|alter|drop|create|pragma|vacuum|reindex)\b[^\n]*(work_items|work_item_artifact|table|index|journal|synchronous)' "$cli"; then
  fail 'cli.py: human CLI must remain strictly read-only; SQL mutation/schema/PRAGMA path detected'
fi
if rg -q 'from (core|artifacts) import .*update_|from (core|artifacts) import .*create_|create_work_item\(|append_artifact\(|finalize_artifact\(' "$cli"; then
  fail 'cli.py: human CLI must not import/call Work Item or artifact mutation functions'
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
  'from mcp.server import MCPServer; import pydantic; from core import NotFoundError; from server import _not_found_result; r = _not_found_result("redmine:1", NotFoundError("missing")); assert r["found"] is False and r["error"]["code"] == "work_item_not_found"; print("work-item-mcp-runtime: PASS")' \
  >/dev/null; then
  fail 'Work Item MCP runtime/control-flow import failed; run uv sync --project mcp/work_item'
fi

if ((errors > 0)); then
  printf 'work-item-template-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi
printf 'work-item-template-check: PASS\n'
