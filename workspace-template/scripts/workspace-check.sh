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
  .agents/skills/herdr/SKILL.md
  .agents/skills/herdr/LICENSE.txt
  .agents/skills/herdr/SOURCE.md
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
  rg -q '`\.agents/skills/herdr/SKILL\.md`' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must route QiQi to the Herdr skill'
  rg -q 'HERDR_ENV=1' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must require HERDR_ENV=1 before Herdr control'
  rg -q '`\.qiqi/tasks/' "$workspace_root/AGENTS.md" || \
    fail 'AGENTS.md: must define task-context routing'
fi

if [[ -f "$workspace_root/KNOWLEDGE.md" ]]; then
  rg -q 'knowledge/INDEX\.md' "$workspace_root/KNOWLEDGE.md" || \
    fail 'KNOWLEDGE.md: must route through knowledge/INDEX.md'
  rg -q 'knowledge/proposals/' "$workspace_root/KNOWLEDGE.md" || \
    fail 'KNOWLEDGE.md: must define proposal lifecycle'
  rg -q 'repository con' "$workspace_root/KNOWLEDGE.md" || \
    fail 'KNOWLEDGE.md: must preserve repo-local ownership'
fi

herdr_skill="$workspace_root/.agents/skills/herdr/SKILL.md"
herdr_license="$workspace_root/.agents/skills/herdr/LICENSE.txt"
herdr_source="$workspace_root/.agents/skills/herdr/SOURCE.md"

if [[ -f "$herdr_skill" ]]; then
  rg -q '^---$' "$herdr_skill" || \
    fail '.agents/skills/herdr/SKILL.md: missing YAML frontmatter'
  rg -q '^name:[[:space:]]+herdr$' "$herdr_skill" || \
    fail '.agents/skills/herdr/SKILL.md: frontmatter name must be herdr'
  rg -q 'HERDR_ENV=1' "$herdr_skill" || \
    fail '.agents/skills/herdr/SKILL.md: must require HERDR_ENV=1'
fi

if [[ -f "$herdr_license" ]]; then
  rg -q 'Apache License' "$herdr_license" || \
    fail '.agents/skills/herdr/LICENSE.txt: expected Apache License text'
  rg -q 'Version 2\.0' "$herdr_license" || \
    fail '.agents/skills/herdr/LICENSE.txt: expected Version 2.0'
fi

if [[ -f "$herdr_source" ]]; then
  rg -q 'https://github\.com/ogulcancelik/herdr' "$herdr_source" || \
    fail '.agents/skills/herdr/SOURCE.md: missing upstream repository'
  rg -q 'Upstream commit' "$herdr_source" || \
    fail '.agents/skills/herdr/SOURCE.md: missing pinned upstream commit'
  rg -q 'Local modifications' "$herdr_source" || \
    fail '.agents/skills/herdr/SOURCE.md: missing modification status'
fi

if [[ -f "$workspace_root/instructions/model-routing.md" ]]; then
  rg -q 'Agent kind' "$workspace_root/instructions/model-routing.md" || \
    fail 'model-routing.md: missing agent kind inventory'
  rg -q 'Model ID' "$workspace_root/instructions/model-routing.md" || \
    fail 'model-routing.md: missing exact model ID inventory'
  rg -q 'Native arguments' "$workspace_root/instructions/model-routing.md" || \
    fail 'model-routing.md: missing native arguments'
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
