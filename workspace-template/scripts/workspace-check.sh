#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mcp_project="$workspace_root/mcp/qiqi_delegate"
template_mode="${QIQI_TEMPLATE_CHECK:-0}"
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

command -v git >/dev/null 2>&1 || fail 'missing command: git'
command -v uv >/dev/null 2>&1 || fail 'missing command: uv'
command -v python3 >/dev/null 2>&1 || fail 'missing command: python3'

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
  'child continuity không được phụ thuộc vào env inheritance từ Herdr server' \
  'work_item_path=<absolute dossier path>; id=<canonical id>; revision=<n>' \
  'Requirement change rewrite current requirement' \
  'TaskPacket phải là smallest sufficient' \
  'Default delegation route = `claude-balanced`' \
  'just-in-time ngay trước route decision' \
  'Nếu `state="blocked"`' \
  'giữ exact returned `session_id`'; do
  grep -Fq -- "$pattern" "$agents" || fail "AGENTS.md missing current policy: $pattern"
done

grep -Fq 'đọc file này ngay trước route decision' "$model_routing" || \
  fail 'model-routing.md must require just-in-time route policy hydration'
grep -Fq 'Default delegation route = claude-balanced' "$model_routing" || \
  fail 'model-routing.md must preserve claude-balanced default'

# Validate the canonical repository/dependency registry. The harness template itself
# contains {{...}} placeholders, so CI sets QIQI_TEMPLATE_CHECK=1 and validates
# structure without requiring concrete Git roots. Installed workspaces run the full
# referential, cycle and exact-root checks.
uv run --project "$mcp_project" python - "$workspace_root" "$template_mode" <<'PY'
from pathlib import Path
import subprocess
import sys
import yaml

workspace = Path(sys.argv[1]).resolve()
template_mode = sys.argv[2] == "1"
data = yaml.safe_load((workspace / "repos.yaml").read_text(encoding="utf-8")) or {}

workspace_cfg = data.get("workspace")
assert isinstance(workspace_cfg, dict), "workspace must be a map"
name = workspace_cfg.get("name")
assert isinstance(name, str) and name.strip(), "workspace.name must be non-empty"

repos = data.get("repositories")
assert isinstance(repos, list) and repos, "repositories must be a non-empty list"

names = []
paths = []
graph = {}
placeholder = lambda value: isinstance(value, str) and "{{" in value

for index, repo in enumerate(repos):
    prefix = f"repositories[{index}]"
    assert isinstance(repo, dict), f"{prefix} must be a map"
    for key in ("name", "path", "role"):
        value = repo.get(key)
        assert isinstance(value, str) and value.strip(), f"{prefix}.{key} must be non-empty"
    repo_name = repo["name"]
    repo_path = repo["path"]
    assert not Path(repo_path).is_absolute(), f"{repo_name}.path must be relative"
    names.append(repo_name)
    paths.append(repo_path)
    for key in ("required_for", "depends_on"):
        values = repo.get(key)
        assert isinstance(values, list), f"{repo_name}.{key} must be a list"
        assert all(isinstance(v, str) and v.strip() for v in values), (
            f"{repo_name}.{key} entries must be non-empty strings"
        )
        assert len(values) == len(set(values)), f"{repo_name}.{key} has duplicate entries"
    graph[repo_name] = list(repo["depends_on"])

assert len(names) == len(set(names)), "repository names must be unique"
assert len(paths) == len(set(paths)), "repository paths must be unique"

if not template_mode:
    unresolved = []
    if placeholder(name):
        unresolved.append("workspace.name")
    for index, repo in enumerate(repos):
        for key in ("name", "path", "role"):
            if placeholder(repo[key]):
                unresolved.append(f"repositories[{index}].{key}")
        for key in ("required_for", "depends_on"):
            if any(placeholder(v) for v in repo[key]):
                unresolved.append(f"repositories[{index}].{key}")
    assert not unresolved, "unresolved workspace placeholders: " + ", ".join(unresolved)

    known = set(names)
    for repo_name, dependencies in graph.items():
        for dependency in dependencies:
            assert dependency != repo_name, f"{repo_name}.depends_on references itself"
            assert dependency in known, (
                f"{repo_name}.depends_on references unknown repository: {dependency}"
            )

    visiting = set()
    visited = set()
    stack = []
    def visit(repo_name):
        if repo_name in visited:
            return
        if repo_name in visiting:
            start = stack.index(repo_name)
            raise AssertionError(
                "repository dependency cycle: "
                + " -> ".join(stack[start:] + [repo_name])
            )
        visiting.add(repo_name)
        stack.append(repo_name)
        for dependency in graph[repo_name]:
            visit(dependency)
        stack.pop()
        visiting.remove(repo_name)
        visited.add(repo_name)
    for repo_name in names:
        visit(repo_name)

    roots = []
    for repo_name, repo_path in zip(names, paths):
        root = (workspace / repo_path).resolve()
        assert root.is_dir(), f"{repo_name}: repository path does not exist: {repo_path}"
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, f"{repo_name}: path is not a Git repository"
        git_root = Path(completed.stdout.strip()).resolve()
        assert git_root == root, f"{repo_name}: path must be exact Git root"
        roots.append(str(git_root))
    assert len(roots) == len(set(roots)), "multiple repositories resolve to the same Git root"
PY

# On a real workspace, verification is also a runtime-readiness check. The template
# CI cannot install machine-local Herdr integrations, so it explicitly opts out.
if [[ "$template_mode" != "1" ]]; then
  command -v herdr >/dev/null 2>&1 || fail 'missing command: herdr'
  integration_status="$(herdr integration status 2>&1 || true)"
  mapfile -t adapters < <(
    uv run --project "$mcp_project" python - "$routing" <<'PY'
from pathlib import Path
import sys, yaml
data = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8")) or {}
print("\n".join(sorted({cfg["adapter"] for cfg in data.get("agents", {}).values()})))
PY
  )
  for adapter in "${adapters[@]}"; do
    grep -Eq "^${adapter}:[[:space:]]+current\\b" <<<"$integration_status" || \
      fail "Herdr ${adapter} integration is not current; run: herdr integration install ${adapter}"
  done
fi

bash -n "$launcher"
bash -n "$workspace_root/scripts/workspace-check.sh"

uv run --project "$mcp_project" python -m unittest discover -s "$mcp_project/tests" -v

printf 'Workspace contract: OK\n'
