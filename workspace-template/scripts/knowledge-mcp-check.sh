#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$workspace_root/mcp/knowledge"
errors=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  errors=$((errors + 1))
}

for command in uv python3 rg; do
  command -v "$command" >/dev/null 2>&1 || fail "missing required command: $command"
done

for path in \
  "$project/pyproject.toml" \
  "$project/core.py" \
  "$project/_core.py" \
  "$project/server.py" \
  "$project/cli.py" \
  "$project/tests/test_core.py" \
  "$workspace_root/scripts/qiqi-knowledge-mcp-server.sh" \
  "$workspace_root/scripts/qiqi-knowledge-store.sh" \
  "$workspace_root/docs/KNOWLEDGE_STORE.md" \
  "$workspace_root/AGENTS.md" \
  "$workspace_root/identity.md" \
  "$workspace_root/README.md" \
  "$workspace_root/.codex/config.toml"; do
  [[ -f "$path" ]] || fail "missing file: ${path#$workspace_root/}"
done

bash -n "$workspace_root/scripts/qiqi-knowledge-mcp-server.sh" || \
  fail 'qiqi-knowledge-mcp-server.sh: invalid Bash syntax'
bash -n "$workspace_root/scripts/qiqi-knowledge-store.sh" || \
  fail 'qiqi-knowledge-store.sh: invalid Bash syntax'

for file in core.py _core.py server.py cli.py tests/test_core.py; do
  python3 - "$project/$file" <<'PY' || fail "$file: invalid Python syntax"
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
compile(path.read_text(encoding="utf-8"), str(path), "exec")
PY
done

server="$project/server.py"
[[ "$(rg -c '^@mcp\.tool\(\)$' "$server" || true)" == "2" ]] || \
  fail 'Knowledge MCP must expose exactly two public tools'
rg -q '^async def knowledge_read\(' "$server" || fail 'missing knowledge_read tool'
rg -q '^async def knowledge_write\(' "$server" || fail 'missing knowledge_write tool'

public_core="$project/core.py"
impl_core="$project/_core.py"
rg -q 'must be an absolute path' "$public_core" || \
  fail 'public KnowledgeStore API must reject relative store roots'
rg -q 'QIQI_KNOWLEDGE_ROOT' "$impl_core" || fail 'core must use external knowledge root'
rg -q 'expected_revision' "$impl_core" || fail 'core missing optimistic revision check'
rg -q 'FileLock' "$impl_core" || fail 'core missing cross-process file lock'
rg -q 'os\.replace' "$impl_core" || fail 'core missing atomic file replace'
rg -q 'INDEX_NAME = "INDEX\.md"' "$impl_core" || fail 'core missing INDEX.md contract'
for scope in global system repo domain; do
  rg -q "\"$scope\"" "$impl_core" || fail "core missing shared scope kind: $scope"
done
rg -q '_reject_unknown_keys' "$impl_core" || fail 'core must reject unsupported semantic/storage fields'
rg -q 'test_unknown_storage_field_rejected' "$project/tests/test_core.py" || \
  fail 'tests must cover agent-supplied storage field rejection'
rg -q 'test_document_without_aliases_is_canonical' "$project/tests/test_core.py" || \
  fail 'tests must cover optional aliases canonicalization'
rg -q 'test_revision_conflict_rejected' "$project/tests/test_core.py" || \
  fail 'tests must cover optimistic revision conflicts'
rg -q 'test_manual_document_requires_reindex' "$project/tests/test_core.py" || \
  fail 'tests must cover human-edit + reindex workflow'
rg -q 'test_relative_store_root_rejected' "$project/tests/test_core.py" || \
  fail 'tests must cover CWD-independent absolute store root invariant'

knowledge_doc="$workspace_root/docs/KNOWLEDGE_STORE.md"
rg -q 'user scope' "$knowledge_doc" || fail 'KNOWLEDGE_STORE.md: missing user-scope registration policy'
rg -q 'Agent \*\*submit semantic knowledge, không tạo file\*\*' "$knowledge_doc" || \
  fail 'KNOWLEDGE_STORE.md: agent must submit semantics rather than files'
rg -q 'knowledge_write(entries=\[\])' "$knowledge_doc" || \
  fail 'KNOWLEDGE_STORE.md: explicit empty review contract missing'
rg -q 'expected_revision' "$knowledge_doc" || \
  fail 'KNOWLEDGE_STORE.md: update revision contract missing'
if rg -q '^[[:space:]]*language[[:space:]]*:' "$knowledge_doc"; then
  fail 'KNOWLEDGE_STORE.md: language field must not exist'
fi

agents="$workspace_root/AGENTS.md"
for pattern in \
  '^## Shared Knowledge$' \
  '`knowledge_read`' \
  '`knowledge_write`' \
  'knowledge_write(entries=\[\])' \
  'live source/test thắng' \
  'không có field `language`'; do
  rg -q "$pattern" "$agents" || fail "AGENTS.md: missing shared knowledge policy: $pattern"
done

identity="$workspace_root/identity.md"
rg -q '`knowledge_read`' "$identity" || fail 'identity.md: missing shared knowledge read responsibility'
rg -q '`knowledge_write`' "$identity" || fail 'identity.md: missing shared knowledge write responsibility'

codex_config="$workspace_root/.codex/config.toml"
if rg -q 'qiqi_knowledge|knowledge_read|knowledge_write' "$codex_config"; then
  fail '.codex/config.toml: Knowledge MCP must not be registered project-scoped; use user scope'
fi
rg -q '^\[mcp_servers\.qiqi_delegate\]$' "$codex_config" || \
  fail '.codex/config.toml: qiqi_delegate project-scoped registration missing'

if ! uv run --project "$project" python -c \
  'from mcp.server import MCPServer; import yaml; from filelock import FileLock; print("knowledge-mcp-runtime: PASS")' \
  >/dev/null; then
  fail 'Knowledge MCP runtime import failed; run uv sync --project mcp/knowledge'
fi

if ! (cd "$project" && uv run --project . python -m unittest discover -s tests -v); then
  fail 'Knowledge MCP unit tests failed'
fi

if ((errors > 0)); then
  printf 'knowledge-mcp-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi

printf 'knowledge-mcp-check: PASS\n'
