#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/knowledge"
errors=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  errors=$((errors + 1))
}

for command in bash python3 rg; do
  command -v "$command" >/dev/null 2>&1 || fail "missing required command: $command"
done

required=(
  README.md
  mcp/knowledge/core.py
  mcp/knowledge/server.py
  mcp/knowledge/pyproject.toml
  mcp/knowledge/tests/test_core.py
  scripts/install-user-mcp.sh
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
bash -n "$home/scripts/knowledge-cli.sh" || fail 'knowledge-cli.sh: invalid Bash syntax'
bash -n "$home/scripts/knowledge-mcp-server.sh" || fail 'knowledge-mcp-server.sh: invalid Bash syntax'
bash -n "$home/scripts/knowledge-template-check.sh" || fail 'knowledge-template-check.sh: invalid Bash syntax'

python_runtime="python3"
if [[ -x "$project/.venv/bin/python" ]]; then
  python_runtime="$project/.venv/bin/python"
fi

"$python_runtime" - "$home/mcp/knowledge/core.py" "$home/mcp/knowledge/server.py" "$home/scripts/knowledge.py" <<'PY' || fail 'knowledge Python source: invalid syntax'
import pathlib
import sys
for raw in sys.argv[1:]:
    path = pathlib.Path(raw)
    compile(path.read_text(encoding="utf-8"), str(path), "exec")
PY

"$python_runtime" - <<'PY' || fail 'knowledge core dependencies missing; run uv sync --project mcp/knowledge or provide filelock + PyYAML in current Python'
import filelock
import yaml
PY

server="$home/mcp/knowledge/server.py"
[[ "$(rg -c '^@mcp\.tool\(\)$' "$server" || true)" == "2" ]] || \
  fail 'knowledge server must expose exactly two MCP tools'
rg -q '^async def knowledge_read\(' "$server" || fail 'missing knowledge_read tool'
rg -q '^async def knowledge_write\(' "$server" || fail 'missing knowledge_write tool'

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

if rg -q '^[[:space:]]*language:' "$home/README.md" "$home/skills/knowledge-distill/SKILL.md"; then
  fail 'language field must not be part of the knowledge schema'
fi

if ! "$python_runtime" -m unittest discover -s "$project/tests" -v; then
  fail 'knowledge unit tests failed'
fi

if ! "$python_runtime" "$home/scripts/knowledge.py" check --root "$home/store"; then
  fail 'template store integrity check failed'
fi

if ((errors > 0)); then
  printf 'knowledge-template-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi

printf 'knowledge-template-check: PASS\n'
