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
  scripts/qiqi-mcp-server.sh
  scripts/qiqi-codex-agent.sh
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

for pattern in \
  'work_items_dir="$workspace_root/work-items"' \
  'mkdir -p "$work_items_dir"' \
  'export QIQI_WORK_ITEMS_DIR="$work_items_dir"' \
  'export PATH="$workspace_root/scripts:$PATH"'; do
  grep -Fq -- "$pattern" "$launcher" || fail "launcher missing Work Items contract: $pattern"
done

grep -Fq 'command: qiqi-codex-agent.sh' "$routing" || fail 'Codex must use Work Items adapter wrapper'
grep -Fq 'env: QIQI_WORK_ITEMS_DIR' "$routing" || fail 'Claude must use common QIQI_WORK_ITEMS_DIR'
grep -Fq 'required: true' "$routing" || fail 'Work Items directory must be required for configured shared-dir route'
grep -Fq -- '--add-dir "$QIQI_WORK_ITEMS_DIR"' "$workspace_root/scripts/qiqi-codex-agent.sh" || fail 'Codex wrapper must inject --add-dir'

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

for pattern in \
  'Work Item là filesystem current-state dossier' \
  'Requirement change rewrite current requirement' \
  'TaskPacket phải là smallest sufficient'; do
  grep -Fq -- "$pattern" "$agents" || fail "AGENTS.md missing current Work Item policy: $pattern"
done

bash -n "$launcher"
bash -n "$workspace_root/scripts/qiqi-codex-agent.sh"
bash -n "$workspace_root/scripts/workspace-check.sh"

command -v uv >/dev/null 2>&1 || fail 'missing command: uv'
uv run --project "$mcp_project" python -m unittest discover -s "$mcp_project/tests" -v

printf 'Workspace contract: OK\n'
