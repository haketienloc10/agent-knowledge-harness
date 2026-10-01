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
  docs/WORKSPACE_PROTOCOL.md
  docs/SUPERVISOR_RUNTIME.md
  work-items/.gitkeep
  instructions/supervisor.md
  instructions/agent-routing.yaml
  instructions/model-routing.md
  scripts/qiqi-mcp-server.sh
  scripts/qiqi-supervisor-broker.sh
  scripts/e2e-autonomous-supervisor.sh
  scripts/migrate-work-item-filenames-v27.py
  mcp/qiqi_delegate/server.py
  mcp/qiqi_delegate/core.py
  mcp/qiqi_delegate/supervisor_broker.py
  mcp/qiqi_delegate/supervisor_control.py
  .codex/config.toml
)
for rel in "${required[@]}"; do
  [[ -f "$workspace_root/$rel" ]] || fail "missing required workspace file: $rel"
done

command -v git >/dev/null 2>&1 || fail 'missing command: git'
command -v uv >/dev/null 2>&1 || fail 'missing command: uv'
command -v python3 >/dev/null 2>&1 || fail 'missing command: python3'

launcher="$workspace_root/scripts/qiqi-mcp-server.sh"
supervisor_launcher="$workspace_root/scripts/qiqi-supervisor-broker.sh"
supervisor_e2e="$workspace_root/scripts/e2e-autonomous-supervisor.sh"
supervisor_broker="$mcp_project/supervisor_broker.py"
supervisor_control="$mcp_project/supervisor_control.py"
supervisor_runtime_doc="$workspace_root/docs/SUPERVISOR_RUNTIME.md"
routing="$workspace_root/instructions/agent-routing.yaml"
config="$workspace_root/.codex/config.toml"
agents="$workspace_root/AGENTS.md"
model_routing="$workspace_root/instructions/model-routing.md"
identity="$workspace_root/identity.md"
protocol="$workspace_root/docs/WORKSPACE_PROTOCOL.md"
supervisor="$workspace_root/instructions/supervisor.md"

for pattern in \
  'work_items_dir="$workspace_root/work-items"' \
  'mkdir -p "$work_items_dir"' \
  'export QIQI_WORK_ITEMS_DIR="$work_items_dir"'; do
  grep -Fq -- "$pattern" "$launcher" || fail "launcher missing delegated Work Items contract: $pattern"
done

for pattern in \
  'QIQI_HERDR_SESSION' \
  'supervisor_broker.py'; do
  grep -Fq -- "$pattern" "$supervisor_launcher" || fail "Supervisor launcher missing runtime contract: $pattern"
done

for pattern in \
  'interactive_ready' \
  'launch_pending' \
  'agent_status' \
  '"code":"agent_not_ready"' \
  'Keep the initial Work Item revision unchanged' \
  'MUST NOT increment revision'; do
  grep -Fq -- "$pattern" "$supervisor_e2e" || \
    fail "live Supervisor E2E missing Lead readiness guard: $pattern"
done

grep -Fq 'events.subscribe' "$supervisor_broker" || \
  fail 'Supervisor broker must use Herdr events.subscribe as its primary wakeup stream'
if grep -Eq 'pane[.]read|agent[.]read' "$supervisor_broker"; then
  fail 'Supervisor broker must not read terminal/pane output as semantic truth'
fi

for pattern in \
  '"workspace",' \
  '"create",' \
  '"--label",' \
  'CONTROL_ID' \
  '"pane",' \
  '"split",' \
  '"agent",' \
  '"start",' \
  '"prompt",' \
  '"--sandbox",' \
  '"read-only"' \
  '"--ask-for-approval"' \
  '"never"'; do
  grep -Fq -- "$pattern" "$supervisor_control" || \
    fail "Supervisor control plane missing persistent/runtime boundary: $pattern"
done
if grep -Eq 'pane[.]read|agent[.]read|delegate_repo_task|record_lead_disposition|record_work_item_revision|record_peer_signal|record_peer_signal_resolution|record_candidate_reconciliation|record_dependency_consumed' "$supervisor_control"; then
  fail 'Supervisor control plane must not expose terminal reads, Peer delegation, Work Item/runtime mutation, or Lead disposition mutation'
fi
grep -Fq 'DEFAULT_MODEL = "gpt-5.6-luna"' "$supervisor_control" || \
  fail 'persistent Lead/Supervisor control plane must use gpt-5.6-luna by default'
grep -Fq '"recorded": True' "$supervisor_control" || \
  fail 'Supervisor AuditPacket must expose an existing Lead disposition'
grep -Fq 'LEFT JOIN lead_dispositions d ON d.turn_id = c.turn_id' "$supervisor_control" || \
  fail 'Supervisor pending cases must hydrate disposition state by exact Peer turn'
grep -Fq '_RULE_CONTRACTS' "$supervisor_control" || \
  fail 'Supervisor AuditPacket must define deterministic R1-R5 rule contracts'
grep -Fq '"version": 2' "$supervisor_control" || \
  fail 'Supervisor AuditPacket contract version must include explicit rule semantics'
grep -Fq 'rule_contract is the normative meaning' "$supervisor_control" || \
  fail 'Supervisor prompt must treat rule_contract as normative'
grep -Fq '_agent_matches_pane' "$supervisor_control" || \
  fail 'Supervisor control plane must validate named-agent pane identity'
grep -Fq '_drain_durable' "$supervisor_broker" || \
  fail 'Supervisor broker must drain durable backlog before waiting for wakeups'
grep -Fq 'stream_once(yield_ready=True)' "$supervisor_broker" || \
  fail 'Supervisor broker must establish Herdr subscription before its final durable drain'
grep -Fq '"subscription_started"' "$supervisor_broker" || \
  fail 'Supervisor broker must wait for Herdr subscription acknowledgement'
grep -Fq 'candidate.reconciled' "$supervisor_broker" || \
  fail 'Supervisor broker must close R5 only from explicit stale-candidate evidence'
for rule in R1 R2 R3 R4 R5; do
  grep -Fq "\"$rule\":" "$supervisor_control" || \
    fail "Supervisor AuditPacket missing deterministic rule contract: $rule"
done

for pattern in \
  'bounded AuditPacket' \
  'read-only filesystem sandbox' \
  'Herdr delivery' \
  'không phải closure'; do
  grep -Fq -- "$pattern" "$supervisor" || \
    fail "supervisor.md missing autonomous runtime boundary: $pattern"
done

for pattern in \
  'workspace: slp-control' \
  'Supervisor responses are captured through the native Stop hook' \
  '`pane.read` or `agent.read` as semantic input.' \
  'must not claim continuous supervision' \
  'work_item.revision_changed' \
  'record_dependency_consumed' \
  'record_candidate_reconciliation' \
  'record_peer_signal_resolution' \
  'write_scope.claimed/released' \
  'autonomous E2E-08 state-machine integration test' \
  'normative `rule_contract`' \
  'R1: actual Peer response exists without an explicit Lead disposition' \
  'bash scripts/e2e-autonomous-supervisor.sh <repository-name>'; do
  grep -Fq -- "$pattern" "$supervisor_runtime_doc" || \
    fail "SUPERVISOR_RUNTIME.md missing runtime contract: $pattern"
done

for tool_name in \
  'record_lead_disposition' \
  'record_work_item_revision' \
  'record_peer_signal' \
  'record_peer_signal_resolution' \
  'record_candidate_reconciliation' \
  'record_dependency_consumed'; do
  grep -Fq -- "$tool_name" "$config" || \
    fail "QiQi config missing SLP semantic runtime tool: $tool_name"
done

for invocation in \
  'bash scripts/qiqi-supervisor-broker.sh' \
  'bash scripts/qiqi-supervisor-broker.sh --supervise-once' \
  'bash scripts/qiqi-supervisor-broker.sh --once'; do
  grep -Fq -- "$invocation" "$supervisor_runtime_doc" || \
    fail "SUPERVISOR_RUNTIME.md must invoke the non-executable broker launcher through bash: $invocation"
done

grep -Fq 'command: codex' "$routing" || fail 'Codex must resolve the native codex CLI'
grep -Fq 'model: gpt-5.6-luna' "$routing" || \
  fail 'codex-balanced route must use gpt-5.6-luna'
grep -Fq 'write_claim_recorded = False' "$mcp_project/server.py" || \
  fail 'direct delegation must track whether the durable write claim was persisted'
grep -Fq 'if write_claim_recorded:' "$mcp_project/server.py" || \
  fail 'direct delegation must release durable claim when dispatch recording fails'
grep -Fq 'State/phase/progress/evidence/disposition/report reconciliation' "$agents" || \
  fail 'Lead Work Item policy must forbid revision bumps for state-only reconciliation'
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
  '00_WORK_ITEM.md' \
  '10_intake.md' \
  '20_investigation.md' \
  '30_plan.md' \
  '40_review.md' \
  '90_report.textile' \
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


for pattern in \
  'Supervisor–Lead–Peers (SLP)' \
  'Lead brief' \
  'actual Peer response' \
  'explicit Lead disposition' \
  'REOPEN_REQUEST' \
  'DEPENDENCY_REQUEST' \
  'BLOCKED' \
  'không cấp filesystem authority'; do
  grep -Fq -- "$pattern" "$protocol" || fail "WORKSPACE_PROTOCOL.md missing SLP contract: $pattern"
done

for pattern in \
  'Room role: **Supervisor**' \
  'không phải technical Lead thứ hai' \
  'Không ACCEPT/REJECT candidate' \
  'không giả vờ continuous supervision'; do
  grep -Fq -- "$pattern" "$supervisor" || fail "supervisor.md missing oversight boundary: $pattern"
done

for pattern in \
  'SLP Lead (QiQi)' \
  'docs/WORKSPACE_PROTOCOL.md' \
  'Peer judgment + Lead disposition' \
  'filesystem authorization' \
  'downstream Peer không cần và không được tự dereference sibling repo' \
  'explicit `ACCEPT` / `REJECT`' \
  'record_work_item_revision' \
  'record_peer_signal' \
  'record_peer_signal_resolution' \
  'record_candidate_reconciliation' \
  'record_dependency_consumed' \
  'write_scope.claimed/released'; do
  grep -Fq -- "$pattern" "$agents" || fail "AGENTS.md missing SLP Lead policy: $pattern"
done


for pattern in \
  'SLP **Lead**' \
  'Human sở hữu product goal' \
  'Supervisor là oversight plane' \
  'explicit Lead disposition'; do
  grep -Fq -- "$pattern" "$identity" || fail "identity.md missing SLP Lead authority: $pattern"
done
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

# Real workspaces must be fully migrated to the ordered Work Item filename contract.
# Template CI has only work-items/.gitkeep and intentionally skips runtime dossiers.
if [[ "$template_mode" != "1" ]]; then
  python3 - "$workspace_root/work-items" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
legacy = {
    "WORK_ITEM.md",
    "intake.md",
    "investigation.md",
    "plan.md",
    "review.md",
    "report.textile",
}
numbered_optional = {
    "10_intake.md",
    "20_investigation.md",
    "30_plan.md",
    "40_review.md",
    "90_report.textile",
}

for dossier in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
    if dossier.name.startswith("."):
        continue
    assert dossier.is_dir() and not dossier.is_symlink(), (
        f"Work Item entry must be a real dossier directory: {dossier}"
    )
    present_legacy = sorted(name for name in legacy if (dossier / name).exists() or (dossier / name).is_symlink())
    assert not present_legacy, (
        f"legacy unprefixed Work Item filenames remain in {dossier}: {', '.join(present_legacy)}; "
        "run scripts/migrate-work-item-filenames-v27.py"
    )
    primary = dossier / "00_WORK_ITEM.md"
    assert primary.is_file() and not primary.is_symlink(), (
        f"missing/invalid canonical Work Item file: {primary}"
    )
    for name in numbered_optional:
        path = dossier / name
        if path.exists() or path.is_symlink():
            assert path.is_file() and not path.is_symlink(), (
                f"numbered lifecycle path must be a regular file: {path}"
            )
PY
fi

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
bash -n "$supervisor_launcher"
bash -n "$supervisor_e2e"
bash -n "$workspace_root/scripts/workspace-check.sh"
python3 -m py_compile "$workspace_root/scripts/migrate-work-item-filenames-v27.py"
python3 -m py_compile "$supervisor_broker"
python3 -m py_compile "$supervisor_control"

uv run --project "$mcp_project" python -m unittest discover -s "$mcp_project/tests" -v

printf 'Workspace contract: OK\n'
