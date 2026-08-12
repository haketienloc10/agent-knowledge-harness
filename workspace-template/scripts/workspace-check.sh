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

require_command git
require_command rg
require_command flock

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
  scripts/qiqi-agent-turn.sh
  scripts/qiqi-agent-resume.sh
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

if [[ -f "$workspace_root/AGENTS.md" ]]; then
  rg -q '`identity\.md`' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must route QiQi to identity.md'
  rg -q '`repos\.yaml`' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must route QiQi to repos.yaml'
  rg -q '`SYSTEM_MAP\.md`' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must route QiQi to SYSTEM_MAP.md'
  rg -q '`KNOWLEDGE\.md`' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must route QiQi to KNOWLEDGE.md'
  rg -q '`instructions/model-routing\.md`' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must route QiQi to model routing'
  rg -q '`scripts/qiqi-agent-turn\.sh`' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must route delegated turns through qiqi-agent-turn.sh'
  rg -q '`scripts/qiqi-agent-resume\.sh`' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must route closed-session resume through qiqi-agent-resume.sh'
  rg -q 'QIQI_AGENT_TURN_FINISHED' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: missing turn completion marker'
  rg -q 'QIQI_AGENT_TURN_BUSY' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: missing active-owner behavior'
  rg -qi 'transport backgrounding|Background terminals' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: missing transport-background blocking rule'
  rg -q 'HERDR_ENV=1' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must require HERDR_ENV=1 before session control'
  rg -q '`\.qiqi/tasks/' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must define task-context routing'

  if rg -q 'qiqi-agent-turn\.sh wait' "$workspace_root/AGENTS.md"; then
    fail 'AGENTS.md: turn wrapper must not expose wait mode'
  fi
fi

turn_wrapper="$workspace_root/scripts/qiqi-agent-turn.sh"
if [[ -f "$turn_wrapper" ]]; then
  bash -n "$turn_wrapper" || fail 'qiqi-agent-turn.sh: invalid Bash syntax'
  rg -q 'flock -n' "$turn_wrapper" || \
    fail 'qiqi-agent-turn.sh: missing non-blocking ownership guard'
  rg -q 'prompt must not be empty' "$turn_wrapper" || \
    fail 'qiqi-agent-turn.sh: must reject empty prompts'
  rg -q 'QIQI_AGENT_TURN_BUSY' "$turn_wrapper" || \
    fail 'qiqi-agent-turn.sh: missing busy marker'
  rg -q 'QIQI_AGENT_TURN_FINISHED' "$turn_wrapper" || \
    fail 'qiqi-agent-turn.sh: missing completion marker'
  rg -q 'herdr agent prompt' "$turn_wrapper" || \
    fail 'qiqi-agent-turn.sh: missing prompt command'
  rg -q -- '--wait' "$turn_wrapper" || \
    fail 'qiqi-agent-turn.sh: prompt must synchronously wait for completion'
  rg -q 'Background terminals' "$turn_wrapper" || \
    fail 'qiqi-agent-turn.sh: missing transport-background usage contract'

  if rg -q 'herdr agent wait|prompt \| wait|qiqi-agent-turn\.sh wait' "$turn_wrapper"; then
    fail 'qiqi-agent-turn.sh: wait mode/direct agent wait must not exist'
  fi
fi

resume_wrapper="$workspace_root/scripts/qiqi-agent-resume.sh"
if [[ -f "$resume_wrapper" ]]; then
  bash -n "$resume_wrapper" || fail 'qiqi-agent-resume.sh: invalid Bash syntax'
  rg -q 'flock -n' "$resume_wrapper" || \
    fail 'qiqi-agent-resume.sh: missing non-blocking per-agent lock'
  rg -q 'native resume arguments must not be empty' "$resume_wrapper" || \
    fail 'qiqi-agent-resume.sh: must reject empty resume arguments'
  rg -q 'QIQI_AGENT_RESUME_BUSY' "$resume_wrapper" || \
    fail 'qiqi-agent-resume.sh: missing busy marker'
  rg -q 'QIQI_AGENT_RESUME_FINISHED' "$resume_wrapper" || \
    fail 'qiqi-agent-resume.sh: missing completion marker'
  rg -q 'herdr agent start' "$resume_wrapper" || \
    fail 'qiqi-agent-resume.sh: missing agent start command'
  rg -q -- '--kind' "$resume_wrapper" || \
    fail 'qiqi-agent-resume.sh: missing agent kind forwarding'
  rg -q -- '--pane' "$resume_wrapper" || \
    fail 'qiqi-agent-resume.sh: missing pane forwarding'
fi

if [[ -f "$workspace_root/KNOWLEDGE.md" ]]; then
  rg -q 'knowledge/INDEX\.md' "$workspace_root/KNOWLEDGE.md" || \
    fail 'KNOWLEDGE.md: must route through knowledge/INDEX.md'
  rg -q 'knowledge/proposals/' "$workspace_root/KNOWLEDGE.md" || \
    fail 'KNOWLEDGE.md: must define proposal lifecycle'
  rg -q 'repository con' "$workspace_root/KNOWLEDGE.md" || \
    fail 'KNOWLEDGE.md: must preserve repo-local ownership'
fi

if [[ -f "$workspace_root/instructions/model-routing.md" ]]; then
  rg -q 'Agent kind' "$workspace_root/instructions/model-routing.md" || \
    fail 'model-routing.md: missing agent kind inventory'
  rg -q 'Model ID' "$workspace_root/instructions/model-routing.md" || \
    fail 'model-routing.md: missing exact model ID inventory'
  rg -q 'Native arguments' "$workspace_root/instructions/model-routing.md" || \
    fail 'model-routing.md: missing native arguments'
  rg -q 'Native resume arguments' "$workspace_root/instructions/model-routing.md" || \
    fail 'model-routing.md: missing native resume arguments'
  rg -q 'một active delegated turn' "$workspace_root/instructions/model-routing.md" || \
    fail 'model-routing.md: concurrency metadata must not override serialized QiQi policy'
  for profile in fast balanced deep verifier; do
    rg -q "\`$profile\`" "$workspace_root/instructions/model-routing.md" || \
      fail "model-routing.md: missing $profile profile"
  done
fi

if ! command -v yq >/dev/null 2>&1; then
  fail 'missing required command: yq version 4'
elif ! yq --version 2>&1 | rg -q 'version v?4\.'; then
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
    mapfile -t repository_names < <(
      yq -r '.repositories[].name' "$workspace_root/repos.yaml"
    )
    mapfile -t repository_paths < <(
      yq -r '.repositories[].path' "$workspace_root/repos.yaml"
    )

    for index in "${!repository_names[@]}"; do
      name="${repository_names[$index]}"
      path="${repository_paths[$index]}"

      [[ -n "$name" && "$name" != "null" ]] || \
        fail 'repos.yaml: repository name is empty'
      [[ -n "$path" && "$path" != "null" ]] || \
        fail "repos.yaml: ${name}: path is empty"
      [[ "$path" != /* ]] || \
        fail "repos.yaml: ${name}: path must be relative"
      [[ "$path" != *'..'* ]] || \
        fail "repos.yaml: ${name}: path must not contain .."

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
    [[ -z "$duplicate_names" ]] || \
      fail "repos.yaml: duplicate repository name(s): $duplicate_names"
  fi
fi

if [[ "$errors" -gt 0 ]]; then
  printf 'workspace-check: FAIL (%d error(s))\n' "$errors" >&2
  exit 1
fi

printf 'workspace-check: PASS\n'
