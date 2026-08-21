#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/knowledge"
errors=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  errors=$((errors + 1))
}

for command in bash python3 rg cmp mktemp; do
  command -v "$command" >/dev/null 2>&1 || fail "missing required command: $command"
done

required=(
  README.md
  mcp/knowledge/contracts.py
  mcp/knowledge/core.py
  mcp/knowledge/server.py
  mcp/knowledge/pyproject.toml
  mcp/knowledge/tests/test_contracts.py
  mcp/knowledge/tests/test_core.py
  mcp/knowledge/tests/test_server_contract.py
  scripts/install-user-mcp.sh
  scripts/install-user-skill.sh
  scripts/knowledge-cli.sh
  scripts/knowledge-mcp-server.sh
  scripts/knowledge.py
  scripts/knowledge-template-check.sh
  skills/knowledge-distill/SKILL.md
  store/INDEX.md
)
for path in "${required[@]}"; do
  [[ -f "$home/$path" ]] || fail "missing file: $path"
done

bash -n "$home/scripts/install-user-mcp.sh" || fail 'install-user-mcp.sh: invalid Bash syntax'
bash -n "$home/scripts/install-user-skill.sh" || fail 'install-user-skill.sh: invalid Bash syntax'
bash -n "$home/scripts/knowledge-cli.sh" || fail 'knowledge-cli.sh: invalid Bash syntax'
bash -n "$home/scripts/knowledge-mcp-server.sh" || fail 'knowledge-mcp-server.sh: invalid Bash syntax'
bash -n "$home/scripts/knowledge-template-check.sh" || fail 'knowledge-template-check.sh: invalid Bash syntax'

python_runtime="python3"
if [[ -x "$project/.venv/bin/python" ]]; then
  python_runtime="$project/.venv/bin/python"
fi

"$python_runtime" - \
  "$home/mcp/knowledge/contracts.py" \
  "$home/mcp/knowledge/core.py" \
  "$home/mcp/knowledge/server.py" \
  "$home/scripts/knowledge.py" <<'PY' || fail 'knowledge Python source: invalid syntax'
import pathlib
import sys
for raw in sys.argv[1:]:
    path = pathlib.Path(raw)
    compile(path.read_text(encoding="utf-8"), str(path), "exec")
PY

"$python_runtime" - <<'PY' || fail 'knowledge runtime dependencies missing; run uv sync --project mcp/knowledge'
import filelock
import mcp
import pydantic
import yaml
PY

server="$home/mcp/knowledge/server.py"
contracts="$home/mcp/knowledge/contracts.py"
project_file="$home/mcp/knowledge/pyproject.toml"
skill="$home/skills/knowledge-distill/SKILL.md"
installer="$home/scripts/install-user-mcp.sh"
skill_installer="$home/scripts/install-user-skill.sh"

[[ "$(rg -c '^@mcp\.tool\(\)$' "$server" || true)" == "2" ]] || \
  fail 'knowledge server must expose exactly two MCP tools'
rg -q '^async def knowledge_read\(' "$server" || fail 'missing knowledge_read tool'
rg -q '^async def knowledge_write\(' "$server" || fail 'missing knowledge_write tool'
rg -q 'keywords: ReadKeywords' "$server" || \
  fail 'knowledge_read must expose typed keyword constraints'
rg -q 'context: KnowledgeReadContext \| None' "$server" || \
  fail 'knowledge_read context must use closed typed schema'
rg -q 'entries: WriteEntries' "$server" || \
  fail 'knowledge_write must expose typed nested entry schema'
rg -q '\) -> KnowledgeReadResult:' "$server" || \
  fail 'knowledge_read must expose structured output schema'
rg -q '\) -> KnowledgeWriteResult:' "$server" || \
  fail 'knowledge_write must expose structured output schema'
if rg -q 'entries: list\[dict\[str, Any\]\]' "$server"; then
  fail 'knowledge_write must not regress to generic dict input schema'
fi
rg -q 'knowledge-distill' "$server" || \
  fail 'knowledge_write contract must route semantic distillation through knowledge-distill'
rg -q 'task premise' "$server" || \
  fail 'knowledge_write contract must reject unverified task-premise persistence'
rg -q 'PRECALL LENGTH GATE' "$server" || \
  fail 'knowledge_write contract must expose the pre-call length gate'
rg -q '300 characters or less' "$server" || \
  fail 'knowledge_write contract must expose the summary preflight budget'
rg -q '600 characters or less' "$server" || \
  fail 'knowledge_write contract must expose the source-note preflight budget'
rg -q 'SERIALIZATION RECOVERY' "$server" || \
  fail 'knowledge_write contract must expose caller-side serialization recovery'
rg -q 'Do not resend the same multi-entry batch' "$server" || \
  fail 'knowledge_write serialization recovery must forbid unchanged batch retry'
rg -q 'one entry per typed `knowledge_write` call' "$server" || \
  fail 'knowledge_write serialization recovery must require single-entry fallback'
rg -q 'not persisted' "$server" || \
  fail 'knowledge_write serialization recovery must not claim failed entries persisted'
rg -q 'extra="forbid"' "$contracts" || \
  fail 'typed knowledge models must reject unknown fields'
rg -q "routing fields must be nested under the 'routing' object" "$contracts" || \
  fail 'typed write schema must explain flat routing mistakes'
rg -q 'filesystem fields are owned by Knowledge MCP' "$contracts" || \
  fail 'typed write schema must explain filesystem ownership'
rg -q 'Hard maximum is 500' "$contracts" || \
  fail 'routing.summary schema must expose its hard maximum'
rg -q 'target 300 characters or less' "$contracts" || \
  fail 'routing.summary schema must expose its conservative preflight budget'
rg -q 'is 1000 characters' "$contracts" || \
  fail 'source.note schema must expose its hard maximum'
rg -q 'target 600 characters or less' "$contracts" || \
  fail 'source.note schema must expose its conservative preflight budget'
rg -q '"pydantic>=2,<3"' "$project_file" || \
  fail 'pydantic must be an explicit runtime dependency'

for pattern in \
  'Persist what the work established, not what the task assumed' \
  'Compression must not increase certainty' \
  'Extract durable candidates from the evidence, not the task title' \
  'remaining uncertainty' \
  'immutable commit/revision' \
  'bug premise' \
  'knowledge_write\(entries=\[\]\)' \
  'Run payload readiness before calling knowledge_write' \
  'routing.summary.*retrieval abstract' \
  'non-empty `sources` list' \
  'typed `knowledge_write` payload' \
  'repair only the fields' \
  'do not weaken' \
  'Summary and source-note budget gate' \
  'Write `content` first' \
  'Draft `routing.summary` and `sources\[\]\.note` last' \
  '300 characters or less' \
  '600 characters or less' \
  'deterministically' \
  'Do not mechanically truncate' \
  'durable conclusion.*critical boundary' \
  'stable provenance location.*exact behavior/boundary' \
  'Tool-call JSON serialization recovery' \
  'input JSON failed to parse' \
  'do .*not.*resend.*same multi-entry batch' \
  'one typed tool call with exactly one' \
  'preserve.*exact `id` and.*`expected_revision`' \
  'do not manually construct.*JSON string' \
  'not persisted'; do
  rg -q "$pattern" "$skill" || fail "knowledge-distill missing quality gate: $pattern"
done

rg -q '\.agents/skills' "$skill_installer" || \
  fail 'skill installer must install Codex user-scope skill'
rg -q '\.claude/skills' "$skill_installer" || \
  fail 'skill installer must install Claude user-scope skill'
rg -q 'install-user-skill\.sh' "$installer" || \
  fail 'main knowledge installer must install the distillation skill'

skill_smoke_root="$(mktemp -d)"
if ! bash "$skill_installer" \
  --codex-root "$skill_smoke_root/codex" \
  --claude-root "$skill_smoke_root/claude" >/dev/null; then
  fail 'knowledge-distill user-scope installation smoke test failed'
else
  cmp -s "$skill" "$skill_smoke_root/codex/knowledge-distill/SKILL.md" || \
    fail 'Codex installed skill differs from canonical knowledge-distill skill'
  cmp -s "$skill" "$skill_smoke_root/claude/knowledge-distill/SKILL.md" || \
    fail 'Claude installed skill differs from canonical knowledge-distill skill'
  bash "$skill_installer" \
    --codex-root "$skill_smoke_root/codex" \
    --claude-root "$skill_smoke_root/claude" >/dev/null || \
    fail 'knowledge-distill user-scope installation must be idempotent'
fi
rm -rf "$skill_smoke_root"

core="$home/mcp/knowledge/core.py"
for contract in \
  'expected_revision' \
  'FileLock' \
  'os\.replace' \
  'canonical_relative_path' \
  'INDEX_FILENAME' \
  'MAX_DOCUMENT_BYTES'; do
  rg -q "$contract" "$core" || fail "knowledge core missing contract: $contract"
done

if rg -q '^[[:space:]]*language:' "$home/README.md" "$skill"; then
  fail 'language field must not be part of the knowledge schema'
fi

if ! "$python_runtime" -m unittest discover -s "$project/tests" -v; then
  fail 'knowledge unit/server-contract tests failed'
fi

if ! "$python_runtime" "$home/scripts/knowledge.py" check --root "$home/store"; then
  fail 'template store integrity check failed'
fi

if ((errors > 0)); then
  printf 'knowledge-template-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi

printf 'knowledge-template-check: PASS\n'
