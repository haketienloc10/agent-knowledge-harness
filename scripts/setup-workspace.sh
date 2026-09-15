#!/usr/bin/env bash
set -euo pipefail

harness_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_root=""
coordinators=""
execution_agents=""
default_route=""
install_global_mcp=1
verify_after=1
knowledge_store=""
work_item_db=""
non_interactive=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/setup-workspace.sh /path/to/workspace [options]

Options:
  --workspace PATH                 Existing QiQi workspace root.
  --coordinators claude|codex|both
                                   Coordinator clients to configure.
  --agents claude|codex|both       Herdr execution agents to install.
  --default-route claude|codex     Default balanced delegation route.
  --knowledge-store PATH           Optional Shared Knowledge store root.
  --work-item-db PATH              Optional Global Work Item SQLite path.
  --skip-global-mcp                Do not install/refresh work_item + knowledge.
  --skip-verify                    Skip final unit/workspace checks.
  --non-interactive                Require all required choices as flags.
  -h, --help                       Show this help.

Interactive mode asks for any missing coordinator/agent/default-route choices.
The default route is stored machine-locally in .qiqi/config.local.json.
Claude child isolation is provisioned in each repo's .claude/settings.local.json.
EOF
}

if (($#)) && [[ "$1" != -* ]]; then
  workspace_root="$1"
  shift
fi

while (($#)); do
  case "$1" in
    --workspace)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      workspace_root="$2"
      shift 2
      ;;
    --coordinators)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      coordinators="$2"
      shift 2
      ;;
    --agents)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      execution_agents="$2"
      shift 2
      ;;
    --default-route)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      default_route="$2"
      shift 2
      ;;
    --knowledge-store)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      knowledge_store="$2"
      shift 2
      ;;
    --work-item-db)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      work_item_db="$2"
      shift 2
      ;;
    --skip-global-mcp)
      install_global_mcp=0
      shift
      ;;
    --skip-verify)
      verify_after=0
      shift
      ;;
    --non-interactive)
      non_interactive=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'ERROR: missing command: %s\n' "$1" >&2
    exit 69
  }
}

normalize_multi() {
  case "$1" in
    1|claude) printf 'claude\n' ;;
    2|codex) printf 'codex\n' ;;
    3|both) printf 'both\n' ;;
    *) return 1 ;;
  esac
}

normalize_default() {
  case "$1" in
    1|claude|claude-balanced) printf 'claude-balanced\n' ;;
    2|codex|codex-balanced) printf 'codex-balanced\n' ;;
    *) return 1 ;;
  esac
}

prompt_multi() {
  local title="$1" answer normalized
  printf '\n%s\n' "$title" >&2
  printf '  1) Claude Code\n' >&2
  printf '  2) Codex\n' >&2
  printf '  3) Both\n' >&2
  while true; do
    printf 'Choose [1-3]: ' >&2
    IFS= read -r answer
    if normalized="$(normalize_multi "$answer")"; then
      printf '%s\n' "$normalized"
      return
    fi
    printf 'Invalid choice.\n' >&2
  done
}

prompt_default() {
  local answer normalized
  printf '\nDefault delegation route\n' >&2
  printf '  1) Claude balanced\n' >&2
  printf '  2) Codex balanced\n' >&2
  while true; do
    printf 'Choose [1-2]: ' >&2
    IFS= read -r answer
    if normalized="$(normalize_default "$answer")"; then
      printf '%s\n' "$normalized"
      return
    fi
    printf 'Invalid choice.\n' >&2
  done
}

if [[ -z "$workspace_root" ]]; then
  if ((non_interactive)); then
    printf 'ERROR: --workspace is required in non-interactive mode.\n' >&2
    exit 64
  fi
  printf 'Workspace path: ' >&2
  IFS= read -r workspace_root
fi

require_command python3
workspace_root="$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$workspace_root")"

[[ -d "$workspace_root" ]] || {
  printf 'ERROR: workspace does not exist: %s\n' "$workspace_root" >&2
  exit 66
}
for required in AGENTS.md identity.md repos.yaml scripts/qiqi-mcp-server.sh instructions/agent-routing.yaml; do
  [[ -f "$workspace_root/$required" ]] || {
    printf 'ERROR: not a QiQi workspace; missing %s\n' "$workspace_root/$required" >&2
    exit 66
  }
done

if [[ -z "$coordinators" ]]; then
  ((non_interactive)) && { printf 'ERROR: --coordinators is required.\n' >&2; exit 64; }
  coordinators="$(prompt_multi 'Coordinator clients')"
else
  coordinators="$(normalize_multi "$coordinators")" || {
    printf 'ERROR: invalid --coordinators value\n' >&2
    exit 64
  }
fi

if [[ -z "$execution_agents" ]]; then
  ((non_interactive)) && { printf 'ERROR: --agents is required.\n' >&2; exit 64; }
  execution_agents="$(prompt_multi 'Herdr execution agents')"
else
  execution_agents="$(normalize_multi "$execution_agents")" || {
    printf 'ERROR: invalid --agents value\n' >&2
    exit 64
  }
fi

if [[ -z "$default_route" ]]; then
  if [[ "$execution_agents" == "claude" ]]; then
    default_route="claude-balanced"
  elif [[ "$execution_agents" == "codex" ]]; then
    default_route="codex-balanced"
  else
    ((non_interactive)) && { printf 'ERROR: --default-route is required when --agents=both.\n' >&2; exit 64; }
    default_route="$(prompt_default)"
  fi
else
  default_route="$(normalize_default "$default_route")" || {
    printf 'ERROR: invalid --default-route value\n' >&2
    exit 64
  }
fi

if [[ "$default_route" == claude-* && "$execution_agents" == "codex" ]]; then
  printf 'ERROR: Claude default route requires Claude execution agent.\n' >&2
  exit 64
fi
if [[ "$default_route" == codex-* && "$execution_agents" == "claude" ]]; then
  printf 'ERROR: Codex default route requires Codex execution agent.\n' >&2
  exit 64
fi

printf '\nQiQi workspace setup\n'
printf '  workspace:      %s\n' "$workspace_root"
printf '  coordinators:   %s\n' "$coordinators"
printf '  agents:         %s\n' "$execution_agents"
printf '  default route:  %s\n' "$default_route"
printf '  global MCPs:    %s\n' "$([[ $install_global_mcp -eq 1 ]] && printf install || printf skip)"
printf '\n'

require_command uv
require_command herdr

needs_claude=0
needs_codex=0
[[ "$coordinators" == "claude" || "$coordinators" == "both" || "$execution_agents" == "claude" || "$execution_agents" == "both" ]] && needs_claude=1
[[ "$coordinators" == "codex" || "$coordinators" == "both" || "$execution_agents" == "codex" || "$execution_agents" == "both" ]] && needs_codex=1
((needs_claude)) && require_command claude
((needs_codex)) && require_command codex

if ((install_global_mcp)); then
  work_item_args=()
  [[ -n "$work_item_db" ]] && work_item_args+=(--db-path "$work_item_db")
  bash "$harness_root/work-item-template/scripts/install-user-mcp.sh" "${work_item_args[@]}"

  knowledge_args=()
  [[ -n "$knowledge_store" ]] && knowledge_args+=(--store-root "$knowledge_store")
  bash "$harness_root/knowledge-template/scripts/install-user-mcp.sh" "${knowledge_args[@]}"
fi

uv sync --project "$workspace_root/mcp/qiqi_delegate"

if [[ "$coordinators" == "claude" || "$coordinators" == "both" ]]; then
  bash "$workspace_root/scripts/setup-claude.sh"
fi

if [[ "$coordinators" == "codex" || "$coordinators" == "both" ]]; then
  [[ -f "$workspace_root/.codex/config.toml" ]] || {
    printf 'ERROR: missing Codex project adapter: %s/.codex/config.toml\n' "$workspace_root" >&2
    exit 66
  }
  (cd "$workspace_root" && codex mcp get qiqi_delegate >/dev/null)
fi

if [[ "$execution_agents" == "claude" || "$execution_agents" == "both" ]]; then
  herdr integration install claude
fi
if [[ "$execution_agents" == "codex" || "$execution_agents" == "both" ]]; then
  herdr integration install codex
fi
herdr integration status

mkdir -p "$workspace_root/.qiqi"
python3 - "$workspace_root/.qiqi/config.local.json" "$coordinators" "$execution_agents" "$default_route" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
coordinators = sys.argv[2]
agents = sys.argv[3]
default_route = sys.argv[4]

def expand(value: str) -> list[str]:
    return ["claude", "codex"] if value == "both" else [value]

data = {
    "version": 1,
    "coordinators": expand(coordinators),
    "execution_agents": expand(agents),
    "default_route": default_route,
}
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if ! grep -Fxq 'config.local.json' "$workspace_root/.qiqi/.gitignore" 2>/dev/null; then
  printf 'config.local.json\n' >> "$workspace_root/.qiqi/.gitignore"
fi

if ((verify_after)); then
  uv run --project "$workspace_root/mcp/qiqi_delegate" \
    python -m unittest discover -s "$workspace_root/mcp/qiqi_delegate/tests" -v
  bash "$workspace_root/scripts/workspace-check.sh"
fi

printf '\nSetup complete.\n'
printf '  Runtime config: %s/.qiqi/config.local.json\n' "$workspace_root"
if [[ "$coordinators" == "claude" || "$coordinators" == "both" ]]; then
  printf '  Claude QiQi:    cd %q && claude\n' "$workspace_root"
fi
if [[ "$coordinators" == "codex" || "$coordinators" == "both" ]]; then
  printf '  Codex QiQi:     cd %q && codex\n' "$workspace_root"
fi
