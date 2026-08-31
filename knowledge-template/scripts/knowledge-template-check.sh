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
  mcp/knowledge/tests/test_html_block_sections.py
  mcp/knowledge/tests/test_partial_contracts.py
  mcp/knowledge/tests/test_partial_update.py
  mcp/knowledge/tests/test_review_5058125369.py
  mcp/knowledge/tests/test_review_5058234594.py
  mcp/knowledge/tests/test_review_5058439895.py
  mcp/knowledge/tests/test_review_5060423648.py
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

for script in \
  scripts/install-user-mcp.sh \
  scripts/install-user-skill.sh \
  scripts/knowledge-cli.sh \
  scripts/knowledge-mcp-server.sh \
  scripts/knowledge-template-check.sh; do
  bash -n "$home/$script" || fail "$script: invalid Bash syntax"
done

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
import markdown_it
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
core="$home/mcp/knowledge/core.py"

# Public MCP surface and progressive-disclosure contract.
[[ "$(rg -c '^@mcp\.tool\(\)$' "$server" || true)" == "6" ]] || \
  fail 'knowledge server must expose exactly six MCP tools'
for tool in knowledge_search knowledge_read knowledge_read_metadata knowledge_read_section knowledge_write knowledge_update; do
  rg -q "^async def ${tool}\\(" "$server" || fail "missing ${tool} tool"
done
for pattern in \
  'keywords: SearchKeywords' \
  'context: KnowledgeSearchContext \| None' \
  'ids: ReadIds' \
  'section_id: SectionId' \
  'entries: WriteEntries' \
  'expected_revision: ExactReadRevision' \
  'changes: KnowledgePatch' \
  '\) -> KnowledgeSearchResult:' \
  '\) -> KnowledgeReadResult:' \
  '\) -> KnowledgeMetadataReadResult:' \
  '\) -> KnowledgeSectionReadResult:' \
  '\) -> KnowledgeWriteResult:' \
  'routing decision cards' \
  'intentionally does not return revision' \
  'smallest semantic scope required' \
  'knowledge-distill'; do
  rg -q "$pattern" "$server" || fail "knowledge server missing public invariant: $pattern"
done

# Full read/write typed contract.
for pattern in \
  'extra="forbid"' \
  '^ExactMarkdownText = Annotated' \
  'strip_whitespace=False' \
  "routing fields must be nested under the 'routing' object" \
  'filesystem fields are owned by Knowledge MCP' \
  'MAX_READ_RESULTS' \
  '^class KnowledgeSearchHit' \
  '^class KnowledgeReadItem' \
  'Hard maximum is 500' \
  'target 300 characters or less' \
  'is 1000 characters' \
  'target 600 characters or less'; do
  rg -q "$pattern" "$contracts" || fail "knowledge contracts missing invariant: $pattern"
done

# Scoped exact-read / partial-patch schema. KnowledgePatch is the single patch grammar.
for pattern in \
  '^ExactReadRevision = Annotated' \
  'knowledge_read_metadata' \
  'knowledge_read_section' \
  'knowledge_update.expected_revision' \
  '^class KnowledgeMetadataReadResult' \
  '^class KnowledgeSectionReadResult' \
  '^class KnowledgeRoutingPatch' \
  '^class KnowledgeMetadataPatch' \
  '^class KnowledgeSectionPatch' \
  '^class KnowledgePatch' \
  'MAX_SECTION_ID_CHARS' \
  'MAX_SECTION_HEADING_CHARS' \
  'MAX_SECTION_BODY_CHARS' \
  'cannot be null; omit it when unchanged' \
  'full content replacement and section replacement are mutually exclusive'; do
  rg -q "$pattern" "$partial_contracts" || fail "partial contracts missing invariant: $pattern"
done
for pattern in \
  'KnowledgePatch' \
  'KnowledgePatch\.model_validate' \
  'read_knowledge' \
  'write_knowledge' \
  'current\["revision"\] != expected_revision' \
  'knowledge revision conflict' \
  'replace_section'; do
  rg -q "$pattern" "$partial_update" || fail "partial update adapter missing invariant: $pattern"
done
if rg -q '^def _validate_partial_changes\(' "$partial_update"; then
  fail 'partial update adapter must not duplicate the KnowledgePatch grammar'
fi

# Stable semantic sections: lexical Knowledge rules here; CommonMark block ownership is
# delegated to a maintained parser and behavior details are owned by unit/integration tests.
for pattern in \
  'MAX_KNOWLEDGE_SECTIONS = 100' \
  'MAX_SECTION_ID_CHARS = 100' \
  'MAX_SECTION_HEADING_CHARS = 300' \
  'MAX_SECTION_BODY_CHARS = 24_000' \
  'SECTION_MARKER_PREFIX' \
  'SECTION_MARKER_RE' \
  'SECTION_HEADING_RE' \
  'MARKDOWN_LINE_ENDING_RE' \
  'MarkdownIt\("commonmark"' \
  '"html": True' \
  '^def parse_sections\(' \
  '^def section_summaries\(' \
  '^def read_section\(' \
  '^def replace_section\(' \
  'duplicate knowledge section id' \
  'heading exceeds' \
  'body exceeds' \
  'immediately followed' \
  'Markdown H2-H6 heading' \
  'preserve all existing semantic section markers'; do
  rg -q "$pattern" "$sections" || fail "semantic section contract missing invariant: $pattern"
done
rg -q '"markdown-it-py>=3,<5"' "$project_file" || \
  fail 'markdown-it-py must be an explicit runtime dependency for CommonMark classification'
rg -q '"pydantic>=2,<3"' "$project_file" || \
  fail 'pydantic must be an explicit runtime dependency'

# knowledge-distill remains semantic quality policy independent of storage implementation.
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

# User-scope installation and upgrade safety.
rg -q '\.agents/skills' "$skill_installer" || \
  fail 'skill installer must install Codex user-scope skill'
rg -q '\.claude/skills' "$skill_installer" || \
  fail 'skill installer must install Claude user-scope skill'
rg -q 'install-user-skill\.sh' "$installer" || \
  fail 'main knowledge installer must install the distillation skill'
rg -q 'knowledge\.py" check --root' "$installer" || \
  fail 'main knowledge installer must preflight the canonical store before registration'
rg -q 'compatibility preflight failed' "$installer" || \
  fail 'main knowledge installer must explain store compatibility preflight failure'
rg -q 'reserved section-marker collisions' "$installer" || \
  fail 'main knowledge installer must explain reserved-prefix collision repair'

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

# Canonical storage/concurrency/integrity stays owned by core.
for contract in \
  'expected_revision' \
  'FileLock' \
  'os\.replace' \
  'canonical_relative_path' \
  'INDEX_FILENAME' \
  'MAX_CONTENT_CHARS' \
  'MAX_DOCUMENT_BYTES' \
  'MAX_SEARCH_RESULTS' \
  'MAX_READ_RESULTS' \
  'init_store' \
  'search_knowledge' \
  'read_knowledge' \
  'parse_sections' \
  'split_markdown_lines' \
  '_validate_section_structure' \
  '_semantic_content_from_body' \
  'content exceeds.*MAX_CONTENT_CHARS' \
  '_validate_section_structure\(content, label="knowledge write content"\)' \
  '_validate_section_structure\(content, label=relative\)'; do
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
