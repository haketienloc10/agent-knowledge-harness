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

for command in git rg uv python3 yq herdr; do
  require_command "$command"
done

required_files=(
  AGENTS.md
  identity.md
  SYSTEM_MAP.md
  repos.yaml
  knowledge/README.md
  knowledge/INDEX.md
  knowledge/glossary.md
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
  .qiqi/tasks/active
  .qiqi/tasks/completed
)

for path in "${required_dirs[@]}"; do
  require_dir "$workspace_root/$path"
done

if [[ -e "$workspace_root/KNOWLEDGE.md" ]]; then
  fail 'KNOWLEDGE.md: duplicate knowledge router is not part of the MVP workflow'
fi
if [[ -e "$workspace_root/knowledge/proposals" ]]; then
  fail 'knowledge/proposals: proposal lifecycle is not part of the MVP workflow'
fi

for legacy_example in \
  instructions/agent-routing.codex.example.yaml \
  instructions/agent-routing.claude-code.example.yaml; do
  if [[ -e "$workspace_root/$legacy_example" ]]; then
    fail "$legacy_example: routing examples belong under docs/examples, not active instructions"
  fi
done

for example in \
  docs/examples/agent-routing.codex.yaml \
  docs/examples/agent-routing.claude-code.yaml; do
  if [[ -f "$workspace_root/$example" ]]; then
    rg -q '^# DOCUMENTATION-ONLY EXAMPLE\.$' "$workspace_root/$example" || \
      fail "$example: missing documentation-only banner"
    rg -q 'qiqi_delegate does NOT load this file' "$workspace_root/$example" || \
      fail "$example: must state that MCP does not load the example"
  fi
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
  rg -n 'codex exec|claude -p|--output-format json|prompt_transport|\{schema_path\}|\{result_path\}|terminal structured result' \
    "${existing_policy_files[@]}"; then
  fail 'legacy non-interactive/inline-result delegation contract found in policy'
fi

agents_md="$workspace_root/AGENTS.md"
if [[ -f "$agents_md" ]]; then
  for pattern in \
    'Chief of Staff' \
    '`identity\.md`' \
    '`repos\.yaml`' \
    '`SYSTEM_MAP\.md`' \
    '`knowledge/README\.md`' \
    '`knowledge/INDEX\.md`' \
    '`instructions/agent-routing\.yaml`' \
    '`instructions/model-routing\.md`' \
    '`delegate_repo_task`' \
    '`session_id`' \
    '`result_path`' \
    '`\.qiqi/runs/' \
    '`\.qiqi/tasks/' \
    '## Workflow Workspace ↔ Repository' \
    '## Delegation Silence' \
    '## Dependency và Delegation Waves'; do
    rg -q "$pattern" "$agents_md" || fail "AGENTS.md: missing required policy: $pattern"
  done
  rg -q 'handoff broker duy nhất giữa các repository' "$agents_md" || \
    fail 'AGENTS.md: QiQi must be the only cross-repo handoff broker'
  rg -U -q 'không yêu cầu execution agent tự mở workspace `knowledge/`.*result[[:space:]]+artifact của repository khác' "$agents_md" || \
    fail 'AGENTS.md: child must receive workspace/upstream context through the QiQi prompt'
  rg -U -q 'producer `result_path`.*consumer task prompt|producer result.*consumer task prompt' "$agents_md" || \
    fail 'AGENTS.md: producer result must flow through QiQi into the consumer prompt'
  rg -U -q 'knowledge/INDEX\.md.*trong cùng[[:space:]]+thay đổi' "$agents_md" || \
    fail 'AGENTS.md: durable workspace knowledge must update INDEX.md in the same change'
  rg -q 'đọc.*`result_path`|đọc.*result artifact' "$agents_md" || \
    fail 'AGENTS.md: QiQi must read result_path before deciding the next step'
  rg -q 'không.*RESUME.*report|không.*RESUME.*báo cáo' "$agents_md" || \
    fail 'AGENTS.md: missing no-report-only RESUME invariant'
  rg -q 'prompt.*QiQi|QiQi.*prompt' "$agents_md" || \
    fail 'AGENTS.md: missing QiQi-owned task prompt invariant'
  rg -U -q 'progress[[:space:]]+commentary' "$agents_md" || \
    fail 'AGENTS.md: missing delegation-silence communication invariant'
  rg -q 'Trong cùng `qiqi_delegate` server process' "$agents_md" || \
    fail 'AGENTS.md: conflict guard must be scoped to one qiqi_delegate server process'
  rg -U -q 'cùng[[:space:]]+resolved Git root hoặc cùng native `session_id`' "$agents_md" || \
    fail 'AGENTS.md: missing repo/session conflict invariant'
  rg -q 'poll `status`, process, PID, transcript hoặc session state' "$agents_md" || \
    fail 'AGENTS.md: missing no-polling child-state invariant'
  rg -q 'QiQi không trực tiếp gọi `codex`, `claude` hoặc coding-agent CLI khác' "$agents_md" || \
    fail 'AGENTS.md: missing direct-agent-CLI bypass prohibition'
  rg -U -q 'Không[[:space:]]+fallback sang shell-based `codex`, `claude`' "$agents_md" || \
    fail 'AGENTS.md: missing MCP-failure shell fallback prohibition'
fi

knowledge_readme="$workspace_root/knowledge/README.md"
if [[ -f "$knowledge_readme" ]]; then
  rg -q '^# Workspace Knowledge$' "$knowledge_readme" || \
    fail 'knowledge/README.md: missing workspace knowledge guide title'
  rg -q '`INDEX\.md`' "$knowledge_readme" || \
    fail 'knowledge/README.md: must route reads through INDEX.md'
  rg -U -q 'Execution agent.*không tự đọc thư mục này' "$knowledge_readme" || \
    fail 'knowledge/README.md: child must not read workspace knowledge directly'
  rg -U -q 'cập nhật[[:space:]]+`INDEX\.md` trong cùng thay đổi' "$knowledge_readme" || \
    fail 'knowledge/README.md: knowledge writes must update INDEX.md atomically'
fi

knowledge_index="$workspace_root/knowledge/INDEX.md"
if [[ -f "$knowledge_index" ]]; then
  rg -q '^# Knowledge Index$' "$knowledge_index" || \
    fail 'knowledge/INDEX.md: missing index title'
  rg -q --fixed-strings '| Tài liệu | Summary | Khi nào cần đọc | Phạm vi |' "$knowledge_index" || \
    fail 'knowledge/INDEX.md: missing MVP read-routing columns'
  rg -q 'không quét toàn bộ `knowledge/`' "$knowledge_index" || \
    fail 'knowledge/INDEX.md: must prevent scanning the whole knowledge library'
fi

task_template="$workspace_root/.qiqi/tasks/TEMPLATE.md"
if [[ -f "$task_template" ]]; then
  rg -q '^## Handoff liên repository$' "$task_template" || \
    fail '.qiqi/tasks/TEMPLATE.md: missing cross-repo handoff section'
  rg -U -q 'Không yêu cầu downstream agent tự đọc result artifact hoặc workspace knowledge' "$task_template" || \
    fail '.qiqi/tasks/TEMPLATE.md: downstream context must be brokered by QiQi'
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
    'RUNS_DIR' \
    'HERDR_BIN' \
    'HERDR_SESSION' \
    '_state_lock = asyncio\.Lock' \
    '_active_repositories' \
    '_active_sessions' \
    'def _claim_resources' \
    'def _release_resources' \
    'repository already has an active delegation' \
    'native session already has an active delegation' \
    'def _ensure_herdr_server' \
    'def _require_current_integration' \
    'def _create_herdr_workspace' \
    'def _start_interactive_agent' \
    'def _prompt_and_wait' \
    'agent_prompt_stalled' \
    'send-keys' \
    'def _wait_for_native_session' \
    'def _validate_result_section' \
    'QiQi MCP result handoff protocol' \
    'def delegate_repo_task' \
    'route: str' \
    'session_id: str \| None' \
    'resume identity mismatch' \
    '"result_path"'; do
    rg -q "$pattern" "$server" || fail "qiqi_delegate/server.py: missing contract: $pattern"
  done

  for forbidden in \
    '_repo_locks' \
    'RESULT_SCHEMA' \
    '_parse_codex_result' \
    '_parse_claude_result' \
    'prompt_transport' \
    'stdout\.log' \
    'result\.schema\.json'; do
    if rg -q "$forbidden" "$server"; then
      fail "qiqi_delegate/server.py: legacy contract found: $forbidden"
    fi
  done

  if rg -q 'FastMCP|mcp\.server\.fastmcp' "$server"; then
    fail 'qiqi_delegate/server.py: legacy MCP SDK v1 API found; use MCPServer from MCP SDK v2'
  fi

  if rg -q 'def (status|wait|read_transcript|resume|list_runs)\b' "$server"; then
    fail 'qiqi_delegate/server.py: separate progress/session tool must not exist'
  fi

  tool_count="$(rg -c '^@mcp\.tool\(\)$' "$server" || true)"
  [[ "$tool_count" == "1" ]] || \
    fail "qiqi_delegate/server.py: expected exactly one public MCP tool, found $tool_count"

  if ! uv run --project "$mcp_project" python -c \
    'from mcp.server import MCPServer; import yaml; print("qiqi-mcp-runtime: PASS")' \
    >/dev/null; then
    fail 'qiqi_delegate: MCP SDK runtime import failed; run uv sync --project mcp/qiqi_delegate'
  fi
fi

if ! yq --version 2>&1 | rg -q 'version v?4\.'; then
  fail 'unsupported yq version; install yq version 4'
else
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

  if rg -n '^\s*-\s+(exec|-p|--json|--ignore-user-config|--output-schema|--output-last-message|--output-format|--dangerously-bypass-hook-trust)\s*$' "$routing"; then
    fail 'agent-routing.yaml: legacy/non-interactive execution flag found'
  fi
  if rg -q 'prompt_transport|prompt_arg|\{schema_path\}|\{result_path\}' "$routing"; then
    fail 'agent-routing.yaml: legacy prompt/result placeholder found'
  fi

  integration_status="$(herdr integration status 2>&1 || true)"
  mapfile -t agent_names < <(yq -r '.agents | keys | .[]' "$routing" 2>/dev/null || true)
  checked_adapters=()
  for agent_name in "${agent_names[@]}"; do
    command_name="$(AGENT_NAME="$agent_name" yq -r '.agents[env(AGENT_NAME)].command' "$routing")"
    adapter="$(AGENT_NAME="$agent_name" yq -r '.agents[env(AGENT_NAME)].adapter' "$routing")"

    [[ -n "$command_name" && "$command_name" != "null" ]] || \
      fail "agent-routing.yaml: ${agent_name}: missing command"
    [[ "$adapter" == "codex" || "$adapter" == "claude" ]] || \
      fail "agent-routing.yaml: ${agent_name}: adapter must be codex or claude"

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
    if AGENT_NAME="$agent_name" yq -r \
      '.agents[env(AGENT_NAME)].start_args[]' "$routing" | rg -q '\{session_id\}'; then
      fail "agent-routing.yaml: ${agent_name}: start_args must not contain {session_id}"
    fi
    if ! AGENT_NAME="$agent_name" yq -r \
      '.agents[env(AGENT_NAME)].resume_args[]' "$routing" | rg -q '\{session_id\}'; then
      fail "agent-routing.yaml: ${agent_name}: resume_args missing {session_id}"
    fi

    if ! command -v "$command_name" >/dev/null 2>&1; then
      fail "agent-routing.yaml: ${agent_name}: missing command: $command_name"
      continue
    fi

    help_text="$($command_name --help 2>&1 || true)"
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

    if ! printf '%s\n' "${checked_adapters[@]:-}" | rg -qx -- "$adapter"; then
      checked_adapters+=("$adapter")
      if ! printf '%s\n' "$integration_status" | rg -q "^${adapter}: current\\b"; then
        fail "Herdr integration is not current for configured adapter: $adapter"
      fi
    fi
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
    if ! command -v "$route_command_name" >/dev/null 2>&1; then
      continue
    fi
    route_help_text="$($route_command_name --help 2>&1 || true)"
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
  rg -q 'chọn exact `route`|exact route' "$model_routing" || \
    fail 'model-routing.md: must define exact-route selection policy'
  rg -q '`instructions/agent-routing\.yaml`|`agent-routing\.yaml`' "$model_routing" || \
    fail 'model-routing.md: must identify agent-routing.yaml as runtime source of truth'
  rg -q 'không truyền profile name' "$model_routing" || \
    fail 'model-routing.md: must reject profile-name transport'
  for route in claude-haiku claude-balanced claude-deep claude-verifier codex-balanced; do
    rg -q "\`$route\`" "$model_routing" || \
      fail "model-routing.md: missing route-selection guidance for $route"
  done
  if rg -q '(^|[^a-zA-Z])Profile([^a-zA-Z]|$)|\{model\}|\{session_id\}|\{result_dir\}|\{route_args\}|--permission-mode|--effort|model_reasoning_effort|prompt_transport|schema_path|codex exec|claude -p' "$model_routing"; then
    fail 'model-routing.md: runtime/profile details leaked into route-selection policy'
  fi
fi

if [[ "$errors" -gt 0 ]]; then
  printf 'workspace-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi

printf 'workspace-check: PASS\n'
