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
  instructions/agent-routing.yaml
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
  "$workspace_root/instructions/agent-routing.yaml"
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

agents_md="$workspace_root/AGENTS.md"
if [[ -f "$agents_md" ]]; then
  for pattern in \
    'Chief of Staff' \
    '`identity\.md`' \
    '`repos\.yaml`' \
    '`SYSTEM_MAP\.md`' \
    '`KNOWLEDGE\.md`' \
    '`instructions/agent-routing\.yaml`' \
    '`instructions/model-routing\.md`' \
    '`scripts/qiqi-mcp-server\.sh`' \
    '`delegate_repo_task`' \
    '`session_id`' \
    '`\.qiqi/tasks/' \
    '## Delegation Silence' \
    '## Dependency và Delegation Waves'; do
    rg -q "$pattern" "$agents_md" || fail "AGENTS.md: missing required policy: $pattern"
  done
  rg -q 'progress commentary' "$agents_md" || \
    fail 'AGENTS.md: missing delegation-silence communication invariant'
  rg -q 'cùng resolved Git root hoặc cùng native `session_id`' "$agents_md" || \
    fail 'AGENTS.md: missing repo/session conflict invariant'
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

mcp_project="$workspace_root/mcp/qiqi_delegate"
server="$mcp_project/server.py"
if [[ -f "$server" ]]; then
  python3 - "$server" <<'PY' || fail 'qiqi_delegate/server.py: invalid Python syntax'
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
compile(path.read_text(encoding="utf-8"), str(path), "exec")
PY

  for pattern in \
    'MCPServer' \
    '_state_lock = asyncio\.Lock' \
    '_active_repositories' \
    '_active_sessions' \
    'def _claim_resources' \
    'def _release_resources' \
    'repository already has an active delegation' \
    'native session already has an active delegation' \
    'agent-routing\.yaml' \
    'def delegate_repo_task' \
    'route: str' \
    'session_id: str \| None' \
    '_parse_codex_result' \
    '_parse_claude_result' \
    'resume identity mismatch' \
    'transcript|stdout\.log'; do
    rg -q "$pattern" "$server" || fail "qiqi_delegate/server.py: missing contract: $pattern"
  done

  if rg -q '_delegate_lock' "$server"; then
    fail 'qiqi_delegate/server.py: legacy global delegation lock found; concurrency must be repo/session scoped'
  fi

  if rg -q 'FastMCP|mcp\.server\.fastmcp' "$server"; then
    fail 'qiqi_delegate/server.py: legacy MCP SDK v1 API found; use MCPServer from MCP SDK v2'
  fi

  if rg -q 'def (status|wait|read_transcript|resume|list_runs)\b' "$server"; then
    fail 'qiqi_delegate/server.py: separate progress/session tool must not exist'
  fi

  if ! uv run --project "$mcp_project" python -c \
    'from mcp.server import MCPServer; import yaml; print("qiqi-mcp-runtime: PASS")' \
    >/dev/null; then
    fail 'qiqi_delegate: MCP SDK runtime import failed; run uv sync --project mcp/qiqi_delegate'
  fi
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
    repository_git_roots=()

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
      repository_git_roots+=("$git_root")
    done

    duplicate_names="$(printf '%s\n' "${repository_names[@]}" | sort | uniq -d)"
    [[ -z "$duplicate_names" ]] || fail "repos.yaml: duplicate repository name(s): $duplicate_names"

    duplicate_git_roots="$(printf '%s\n' "${repository_git_roots[@]}" | sort | uniq -d)"
    [[ -z "$duplicate_git_roots" ]] || \
      fail "repos.yaml: multiple entries resolve to the same Git root(s): $duplicate_git_roots"
  fi

  routing="$workspace_root/instructions/agent-routing.yaml"
  if ! yq -e '.version == 1' "$routing" >/dev/null; then
    fail 'agent-routing.yaml: version must be 1'
  fi
  if ! yq -e '.agents | type == "!!map" and length > 0' "$routing" >/dev/null; then
    fail 'agent-routing.yaml: agents must be a non-empty map'
  fi
  if ! yq -e '.routes | type == "!!map" and length > 0' "$routing" >/dev/null; then
    fail 'agent-routing.yaml: routes must be a non-empty map'
  fi

  mapfile -t agent_names < <(yq -r '.agents | keys | .[]' "$routing" 2>/dev/null || true)
  for agent_name in "${agent_names[@]}"; do
    command_name="$(AGENT_NAME="$agent_name" yq -r '.agents[env(AGENT_NAME)].command' "$routing")"
    adapter="$(AGENT_NAME="$agent_name" yq -r '.agents[env(AGENT_NAME)].adapter' "$routing")"
    transport="$(AGENT_NAME="$agent_name" yq -r '.agents[env(AGENT_NAME)].prompt_transport' "$routing")"

    [[ -n "$command_name" && "$command_name" != "null" ]] || \
      fail "agent-routing.yaml: ${agent_name}: missing command"
    [[ "$adapter" == "codex" || "$adapter" == "claude" ]] || \
      fail "agent-routing.yaml: ${agent_name}: adapter must be codex or claude"
    [[ "$transport" == "stdin" || "$transport" == "argument" ]] || \
      fail "agent-routing.yaml: ${agent_name}: invalid prompt_transport"

    if ! AGENT_NAME="$agent_name" yq -e \
      '.agents[env(AGENT_NAME)].start_args | type == "!!seq" and length > 0' \
      "$routing" >/dev/null; then
      fail "agent-routing.yaml: ${agent_name}: start_args must be non-empty"
    fi
    if ! AGENT_NAME="$agent_name" yq -e \
      '.agents[env(AGENT_NAME)].resume_args | type == "!!seq" and length > 0' \
      "$routing" >/dev/null; then
      fail "agent-routing.yaml: ${agent_name}: resume_args must be non-empty"
    fi
    if ! AGENT_NAME="$agent_name" yq -r \
      '.agents[env(AGENT_NAME)].resume_args[]' "$routing" | rg -q '\{session_id\}'; then
      fail "agent-routing.yaml: ${agent_name}: resume_args missing {session_id}"
    fi

    if ! command -v "$command_name" >/dev/null 2>&1; then
      fail "agent-routing.yaml: ${agent_name}: missing command: $command_name"
      continue
    fi

    if [[ "$adapter" == "codex" ]]; then
      help_text="$($command_name exec --help 2>&1 || true)"
    else
      help_text="$($command_name --help 2>&1 || true)"
    fi

    mapfile -t configured_flags < <(
      AGENT_NAME="$agent_name" yq -r \
        '(.agents[env(AGENT_NAME)].start_args[], .agents[env(AGENT_NAME)].resume_args[]) | select(test("^--"))' \
        "$routing" | sort -u
    )
    for flag in "${configured_flags[@]}"; do
      if ! printf '%s\n' "$help_text" | rg -q --fixed-strings -- "$flag"; then
        fail "agent-routing.yaml: ${agent_name}: installed CLI help does not advertise configured flag: $flag"
      fi
    done
  done

  mapfile -t route_names < <(yq -r '.routes | keys | .[]' "$routing" 2>/dev/null || true)
  for route_name in "${route_names[@]}"; do
    route_agent="$(ROUTE_NAME="$route_name" yq -r '.routes[env(ROUTE_NAME)].agent' "$routing")"
    route_model="$(ROUTE_NAME="$route_name" yq -r '.routes[env(ROUTE_NAME)].model' "$routing")"

    if ! AGENT_NAME="$route_agent" yq -e '.agents | has(env(AGENT_NAME))' "$routing" >/dev/null; then
      fail "agent-routing.yaml: ${route_name}: unknown agent: $route_agent"
      continue
    fi
    [[ -n "$route_model" && "$route_model" != "null" ]] || \
      fail "agent-routing.yaml: ${route_name}: model must be non-empty"
    if ! ROUTE_NAME="$route_name" yq -e \
      '.routes[env(ROUTE_NAME)].args | type == "!!seq"' "$routing" >/dev/null; then
      fail "agent-routing.yaml: ${route_name}: args must be a list"
      continue
    fi

    route_arg_count="$(ROUTE_NAME="$route_name" yq -r '.routes[env(ROUTE_NAME)].args | length' "$routing")"
    if [[ "$route_arg_count" -gt 0 ]]; then
      for lifecycle in start_args resume_args; do
        if ! AGENT_NAME="$route_agent" LIFECYCLE="$lifecycle" yq -r \
          '.agents[env(AGENT_NAME)][env(LIFECYCLE)][]' "$routing" | rg -qx '\{route_args\}'; then
          fail "agent-routing.yaml: ${route_name}: ${route_agent}.${lifecycle} missing {route_args}"
        fi
      done
    fi

    route_command_name="$(AGENT_NAME="$route_agent" yq -r '.agents[env(AGENT_NAME)].command' "$routing")"
    route_adapter="$(AGENT_NAME="$route_agent" yq -r '.agents[env(AGENT_NAME)].adapter' "$routing")"
    if ! command -v "$route_command_name" >/dev/null 2>&1; then
      continue
    fi

    if [[ "$route_adapter" == "codex" ]]; then
      route_help_text="$($route_command_name exec --help 2>&1 || true)"
    else
      route_help_text="$($route_command_name --help 2>&1 || true)"
    fi

    mapfile -t route_flags < <(
      ROUTE_NAME="$route_name" yq -r \
        '.routes[env(ROUTE_NAME)].args[] | select(test("^--"))' \
        "$routing" | sort -u
    )
    for flag in "${route_flags[@]}"; do
      if ! printf '%s\n' "$route_help_text" | rg -q --fixed-strings -- "$flag"; then
        fail "agent-routing.yaml: ${route_name}: installed ${route_agent} CLI help does not advertise route flag: $flag"
      fi
    done
  done
fi

model_routing="$workspace_root/instructions/model-routing.md"
if [[ -f "$model_routing" ]]; then
  rg -q 'Route' "$model_routing" || fail 'model-routing.md: missing Route column'
  for profile in fast balanced deep verifier; do
    rg -q "\`$profile\`" "$model_routing" || fail "model-routing.md: missing $profile profile"
  done
  if rg -q 'one active|một active|single-flight' "$model_routing"; then
    fail 'model-routing.md: legacy global single-flight policy found'
  fi
fi

if [[ "$errors" -gt 0 ]]; then
  printf 'workspace-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi

printf 'workspace-check: PASS\n'
