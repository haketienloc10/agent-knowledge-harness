#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
errors=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  errors=$((errors + 1))
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "missing file: ${path#$workspace_root/}"
}

require_dir() {
  local path="$1"
  [[ -d "$path" ]] || fail "missing directory: ${path#$workspace_root/}"
}

for command in git rg uv python3 yq; do
  require_command "$command"
done

required_files=(
  AGENTS.md
  identity.md
  SYSTEM_MAP.md
  repos.yaml
  KNOWLEDGE.md
  knowledge/INDEX.md
  knowledge/glossary.md
  knowledge/proposals/TEMPLATE.md
  .qiqi/tasks/TEMPLATE.md
  instructions/model-routing.md
  .codex/config.toml
  mcp/qiqi_delegate/pyproject.toml
  mcp/qiqi_delegate/server.py
  scripts/qiqi-mcp-server.sh
  scripts/workspace-check.sh
  docs/WORKSPACE_SETUP.md
)

for path in "${required_files[@]}"; do
  require_file "$workspace_root/$path"
done

required_dirs=(
  knowledge/systems
  knowledge/contracts
  knowledge/decisions
  knowledge/proposals
  .qiqi/tasks/active
  .qiqi/tasks/completed
)

for path in "${required_dirs[@]}"; do
  require_dir "$workspace_root/$path"
done

managed_files=(
  "$workspace_root/repos.yaml"
  "$workspace_root/SYSTEM_MAP.md"
  "$workspace_root/instructions/model-routing.md"
)

existing_managed_files=()
for path in "${managed_files[@]}"; do
  [[ -f "$path" ]] && existing_managed_files+=("$path")
done

if ((${#existing_managed_files[@]} > 0)) && \
  rg -n '\{\{[^}]+\}\}' "${existing_managed_files[@]}"; then
  fail 'unresolved placeholder(s) found in workspace configuration'
fi

policy_files=(
  "$workspace_root/AGENTS.md"
  "$workspace_root/identity.md"
  "$workspace_root/README.md"
  "$workspace_root/docs/WORKSPACE_SETUP.md"
  "$workspace_root/instructions/model-routing.md"
)

existing_policy_files=()
for path in "${policy_files[@]}"; do
  [[ -f "$path" ]] && existing_policy_files+=("$path")
done

if ((${#existing_policy_files[@]} > 0)) && \
  rg -n 'Herdr|HERDR_ENV|qiqi-agent-turn|qiqi-agent-resume' "${existing_policy_files[@]}"; then
  fail 'legacy Herdr/session orchestration reference found in MCP-only policy'
fi

agents="$workspace_root/AGENTS.md"
if [[ -f "$agents" ]]; then
  for pattern in \
    '`identity\.md`' \
    '`repos\.yaml`' \
    '`SYSTEM_MAP\.md`' \
    '`KNOWLEDGE\.md`' \
    '`instructions/model-routing\.md`' \
    '`delegate_repo_task`' \
    '`\.qiqi/tasks/'; do
    rg -q "$pattern" "$agents" || fail "AGENTS.md: missing required route: $pattern"
  done
  rg -q 'Không có polling workflow' "$agents" || \
    fail 'AGENTS.md: missing no-polling invariant'
  rg -q 'Không có đường vòng' "$agents" || \
    fail 'AGENTS.md: missing no-bypass invariant'
fi

codex_config="$workspace_root/.codex/config.toml"
if [[ -f "$codex_config" ]]; then
  rg -q '^\[mcp_servers\.qiqi_delegate\]$' "$codex_config" || \
    fail '.codex/config.toml: missing qiqi_delegate MCP server'
  rg -q 'enabled_tools = \["delegate_repo_task"\]' "$codex_config" || \
    fail '.codex/config.toml: MCP must expose only delegate_repo_task'
  rg -q 'tool_timeout_sec = 7200' "$codex_config" || \
    fail '.codex/config.toml: expected long synchronous tool timeout'
  rg -q 'required = true' "$codex_config" || \
    fail '.codex/config.toml: qiqi_delegate must be required'
fi

launcher="$workspace_root/scripts/qiqi-mcp-server.sh"
if [[ -f "$launcher" ]]; then
  bash -n "$launcher" || fail 'qiqi-mcp-server.sh: invalid Bash syntax'
  rg -q 'uv run --project' "$launcher" || \
    fail 'qiqi-mcp-server.sh: must launch MCP through uv project'
  rg -q 'QIQI_WORKSPACE_ROOT' "$launcher" || \
    fail 'qiqi-mcp-server.sh: must pass workspace root to MCP server'
fi

server="$workspace_root/mcp/qiqi_delegate/server.py"
if [[ -f "$server" ]]; then
  python3 - "$server" <<'PY' || fail 'qiqi_delegate/server.py: invalid Python syntax'
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
compile(path.read_text(encoding="utf-8"), str(path), "exec")
PY

  for pattern in \
    'FastMCP' \
    'asyncio\.Lock' \
    'def delegate_repo_task' \
    '"exec"' \
    '"--ephemeral"' \
    '"--output-schema"' \
    'mcp_servers\.qiqi_delegate\.enabled=false' \
    'transcript\.log'; do
    rg -q "$pattern" "$server" || fail "qiqi_delegate/server.py: missing contract: $pattern"
  done

  if rg -q 'def (status|wait|read_transcript|resume|list_runs)\b' "$server"; then
    fail 'qiqi_delegate/server.py: progress/session tool must not exist'
  fi
fi

routing="$workspace_root/instructions/model-routing.md"
if [[ -f "$routing" ]]; then
  rg -q 'Model ID' "$routing" || fail 'model-routing.md: missing Model ID'
  rg -q 'Reasoning effort' "$routing" || fail 'model-routing.md: missing reasoning effort'
  for profile in fast balanced deep verifier; do
    rg -q "\`$profile\`" "$routing" || fail "model-routing.md: missing $profile profile"
  done
fi

if ! yq --version 2>&1 | rg -q 'version v?4\.'; then
  fail 'unsupported yq version; install yq version 4'
else
  if ! yq -e '.workspace.name | type == "!!str" and length > 0' \
    "$workspace_root/repos.yaml" >/dev/null; then
    fail 'repos.yaml: workspace.name must be a non-empty string'
  fi

  if ! yq -e '.repositories | type == "!!seq" and length > 0' \
    "$workspace_root/repos.yaml" >/dev/null; then
    fail 'repos.yaml: repositories must be a non-empty list'
  else
    mapfile -t repository_names < <(yq -r '.repositories[].name' "$workspace_root/repos.yaml")
    mapfile -t repository_paths < <(yq -r '.repositories[].path' "$workspace_root/repos.yaml")

    for index in "${!repository_names[@]}"; do
      name="${repository_names[$index]}"
      path="${repository_paths[$index]}"

      [[ -n "$name" && "$name" != "null" ]] || fail 'repos.yaml: repository name is empty'
      [[ -n "$path" && "$path" != "null" ]] || fail "repos.yaml: ${name}: path is empty"
      [[ "$path" != /* ]] || fail "repos.yaml: ${name}: path must be relative"
      [[ "$path" != *'..'* ]] || fail "repos.yaml: ${name}: path must not contain .."

      module_root="$workspace_root/$path"
      if ! git -C "$module_root" rev-parse --show-toplevel >/dev/null 2>&1; then
        fail "repos.yaml: ${name}: path is not a Git repository: $path"
        continue
      fi

      git_root="$(git -C "$module_root" rev-parse --show-toplevel)"
      [[ "$git_root" == "$module_root" ]] || \
        fail "repos.yaml: ${name}: path must be the Git root: $path"
    done

    duplicate_names="$(printf '%s\n' "${repository_names[@]}" | sort | uniq -d)"
    [[ -z "$duplicate_names" ]] || fail "repos.yaml: duplicate repository name(s): $duplicate_names"
  fi
fi

if [[ "$errors" -gt 0 ]]; then
  printf 'workspace-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi

printf 'workspace-check: PASS\n'
