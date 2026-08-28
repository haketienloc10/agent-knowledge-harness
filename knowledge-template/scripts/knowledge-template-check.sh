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
  mcp/knowledge/partial_contracts.py
  mcp/knowledge/partial_update.py
  mcp/knowledge/sections.py
  mcp/knowledge/server.py
  mcp/knowledge/pyproject.toml
  mcp/knowledge/tests/test_contracts.py
  mcp/knowledge/tests/test_core.py
  mcp/knowledge/tests/test_partial_contracts.py
  mcp/knowledge/tests/test_partial_update.py
  mcp/knowledge/tests/test_review_regressions.py
  mcp/knowledge/tests/test_section_integrity.py
  mcp/knowledge/tests/test_server_contract.py
  scripts/install-user-mcp.sh
  scripts/install-user-skill.sh
  scripts/knowledge-cli.sh
  scripts/knowledge-mcp-server.sh
  scripts/knowledge-template-check.sh
  scripts/knowledge.py
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
  "$home/mcp/knowledge/partial_contracts.py" \
  "$home/mcp/knowledge/partial_update.py" \
  "$home/mcp/knowledge/sections.py" \
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
partial_contracts="$home/mcp/knowledge/partial_contracts.py"
partial_update="$home/mcp/knowledge/partial_update.py"
sections="$home/mcp/knowledge/sections.py"
project_file="$home/mcp/knowledge/pyproject.toml"
skill="$home/skills/knowledge-distill/SKILL.md"
installer="$home/scripts/install-user-mcp.sh"
skill_installer="$home/scripts/install-user-skill.sh"

[[ "$(rg -c '^@mcp\.tool\(\)$' "$server" || true)" == "6" ]] || \
  fail 'knowledge server must expose exactly six MCP tools'
for tool in knowledge_search knowledge_read knowledge_read_metadata knowledge_read_section knowledge_write knowledge_update; do
  rg -q "^async def ${tool}\\(" "$server" || fail "missing ${tool} tool"
done
rg -q 'keywords: SearchKeywords' "$server" || \
  fail 'knowledge_search must expose typed keyword constraints'
rg -q 'context: KnowledgeSearchContext \| None' "$server" || \
  fail 'knowledge_search context must use closed typed schema'
rg -q 'ids: ReadIds' "$server" || \
  fail 'knowledge read tools must accept exact bounded ids'
rg -q 'section_id: SectionId' "$server" || \
  fail 'knowledge_read_section must expose a stable typed section id'
rg -q 'entries: WriteEntries' "$server" || \
  fail 'knowledge_write must expose typed nested entry schema'
rg -q 'expected_revision: ExactReadRevision' "$server" || \
  fail 'knowledge_update must accept exact revision from any scoped exact read surface'
rg -q 'changes: KnowledgePatch' "$server" || \
  fail 'knowledge_update must expose a typed partial patch schema'
rg -q '\) -> KnowledgeSearchResult:' "$server" || \
  fail 'knowledge_search must expose structured output schema'
rg -q '\) -> KnowledgeReadResult:' "$server" || \
  fail 'knowledge_read must expose structured output schema'
rg -q '\) -> KnowledgeMetadataReadResult:' "$server" || \
  fail 'knowledge_read_metadata must expose structured output schema'
rg -q '\) -> KnowledgeSectionReadResult:' "$server" || \
  fail 'knowledge_read_section must expose structured output schema'
rg -q '\) -> KnowledgeWriteResult:' "$server" || \
  fail 'knowledge mutation tools must expose structured output schema'
rg -q 'routing decision cards' "$server" || \
  fail 'server instructions must state search cards are discovery-only'
rg -q 'intentionally does not return revision' "$server" || \
  fail 'server instructions must preserve exact-read-before-update guardrail'
rg -q 'smallest semantic scope required' "$server" || \
  fail 'server instructions must explain progressive partial reads'
rg -q 'knowledge-distill' "$server" || \
  fail 'knowledge mutation contract must route semantic distillation through knowledge-distill'

rg -q 'extra="forbid"' "$contracts" || \
  fail 'typed knowledge models must reject unknown fields'
rg -q "routing fields must be nested under the 'routing' object" "$contracts" || \
  fail 'typed write schema must explain flat routing mistakes'
rg -q 'filesystem fields are owned by Knowledge MCP' "$contracts" || \
  fail 'typed write schema must explain filesystem ownership'
rg -q 'MAX_READ_RESULTS' "$contracts" || \
  fail 'knowledge_read ids must have a hard hydration bound'
rg -q '^class KnowledgeSearchHit' "$contracts" || \
  fail 'missing thin search-hit schema'
rg -q '^class KnowledgeReadItem' "$contracts" || \
  fail 'missing full read-item schema'
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
  '^ExactReadRevision = Annotated' \
  'knowledge_read_metadata' \
  'knowledge_read_section' \
  'knowledge_update.expected_revision' \
  '^class _ExactSectionModel' \
  '^class KnowledgeMetadataReadResult' \
  '^class KnowledgeSectionReadResult' \
  '^class KnowledgeRoutingPatch' \
  '^class KnowledgeMetadataPatch' \
  '^class KnowledgeSectionPatch' \
  '^class KnowledgePatch' \
  'str_strip_whitespace=False' \
  'MAX_SECTION_ID_CHARS' \
  'MAX_SECTION_HEADING_CHARS' \
  'MAX_SECTION_BODY_CHARS' \
  'cannot be null; omit it when unchanged' \
  'full content replacement and section replacement are mutually exclusive'; do
  rg -q "$pattern" "$partial_contracts" || fail "partial contracts missing invariant: $pattern"
done

for pattern in \
  'read_knowledge' \
  'write_knowledge' \
  'current\["revision"\] != expected_revision' \
  'knowledge revision conflict' \
  'replace_section' \
  'parse_sections' \
  'metadata.*content.*section'; do
  rg -U -q "$pattern" "$partial_update" || fail "partial update adapter missing invariant: $pattern"
done

for pattern in \
  'MAX_KNOWLEDGE_SECTIONS = 100' \
  'MAX_SECTION_ID_CHARS = 100' \
  'MAX_SECTION_HEADING_CHARS = 300' \
  'MAX_SECTION_BODY_CHARS = 24_000' \
  'knowledge-section:' \
  'lowercase-kebab-id' \
  'duplicate knowledge section id' \
  'heading exceeds' \
  'body exceeds' \
  'immediately followed' \
  'Markdown H2-H6 heading' \
  '_opening_fence' \
  'fenced Markdown code blocks are ignored' \
  '_section_body_lines' \
  'never content whitespace' \
  'preserve all existing semantic section markers' \
  'section structure is owned by the canonical document'; do
  rg -U -q "$pattern" "$sections" || fail "semantic section parser missing invariant: $pattern"
done

for pattern in \
  'Persist what the work established, not what the task assumed' \
  'Compression must not increase certainty' \
  'candidate meaning' \
  'remaining uncertainty' \
  'immutable commit/revision' \
  'bug premise' \
  'knowledge_write\(entries=\[\]\)' \
  'knowledge_update' \
  'knowledge_read_metadata' \
  'knowledge_read_section' \
  'smallest sufficient semantic scope' \
  'knowledge-section:' \
  'Run payload readiness before calling knowledge_write|Run payload readiness before mutation' \
  'routing.summary.*retrieval abstract' \
  'non-empty `sources` list' \
  'Build typed write payload|Build typed mutation payload' \
  'repair only the fields' \
  'Do not weaken' \
  'Summary and source-note budget gate' \
  '[Vv]iết `content` trước' \
  'Draft `routing.summary`' \
  '300 characters or less' \
  '600 characters or less' \
  'deterministically' \
  'Do not mechanically truncate' \
  'Tool-call JSON serialization recovery' \
  'knowledge_search' \
  'decision card' \
  'knowledge_read' \
  'one or two' \
  'revision'; do
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
  'MAX_DOCUMENT_BYTES' \
  'MAX_SEARCH_RESULTS' \
  'MAX_READ_RESULTS' \
  'search_knowledge' \
  'read_knowledge' \
  'parse_sections' \
  '_validate_section_structure' \
  '_validate_section_structure\(content, label="knowledge write content"\)' \
  '_validate_section_structure\(body, label=relative\)'; do
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
