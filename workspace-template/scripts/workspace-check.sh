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

for command in git rg uv python3 yq herdr; do
  require_command "$command"
done

required_files=(
  AGENTS.md
  identity.md
  README.md
  SYSTEM_MAP.md
  repos.yaml
  instructions/agent-routing.yaml
  instructions/model-routing.md
  .agents/skills/ticket-work-item/SKILL.md
  .codex/config.toml
  .qiqi/.gitignore
  mcp/qiqi_delegate/pyproject.toml
  mcp/qiqi_delegate/core.py
  mcp/qiqi_delegate/result_hook.py
  mcp/qiqi_delegate/server.py
  mcp/qiqi_delegate/tests/test_core.py
  mcp/qiqi_delegate/tests/test_result_hook.py
  scripts/qiqi-mcp-server.sh
  scripts/workspace-check.sh
  docs/WORKSPACE_SETUP.md
)
for path in "${required_files[@]}"; do
  require_file "$workspace_root/$path"
done

managed_files=(
  "$workspace_root/repos.yaml"
  "$workspace_root/SYSTEM_MAP.md"
  "$workspace_root/instructions/agent-routing.yaml"
  "$workspace_root/instructions/model-routing.md"
)
if rg -n '\{\{[^}]+\}\}' "${managed_files[@]}"; then
  fail 'unresolved workspace template placeholder(s) found'
fi

policy_files=(
  "$workspace_root/AGENTS.md"
  "$workspace_root/identity.md"
  "$workspace_root/README.md"
  "$workspace_root/docs/WORKSPACE_SETUP.md"
  "$workspace_root/instructions/model-routing.md"
)
if rg -n 'result_path|QiQi MCP result handoff protocol|### Outcome|### Repo-local Knowledge' "${policy_files[@]}"; then
  fail 'legacy Markdown result-handoff contract found in active workspace policy'
fi

agents_md="$workspace_root/AGENTS.md"
for pattern in \
  'Chief of Staff' \
  'Global Work Item MCP' \
  'work_item_get' \
  'work_item_update' \
  'expected_revision' \
  'canonical Work Item' \
  'Current snapshot và material history' \
  'current effective repo truth' \
  'accumulated material phase/milestone history' \
  'Artifact creation không được tính là thay thế' \
  'Implementation:.*không tạo artifact' \
  'Review code\.\.\.' \
  'Report:.*presentation/detail' \
  '`delegate_repo_task`' \
  '`user_request`' \
  '`required_context`' \
  '`acceptance_criteria`' \
  'Closed-world context rule' \
  '`agent_response`' \
  'native Stop hook' \
  '`\.qiqi/state/qiqi_delegate\.sqlite3`' \
  'orchestration/synchronization broker' \
  '## Delegation Silence'; do
  rg -U -q "$pattern" "$agents_md" || fail "AGENTS.md: missing required policy: $pattern"
done

for pattern in \
  'current_requirements' \
  'questions' \
  'decisions' \
  'changes' \
  'handoffs' \
  'next_actions' \
  'superseded_by' \
  'revision conflict'; do
  rg -q "$pattern" "$agents_md" || fail "AGENTS.md: missing Work Item continuity rule: $pattern"
done

rg -U -q 'native response established material repo state.*latest Work Item thiếu.*không silently tiếp tục' "$agents_md" || \
  fail 'AGENTS.md: QiQi must detect missing repo persistence after material delegation'

# CRITICAL INVARIANT — DO NOT REMOVE OR WEAKEN THIS CHECK merely to make a
# migration/check pass. Delegation silence is part of the synchronous execution
# contract. Change this expected block only when the contract is intentionally
# changed and reviewed together with qiqi_delegate semantics.
delegation_silence_expected="$(cat <<'EOF'
## Delegation Silence

Trong khi `delegate_repo_task` đang chạy đồng bộ, QiQi không poll process/pane/session, không đọc `.qiqi/state/`, không scrape terminal và không phát user-facing progress dựa trên hidden child runtime. Chờ tool terminal return; sau đó reconcile structured state + native response. Nếu tool fail/blocked, xử lý theo exact returned contract, không tự mở runtime internals để đoán tiến độ hoặc kết quả.
EOF
)"
delegation_silence_actual="$(python3 - "$agents_md" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
heading = "## Delegation Silence\n"
start = text.find(heading)
if start < 0:
    print("")
    raise SystemExit(0)
next_heading = text.find("\n## ", start + len(heading))
section = text[start:] if next_heading < 0 else text[start:next_heading]
print(section.rstrip("\n"))
PY
)"
if [[ "$delegation_silence_actual" != "$delegation_silence_expected" ]]; then
  fail 'AGENTS.md: Delegation Silence must match the exact synchronous no-progress contract; do not weaken/remove this invariant check'
fi

if rg -q 'English task title|read `result_path`|đọc `result_path`' "$agents_md"; then
  fail 'AGENTS.md: legacy workspace result artifact convention remains'
fi

skill="$workspace_root/.agents/skills/ticket-work-item/SKILL.md"
if [[ -f "$skill" ]]; then
  for pattern in \
    '^name: ticket-work-item$' \
    'Use only when the user explicitly invokes' \
    'Do not auto-apply merely because' \
    '\$ticket-work-item path/to/ticket\.md' \
    'Resolve relative paths from the current workspace directory' \
    'work_item_get' \
    'expected_revision' \
    'delegate_repo_task' \
    '^## Material session reconciliation$' \
    'Artifact creation never substitutes' \
    'Implementation:.*no artifact|Implementation:.*không' \
    'Review code\.\.\.' \
    'Report:.*presentation/detail' \
    'knowledge_search → knowledge_read → knowledge_write'; do
    rg -U -q "$pattern" "$skill" || fail "ticket-work-item skill: missing contract: $pattern"
  done
fi

codex_config="$workspace_root/.codex/config.toml"
rg -q '^\[mcp_servers\.qiqi_delegate\]$' "$codex_config" || \
  fail '.codex/config.toml: missing qiqi_delegate MCP server'
rg -q 'enabled_tools = \["delegate_repo_task"\]' "$codex_config" || \
  fail '.codex/config.toml: MCP must expose only delegate_repo_task'
rg -q 'tool_timeout_sec = 7200' "$codex_config" || \
  fail '.codex/config.toml: expected long synchronous tool timeout'
rg -q 'required = true' "$codex_config" || \
  fail '.codex/config.toml: qiqi_delegate must be required'
if rg -q '^\[mcp_servers\.(work_item|knowledge)\]' "$codex_config"; then
  fail '.codex/config.toml: work_item and knowledge must remain user-scoped, not project-scoped'
fi

launcher="$workspace_root/scripts/qiqi-mcp-server.sh"
bash -n "$launcher" || fail 'qiqi-mcp-server.sh: invalid Bash syntax'
rg -q 'uv run --project' "$launcher" || \
  fail 'qiqi-mcp-server.sh: must launch MCP through uv project'
rg -q 'QIQI_WORKSPACE_ROOT' "$launcher" || \
  fail 'qiqi-mcp-server.sh: must pass workspace root to MCP server'

mcp_project="$workspace_root/mcp/qiqi_delegate"
core="$mcp_project/core.py"
hook="$mcp_project/result_hook.py"
server="$mcp_project/server.py"
for py in "$core" "$hook" "$server"; do
  python3 - "$py" <<'PY' || fail "${py#$workspace_root/}: invalid Python syntax"
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
compile(path.read_text(encoding="utf-8"), str(path), "exec")
PY
done

for pattern in \
  'TASK_PACKET_MAX_CHARS = 100_000' \
  'class TaskPacket' \
  'class ContextFact' \
  'def build_task_packet' \
  'def render_task_prompt' \
  'You do not share QiQi' \
  'Do not invent an omitted external fact' \
  'there are no required result headings' \
  'def normalize_hook_payload' \
  'last_assistant_message' \
  'class SessionStore' \
  'CREATE TABLE IF NOT EXISTS sessions' \
  'CREATE TABLE IF NOT EXISTS turns'; do
  rg -q "$pattern" "$core" || fail "qiqi_delegate/core.py: missing contract: $pattern"
done
if rg -q 'AGENT_RESPONSE_MAX|TASK_TEXT_MAX|TASK_ITEM_MAX|TASK_LIST_MAX' "$core"; then
  fail 'qiqi_delegate/core.py: guessed per-field/native-response limits are forbidden'
fi

for pattern in \
  'json\.load\(sys\.stdin\)' \
  'def _load_active_capture' \
  'active-captures' \
  'expected_session_id' \
  'os\.fsync' \
  'os\.replace' \
  'os\.chmod\(temp, 0o600\)'; do
  rg -q "$pattern" "$hook" || fail "qiqi_delegate/result_hook.py: missing contract: $pattern"
done

for pattern in \
  'MCPServer' \
  'STATE_DB' \
  'ACTIVE_CAPTURES_DIR' \
  'LEGACY_RUNS_DIR' \
  'RESULT_HOOK_PATH' \
  'SessionStore' \
  'def _build_handoff_args' \
  'def _register_active_capture' \
  'expected_session_id' \
  'def _wait_for_result_capture' \
  'refusing to fall back to terminal screen or transcript parsing' \
  'user_request: str' \
  'required_context: list\[dict\[str, str\]\]' \
  'acceptance_criteria: list\[str\]' \
  '"agent_response": response' \
  'def delegate_repo_task'; do
  rg -q "$pattern" "$server" || fail "qiqi_delegate/server.py: missing contract: $pattern"
done

bypass_count="$(rg -o --fixed-strings -- '--dangerously-bypass-hook-trust' "$server" | wc -l | tr -d ' ')"
[[ "$bypass_count" == "1" ]] || \
  fail "qiqi_delegate/server.py: hook-trust bypass must appear only in route-arg rejection policy, found $bypass_count occurrences"
if rg -q '"--sink"|"--nonce"' "$server"; then
  fail 'qiqi_delegate/server.py: native hook command must be static; sink/nonce belong in active-capture state'
fi

for forbidden in \
  'REQUIRED_RESULT_HEADINGS' \
  '_validate_result_section' \
  '_append_task_section' \
  'QiQi MCP result handoff protocol' \
  '"result_path"'; do
  if rg -q "$forbidden" "$server"; then
    fail "qiqi_delegate/server.py: legacy result transport found: $forbidden"
  fi
done
if rg -q 'FastMCP|mcp\.server\.fastmcp' "$server"; then
  fail 'qiqi_delegate/server.py: legacy MCP SDK v1 API found'
fi
tool_count="$(rg -c '^@mcp\.tool\(\)$' "$server" || true)"
[[ "$tool_count" == "1" ]] || \
  fail "qiqi_delegate/server.py: expected exactly one public MCP tool, found $tool_count"

python3 -m unittest discover -s "$mcp_project/tests" -v || \
  fail 'qiqi_delegate: unit tests failed'

if ! uv run --project "$mcp_project" python -c \
  'from mcp.server import MCPServer; import yaml; print("qiqi-mcp-runtime: PASS")' \
  >/dev/null; then
  fail 'qiqi_delegate: MCP SDK runtime import failed; run uv sync --project mcp/qiqi_delegate'
fi

routing="$workspace_root/instructions/agent-routing.yaml"
if ! yq --version 2>&1 | rg -q 'version v?4\.'; then
  fail 'unsupported yq version; install yq version 4'
else
  yq -e '.version == 2' "$routing" >/dev/null || fail 'agent-routing.yaml: version must be 2'
  yq -e '.agents | type == "!!map" and length > 0' "$routing" >/dev/null || fail 'agent-routing.yaml: agents must be a non-empty map'
  yq -e '.routes | type == "!!map" and length > 0' "$routing" >/dev/null || fail 'agent-routing.yaml: routes must be a non-empty map'
fi

if ! uv run --project "$mcp_project" python - "$routing" <<'PY'; then
import pathlib
import sys
import yaml
path = pathlib.Path(sys.argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
assert data.get("version") == 2
agents = data.get("agents")
routes = data.get("routes")
assert isinstance(agents, dict) and agents
assert isinstance(routes, dict) and routes
for name, agent in agents.items():
    for key in ("start_args", "resume_args"):
        values = agent.get(key)
        assert isinstance(values, list), f"{name}.{key} must be a list"
        assert values.count("{handoff_args}") == 1, f"{name}.{key}: exactly one handoff slot required"
    assert "{session_id}" not in agent["start_args"]
    assert "{session_id}" in agent["resume_args"]
    assert all("{result_dir}" not in value for key in ("start_args", "resume_args") for value in agent[key])
for name, route in routes.items():
    assert route.get("agent") in agents, f"{name}: unknown agent"
    args = route.get("args", [])
    assert isinstance(args, list)
    assert not any(value in {"--settings", "--dangerously-bypass-hook-trust", "--enable", "--disable"} or value.startswith("hooks.") for value in args), f"{name}: handoff config must be MCP-owned"
PY
  fail 'agent-routing.yaml: structured native-handoff validation failed'
fi

if rg -q '\{result_dir\}|result_path|prompt_transport|result\.schema\.json' "$routing"; then
  fail 'agent-routing.yaml: legacy result transport placeholder/config found'
fi

rg -q '^state/$' "$workspace_root/.qiqi/.gitignore" || fail '.qiqi/.gitignore: state/ must be ignored'
rg -q '^runs/$' "$workspace_root/.qiqi/.gitignore" || fail '.qiqi/.gitignore: legacy runs/ path must remain ignored'

if yq -e '.repositories | type == "!!seq" and length > 0' "$workspace_root/repos.yaml" >/dev/null 2>&1; then
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
    [[ "$git_root" == "$module_root" ]] || fail "repos.yaml: ${name}: path must be exact Git root: $path"
    repository_git_roots+=("$git_root")
  done
  duplicate_names="$(printf '%s\n' "${repository_names[@]}" | sort | uniq -d)"
  [[ -z "$duplicate_names" ]] || fail "repos.yaml: duplicate repository name(s): $duplicate_names"
  duplicate_roots="$(printf '%s\n' "${repository_git_roots[@]}" | sort | uniq -d)"
  [[ -z "$duplicate_roots" ]] || fail "repos.yaml: multiple entries resolve to same Git root(s): $duplicate_roots"
else
  fail 'repos.yaml: repositories must be a non-empty list'
fi

integration_status="$(herdr integration status 2>&1 || true)"
mapfile -t adapters < <(yq -r '.agents[].adapter' "$routing" 2>/dev/null | sort -u)
for adapter in "${adapters[@]}"; do
  rg -q "^${adapter}: current\\b" <<<"$integration_status" || fail "Herdr ${adapter} integration is not current"
done

if ((errors > 0)); then
  printf '\nworkspace-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi
printf 'workspace-check: PASS\n'
