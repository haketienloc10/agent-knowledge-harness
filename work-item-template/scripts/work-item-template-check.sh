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

for file in "$home/CLI.md" "$home/ARTIFACTS.md" "$home/config/artifact-templates.json"; do
  [[ -f "$file" ]] || fail "missing required Work Item file: ${file#$home/}"
done

PYTHONPATH="$project" python3 -m unittest discover -s "$project/tests" -v || \
  fail 'Work Item core/CLI/artifact/template unit tests failed'
PYTHONPATH="$project" uv run --project "$project" python -m unittest discover -s "$project/mcp_tests" -v || \
  fail 'Work Item typed MCP/template contract tests failed'
python3 -m py_compile \
  "$project/core.py" \
  "$project/mutations.py" \
  "$project/server.py" \
  "$project/artifacts.py" \
  "$project/artifact_templates.py" \
  "$project/cli.py" \
  "$project/models.py" || \
  fail 'Work Item Python syntax check failed'
bash -n "$home/scripts/work-item-mcp-server.sh" || \
  fail 'work-item-mcp-server.sh: invalid Bash syntax'
bash -n "$home/scripts/work-item-cli.sh" || \
  fail 'work-item-cli.sh: invalid Bash syntax'
bash -n "$home/scripts/install-user-mcp.sh" || \
  fail 'install-user-mcp.sh: invalid Bash syntax'

server="$project/server.py"
core="$project/core.py"
mutations="$project/mutations.py"
artifacts="$project/artifacts.py"
artifact_templates="$project/artifact_templates.py"
artifact_template_config="$home/config/artifact-templates.json"
models="$project/models.py"
cli="$project/cli.py"
installer="$home/scripts/install-user-mcp.sh"
cli_launcher="$home/scripts/work-item-cli.sh"

for pattern in \
  'MCPServer' \
  'WORK_ITEM_DB_PATH' \
  'work_item_get' \
  'work_item_history_read' \
  'work_item_list' \
  'work_item_create' \
  'work_item_update' \
  'WorkItemSnapshot' \
  'WorkItemHistoryPage' \
  'HistoryCollection' \
  'HistoryReadLimit' \
  'history_revision_conflict' \
  'WorkItemMutation' \
  'mutate_work_item' \
  '_work_item_update_error_result' \
  '"updated": False' \
  'work_item_validation' \
  'expected_revision' \
  'except NotFoundError as exc' \
  '"found": False' \
  'work_item_not_found' \
  'question_upsert' \
  'decision_upsert' \
  'change_upsert' \
  'blocker_upsert' \
  'handoff_upsert' \
  'checkpoint_append' \
  'compact receipt' \
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
  'Do not create artifacts merely as normal progress' \
  'Artifact read cursors are bound to one artifact revision' \
  'Artifact mutations never advance' \
  'load_artifact_templates' \
  'ARTIFACT_TEMPLATES = load_artifact_templates()' \
  '_with_template_guidance' \
  'template_guidance' \
  'not persisted' \
  'does not enforce'; do
  rg -F -q "$pattern" "$server" || fail "server.py: missing contract: $pattern"
done

tool_count="$(rg -c '^@mcp\.tool\(\)$' "$server" || true)"
[[ "$tool_count" == "11" ]] || \
  fail "server.py: expected exactly eleven public MCP tools (5 Work Item + 6 artifact), found $tool_count"

# CRITICAL TYPED INCREMENTAL UPDATE INVARIANT — DO NOT REMOVE OR WEAKEN THIS CHECK.
# Historical semantic collections must not return to public full-array replacement. The
# MCP exposes one typed mutation envelope so state + semantic commands commit atomically.
if ! SERVER_PATH="$server" python3 - <<'PY'
import ast
import os
from pathlib import Path

path = Path(os.environ["SERVER_PATH"])
text = path.read_text(encoding="utf-8")
tree = ast.parse(text)
funcs = {
    node.name: node
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
update = funcs["work_item_update"]
mutation_arg = next(arg for arg in update.args.args if arg.arg == "mutation")
source = ast.get_source_segment(text, update) or ""
assert isinstance(mutation_arg.annotation, ast.Name)
assert mutation_arg.annotation.id == "WorkItemMutation"
assert "mutation.to_core_mutation()" in source
assert "mutate_work_item(" in source
assert "update_work_item(" not in source
assert "_work_item_update_error_result" in source
assert "except (ValidationError, ConflictError, NotFoundError)" in source
PY
then
  fail 'server.py: work_item_update must expose WorkItemMutation and route only through incremental mutation engine'
fi

# CRITICAL BOUNDED READ INVARIANT — public GET must never regress to raw full-document
# hydration. History is a separate one-collection typed tool with revision-bound cursor semantics.
if ! SERVER_PATH="$server" python3 - <<'PY'
import ast
import os
from pathlib import Path

path = Path(os.environ["SERVER_PATH"])
text = path.read_text(encoding="utf-8")
tree = ast.parse(text)
funcs = {
    node.name: node
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
get_fn = funcs["work_item_get"]
history_fn = funcs["work_item_history_read"]
get_source = ast.get_source_segment(text, get_fn) or ""
history_source = ast.get_source_segment(text, history_fn) or ""
assert "get_work_item_snapshot(" in get_source
assert "WorkItemSnapshot.model_validate" in get_source
assert "get_work_item(_db_path()" not in get_source
args = {
    arg.arg: ast.unparse(arg.annotation)
    for arg in history_fn.args.args
    if arg.annotation is not None
}
assert args["collection"] == "HistoryCollection"
assert args["status"] == "HistoryStatus | None"
assert "read_work_item_history(" in history_source
assert "WorkItemHistoryPage.model_validate" in history_source
PY
then
  fail 'server.py: bounded snapshot/scoped-history read contract regressed'
fi

# CRITICAL ARTIFACT TEMPLATE BOUNDARY — guidance is startup advisory data only.
# It may enrich artifact-create response from memory, but storage/list/get/read/finalize
# must remain independent of template config and must not enforce template sections.
if ! SERVER_PATH="$server" python3 - <<'PY'
import ast
import os
from pathlib import Path

path = Path(os.environ["SERVER_PATH"])
text = path.read_text(encoding="utf-8")
tree = ast.parse(text)
funcs = {
    node.name: ast.get_source_segment(text, node) or ""
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
create = funcs["work_item_artifact_create"]
helper = funcs["_with_template_guidance"]
assert "create_artifact(" in create
assert "_with_template_guidance" in create
assert "template_guidance_for" in helper
assert "list_artifacts(" not in create
assert "get_artifact(" not in create
PY
then
  fail 'server.py: artifact create must attach advisory in-memory guidance without a post-commit DB enrichment query'
fi

# CRITICAL MUTATION RESPONSE INVARIANT — DO NOT REMOVE OR WEAKEN THIS CHECK.
# A committed Work Item update returns the bounded receipt produced by the mutation
# transaction and never depends on a second artifact/snapshot query.
if ! SERVER_PATH="$server" python3 - <<'PY'
import ast
import os
from pathlib import Path

path = Path(os.environ["SERVER_PATH"])
text = path.read_text(encoding="utf-8")
tree = ast.parse(text)
funcs = {
    node.name: ast.get_source_segment(text, node) or ""
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
assert "_with_artifacts" in funcs["work_item_get"]
assert "_with_artifacts" not in funcs["work_item_create"]
assert "_with_artifacts" not in funcs["work_item_update"]
assert "get_work_item_snapshot" not in funcs["work_item_update"]
assert "read_work_item_history" not in funcs["work_item_update"]
PY
then
  fail 'server.py: update must return its compact committed receipt without post-commit enrichment/history hydration'
fi

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
  'checkpoints' \
  'DERIVED_FIELDS = \{"artifacts"\}' \
  'must not persist derived fields' \
  'must not modify derived fields' \
  'load_work_item_document' \
  'project_work_item_snapshot' \
  'get_work_item_snapshot' \
  'read_work_item_history' \
  'HISTORY_COLLECTIONS' \
  'HISTORY_STATUS_BY_COLLECTION' \
  'HISTORY_REPOSITORY_FILTER_COLLECTIONS' \
  'history revision conflict' \
  'history cursor does not match collection or filters' \
  'PRAGMA user_version' \
  'WORK_ITEM_DATA_VERSION = 1' \
  '_migrate_legacy_lifecycle_statuses'; do
  rg -q "$pattern" "$core" || fail "core.py: missing read/storage contract: $pattern"
done

for pattern in \
  'MUTATION_OPERATION_MAX = 50' \
  'STATE_FIELDS' \
  'LIFECYCLE_TRANSITIONS' \
  'IMMUTABLE_FIELDS' \
  'WRITE_ONCE_FIELDS' \
  'question_upsert' \
  'decision_upsert' \
  'change_upsert' \
  'blocker_upsert' \
  'handoff_upsert' \
  'checkpoint_append' \
  'duplicate target' \
  '_validate_cross_record_references' \
  'BEGIN IMMEDIATE' \
  'revision conflict' \
  'validate_document(current)' \
  'validate_document(candidate)' \
  'mutation does not change canonical Work Item state' \
  '"updated": True' \
  '"changed": changed'; do
  rg -F -q "$pattern" "$mutations" || fail "mutations.py: missing incremental mutation invariant: $pattern"
done

# Mutation write path must stay one whole-document optimistic transaction. It must not
# hydrate public read surfaces, loop on conflicts, or recursively re-enter itself.
if ! MUTATIONS_PATH="$mutations" python3 - <<'PY'
import ast
import os
from pathlib import Path

path = Path(os.environ["MUTATIONS_PATH"])
tree = ast.parse(path.read_text(encoding="utf-8"))
mutate = next(
    node
    for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name == "mutate_work_item"
)
call_names = {
    node.func.id
    for node in ast.walk(mutate)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
}
assert "get_work_item_snapshot" not in call_names
assert "read_work_item_history" not in call_names
assert "mutate_work_item" not in call_names
assert not any(isinstance(node, ast.While) for node in ast.walk(mutate))
assert not any(
    isinstance(node, ast.ExceptHandler)
    and isinstance(node.type, ast.Name)
    and node.type.id == "ConflictError"
    for node in ast.walk(mutate)
)
PY
then
  fail 'mutations.py: mutation engine must not hydrate public reads or auto-retry/rebase stale operations'
fi

for pattern in \
  'class QuestionRecord' \
  'class DecisionRecord' \
  'class RequirementChangeRecord' \
  'class BlockerRecord' \
  'class HandoffRecord' \
  'class NextActionRecord' \
  'class CheckpointRecord' \
  'class WorkItemSnapshot' \
  'class WorkItemHistoryPage' \
  'class WorkItemStatePatch' \
  'class QuestionMutation' \
  'class DecisionMutation' \
  'class RequirementChangeMutation' \
  'class BlockerMutation' \
  'class HandoffMutation' \
  'class CheckpointAppendOperation' \
  'class QuestionUpsertOperation' \
  'class DecisionUpsertOperation' \
  'class ChangeUpsertOperation' \
  'class BlockerUpsertOperation' \
  'class HandoffUpsertOperation' \
  'class WorkItemMutation' \
  'MUTATION_OPERATION_MAX = 50' \
  'Required canonical question lifecycle' \
  'Required canonical decision lifecycle' \
  'extra="forbid"' \
  'extra="allow"' \
  'to_merge_patch' \
  'to_core_mutation' \
  'exclude_unset=True' \
  'by_alias=True' \
  'Current effective repository contribution/state' \
  'not a narrative of the latest session' \
  'kind: str | None' \
  'artifact_id: str | None' \
  'not an enum or workflow FSM' \
  'Partial semantic command' \
  'Historical semantic collections are intentionally not replaceable here'; do
  rg -F -q "$pattern" "$models" || fail "models.py: missing typed read/mutation contract: $pattern"
done

# Public mutation schema must make historical full-array replacement unrepresentable.
# Current-state null/omission merge semantics remain available only inside state patch;
# semantic record commands reject explicit null and use typed incremental operations.
if ! PYTHONPATH="$project" uv run --project "$project" python - <<'PY'
from pydantic import ValidationError
from models import (
    DecisionRecord,
    MUTATION_OPERATION_MAX,
    QuestionRecord,
    WorkItemMutation,
    WorkItemStatePatch,
)
assert WorkItemStatePatch.model_validate({}).to_merge_patch() == {}
assert WorkItemMutation.model_validate({"state": {"repos": {"old": None}}}).to_core_mutation() == {
    "state": {"repos": {"old": None}}
}
partial = WorkItemMutation.model_validate({
    "operations": [{
        "op": "question_upsert",
        "value": {"id": "q1", "status": "resolved", "decision_id": "d2"},
    }]
}).to_core_mutation()
assert partial["operations"][0]["value"] == {
    "id": "q1", "status": "resolved", "decision_id": "d2"
}
checkpoint = WorkItemMutation.model_validate({
    "operations": [{
        "op": "checkpoint_append",
        "value": {
            "repo": "repo-a",
            "kind": "implementation-rework",
            "artifact_id": "review:2",
            "summary": "Fixed review finding and reverified.",
        },
    }]
}).to_core_mutation()["operations"][0]["value"]
assert checkpoint["kind"] == "implementation-rework"
assert checkpoint["artifact_id"] == "review:2"
state_properties = WorkItemStatePatch.model_json_schema()["properties"]
for historical in ("questions", "decisions", "changes", "blockers", "handoffs", "checkpoints"):
    assert historical not in state_properties
assert WorkItemMutation.model_json_schema()["properties"]["operations"]["maxItems"] == MUTATION_OPERATION_MAX
try:
    WorkItemMutation.model_validate({"operations": [{"op": "question_upsert", "value": {"id": "q1", "answer": None}}]})
except ValidationError:
    pass
else:
    raise AssertionError("incremental semantic mutation must reject explicit null")
try:
    QuestionRecord.model_validate({"id": "q1", "question": "missing status"})
except ValidationError:
    pass
else:
    raise AssertionError("QuestionRecord.status must be required")
try:
    DecisionRecord.model_validate({"id": "d1", "summary": "missing status"})
except ValidationError:
    pass
else:
    raise AssertionError("DecisionRecord.status must be required")
PY
then
  fail 'models.py: bounded state + typed incremental mutation schema invariants failed'
fi

for pattern in \
  'ARTIFACT_TEMPLATES_ENV = "WORK_ITEM_ARTIFACT_TEMPLATES_PATH"' \
  'config" / "artifact-templates.json"' \
  'ARTIFACT_TEMPLATE_FILE_MAX_BYTES = 64_000' \
  'ARTIFACT_TEMPLATE_SECTION_MAX = 100' \
  'class ArtifactTemplateConfigError' \
  'resolve_artifact_templates_path' \
  'validate_artifact_templates' \
  'load_artifact_templates' \
  'template_guidance_for' \
  'unsupported types' \
  'duplicate id' \
  'unknown fields' \
  'copy.deepcopy'; do
  rg -F -q "$pattern" "$artifact_templates" || \
    fail "artifact_templates.py: missing config contract: $pattern"
done

# Parse the shipped config through the same stdlib validator used at MCP startup.
if ! PYTHONPATH="$project" ARTIFACT_TEMPLATE_CONFIG="$artifact_template_config" python3 - <<'PY'
import os
from artifact_templates import load_artifact_templates

templates = load_artifact_templates(os.environ["ARTIFACT_TEMPLATE_CONFIG"])
assert set(templates) == {"intake", "investigation", "plan", "review", "report"}
report = templates["report"]
assert [section["id"] for section in report["sections"]] == [
    "root-cause-requirement",
    "solution",
    "affected",
    "impact-module-analysis",
    "sql-report",
    "commits",
    "testcase-ut",
    "deploy",
]
assert report["sections"][0]["title"] == "h3. +1. Root-cause/requirement:+"
assert report["sections"][-1]["title"] == "h3. +8. Deploy:+"
commits = next(section for section in report["sections"] if section["id"] == "commits")
deploy = next(section for section in report["sections"] if section["id"] == "deploy")
testcase = next(section for section in report["sections"] if section["id"] == "testcase-ut")
assert "<<branch user tự điền>>" in commits["purpose"]
assert "<<pre4 user tự điền>>" in deploy["purpose"]
assert "never invent passing tests" in testcase["purpose"]
PY
then
  fail 'config/artifact-templates.json: default artifact template config is invalid'
fi

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
  'cursor revision' \
  '_parse_cursor' \
  '_cursor' \
  'artifact is complete and immutable' \
  'split it into smaller chunks' \
  'cursor is invalid' \
  'cannot finalize an artifact without content' \
  'ON DELETE CASCADE'; do
  rg -q "$pattern" "$artifacts" || fail "artifacts.py: missing bounded artifact contract: $pattern"
done

# Template config must never become an artifact storage dependency or second truth source.
if rg -q 'artifact_templates|ARTIFACT_TEMPLATES|template_guidance' "$artifacts"; then
  fail 'artifacts.py: artifact storage must not import, persist, or enforce template guidance'
fi

# CRITICAL PAYLOAD/REVISION INVARIANTS — DO NOT REMOVE OR WEAKEN THESE CHECKS
# merely to make a change pass. Artifact bodies must never become an unbounded
# MCP request/response, and artifact writes must remain independently revisioned
# from canonical Work Item state.
rg -q 'len\(value\.encode\("utf-8"\)\) > ARTIFACT_CHUNK_MAX_BYTES' "$artifacts" || \
  fail 'artifacts.py: append must enforce UTF-8 byte limit server-side'
rg -q 'ARTIFACT_READ_MIN_BYTES <= limit_bytes <= ARTIFACT_READ_MAX_BYTES' "$artifacts" || \
  fail 'artifacts.py: read must enforce bounded response size server-side'
rg -q 'return value' "$artifacts" || \
  fail 'artifacts.py: chunk content must be preserved rather than stripped/reformatted'
rg -q 'SET revision = \?, updated_at = \?' "$artifacts" || \
  fail 'artifacts.py: artifact append must advance artifact revision'
rg -q "SET state = 'complete', revision = \?, updated_at = \?" "$artifacts" || \
  fail 'artifacts.py: artifact finalize must advance artifact revision'
if rg -q 'UPDATE work_items|SET revision = .*work_items' "$artifacts"; then
  fail 'artifacts.py: artifact mutations must never update Work Item revision/state'
fi
if rg -q 'PRAGMA journal_mode|PRAGMA synchronous' "$artifacts"; then
  fail 'artifacts.py: base SQLite connection policy belongs to core.py and must not be duplicated'
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
  '_stream_artifact_section_chunks' \
  '_print_artifact_stream' \
  '_print_artifact_raw_stream' \
  '_get_artifact_json_readonly' \
  'SELECT content FROM work_item_artifact_chunks' \
  '--raw' \
  'QUESTIONS' \
  'DECISIONS' \
  'CHANGES' \
  'BLOCKERS' \
  'HANDOFFS' \
  'NEXT ACTIONS' \
  'CHECKPOINTS' \
  'revision='; do
  rg -q -- "$pattern" "$cli" || fail "cli.py: missing human-view contract: $pattern"
done

if rg -i -q '\b(insert|update|delete|replace|alter|drop|create|pragma|vacuum|reindex)\b[^\n]*(work_items|work_item_artifact|table|index|journal|synchronous)' "$cli"; then
  fail 'cli.py: human CLI must remain strictly read-only; SQL mutation/schema/PRAGMA path detected'
fi
if rg -q 'from (core|artifacts) import .*update_|from (core|artifacts) import .*create_|create_work_item\(|append_artifact\(|finalize_artifact\(' "$cli"; then
  fail 'cli.py: human CLI must not import/call Work Item or artifact mutation functions'
fi

if ! CLI_PATH="$cli" python3 - <<'PY'
import ast
import os
from pathlib import Path

path = Path(os.environ["CLI_PATH"])
text = path.read_text(encoding="utf-8")
tree = ast.parse(text)
funcs = {
    node.name: ast.get_source_segment(text, node) or ""
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
stream = funcs["_stream_artifact_section_chunks"]
diagnostic = funcs["_print_artifact_stream"]
raw = funcs["_print_artifact_raw_stream"]
build_parser = funcs["_build_parser"]
main = funcs["main"]
assert "SELECT content FROM work_item_artifact_chunks" in stream
assert "sys.stdout.write(text)" in stream
assert "_get_artifact_json_readonly" not in stream
assert "_stream_artifact_section_chunks" in diagnostic
assert "_get_artifact_json_readonly" not in diagnostic
assert "_stream_artifact_section_chunks" in raw
assert "_get_artifact_json_readonly" not in raw
assert "add_mutually_exclusive_group" in build_parser
assert '"--raw"' in build_parser
assert "_get_artifact_json_readonly" in main
assert "_print_artifact_stream" in main
assert "_print_artifact_raw_stream" in main
PY
then
  fail 'cli.py: diagnostic/raw artifact views must stream chunks; full materialization is reserved for explicit --json'
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