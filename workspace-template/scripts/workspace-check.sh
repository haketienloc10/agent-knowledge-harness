#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mcp_project="$workspace_root/mcp/qiqi_delegate"
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

required=(
  AGENTS.md
  identity.md
  repos.yaml
  work-items/.gitkeep
  instructions/agent-routing.yaml
  instructions/model-routing.md
  scripts/qiqi-mcp-server.sh
  mcp/qiqi_delegate/server.py
  mcp/qiqi_delegate/core.py
  .codex/config.toml
)
for rel in "${required[@]}"; do
  [[ -f "$workspace_root/$rel" ]] || fail "missing required workspace file: $rel"
done

launcher="$workspace_root/scripts/qiqi-mcp-server.sh"
routing="$workspace_root/instructions/agent-routing.yaml"
config="$workspace_root/.codex/config.toml"
agents="$workspace_root/AGENTS.md"
model_routing="$workspace_root/instructions/model-routing.md"

for pattern in \
  'work_items_dir="$workspace_root/work-items"' \
  'mkdir -p "$work_items_dir"' \
  'export QIQI_WORK_ITEMS_DIR="$work_items_dir"'; do
  grep -Fq -- "$pattern" "$launcher" || fail "launcher missing delegated Work Items contract: $pattern"
done

grep -Fq 'command: codex' "$routing" || fail 'Codex must resolve the native codex CLI'
grep -Fq 'command: claude' "$routing" || fail 'Claude must resolve the native claude CLI'
[[ "$(grep -Fc 'env: QIQI_WORK_ITEMS_DIR' "$routing")" -eq 2 ]] || \
  fail 'Codex and Claude must both declare QIQI_WORK_ITEMS_DIR additional_dirs'
[[ "$(grep -Fc 'required: true' "$routing")" -ge 2 ]] || \
  fail 'Work Items directory must be required for both supported shared-dir routes'

legacy_scan=(
  "$launcher"
  "$routing"
  "$config"
  "$agents"
  "$workspace_root/identity.md"
  "$workspace_root/README.md"
  "$workspace_root/docs/WORKSPACE_SETUP.md"
  "$workspace_root/docs/examples/agent-routing.claude-code.yaml"
  "$workspace_root/docs/examples/agent-routing.codex.yaml"
)
if grep -q 'QIQI_CLAUDE_ADDITIONAL_DIR' "${legacy_scan[@]}"; then
  fail 'legacy Claude-specific additional-dir env remains in current runtime/config/policy'
fi
if grep -Eq '^env_vars[[:space:]]*=' "$config"; then
  fail '.codex/config.toml must not require externally exported Work Items env'
fi
if grep -Fq 'export PATH="$workspace_root/scripts:$PATH"' "$launcher"; then
  fail 'launcher must not shadow native agent CLIs with workspace wrappers'
fi

for pattern in \
  'Work Item là filesystem current-state dossier' \
  'parent không phụ thuộc vào env do MCP child export' \
  'Requirement change rewrite current requirement' \
  'TaskPacket phải là smallest sufficient' \
  'Default delegation route = `claude-balanced`' \
  'just-in-time ngay trước route decision'; do
  grep -Fq -- "$pattern" "$agents" || fail "AGENTS.md missing current policy: $pattern"
done

grep -Fq 'đọc file này ngay trước route decision' "$model_routing" || \
  fail 'model-routing.md must require just-in-time route policy hydration'
grep -Fq 'Default delegation route = claude-balanced' "$model_routing" || \
  fail 'model-routing.md must preserve claude-balanced default'

bash -n "$launcher"
bash -n "$workspace_root/scripts/workspace-check.sh"

command -v uv >/dev/null 2>&1 || fail 'missing command: uv'
uv run --project "$mcp_project" python -m unittest discover -s "$mcp_project/tests" -v

printf 'Workspace contract: OK\n'
