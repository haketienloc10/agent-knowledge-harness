#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/knowledge"
store_root="$home/store"
bin_dir="${HOME}/.local/bin"
clients="available"

usage() {
  cat <<'EOF'
Usage: install-user-mcp.sh [--clients available|claude|codex|both] [--store-root PATH] [--bin-dir PATH]

Installs the user-level Shared Knowledge runtime:
- managed `knowledge-distill` skill for selected Codex/Claude clients;
- stable `agent-knowledge-mcp` wrapper;
- MCP registration named `knowledge` for selected clients.

Default `--clients available` preserves the historical behavior: install the shared
skill for both client families and register the MCP in each CLI currently available.
Explicit `claude`, `codex`, or `both` selections are strict and fail if a selected
CLI is missing.

The installer initializes then integrity-checks the target Knowledge store before changing
user-scope skill/wrapper/MCP registration. If an existing store is incompatible with the
current canonical contract, installation stops for manual repair/reindex first.

If an MCP registration or skill with the same name is owned by something else,
installation fails instead of silently replacing user configuration.
EOF
}

normalize_clients() {
  case "$1" in
    available|claude|codex|both) printf '%s\n' "$1" ;;
    *) return 1 ;;
  esac
}

while (($#)); do
  case "$1" in
    --clients)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      clients="$(normalize_clients "$2")" || {
        printf 'ERROR: invalid --clients value: %s\n' "$2" >&2
        exit 64
      }
      shift 2
      ;;
    --store-root)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      store_root="$2"
      shift 2
      ;;
    --bin-dir)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      bin_dir="$2"
      shift 2
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

command -v uv >/dev/null 2>&1 || {
  printf 'ERROR: missing command: uv\n' >&2
  exit 69
}
command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: missing command: python3\n' >&2
  exit 69
}

store_root="$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$store_root")"
bin_dir="$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$bin_dir")"

uv sync --project "$project"
uv run --project "$project" python "$home/scripts/knowledge.py" init --root "$store_root" >/dev/null

if ! uv run --project "$project" python "$home/scripts/knowledge.py" check --root "$store_root"; then
  printf 'ERROR: Knowledge store compatibility preflight failed: %s\n' "$store_root" >&2
  printf 'Repair the reported canonical documents before enabling the new runtime.\n' >&2
  printf 'For reserved section-marker collisions, fence/escape illustrative `<!-- knowledge-section:` text or convert it to a valid semantic marker + H2-H6 heading.\n' >&2
  printf 'If the only issue is a stale index after valid document repair, run `knowledge.py reindex --root <store>` and rerun this installer.\n' >&2
  exit 78
fi

skill_clients="$clients"
[[ "$skill_clients" == "available" ]] && skill_clients="both"
bash "$home/scripts/install-user-skill.sh" --clients "$skill_clients"

mkdir -p "$bin_dir"
wrapper="$bin_dir/agent-knowledge-mcp"

HOME_PATH="$home" STORE_PATH="$store_root" python3 - "$wrapper" <<'PY'
import os
import shlex
import sys
from pathlib import Path

wrapper = Path(sys.argv[1])
home = os.environ["HOME_PATH"]
store = os.environ["STORE_PATH"]
text = "\n".join(
    [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"export KNOWLEDGE_STORE_ROOT={shlex.quote(store)}",
        f"exec {shlex.quote(home + '/scripts/knowledge-mcp-server.sh')}",
        "",
    ]
)
wrapper.write_text(text, encoding="utf-8")
wrapper.chmod(0o755)
PY

verify_existing_target() {
  local client="$1"
  local output="$2"
  if ! printf '%s\n' "$output" | grep -Fq -- "$wrapper"; then
    printf 'ERROR: %s MCP `knowledge` already exists but does not point to %s\n' \
      "$client" "$wrapper" >&2
    printf 'Remove/rename the conflicting registration explicitly, then rerun installer.\n' >&2
    return 78
  fi
}

client_selected() {
  local client="$1"
  [[ "$clients" == "available" || "$clients" == "both" || "$clients" == "$client" ]]
}

client_required() {
  [[ "$clients" != "available" ]]
}

registered=0
if client_selected codex; then
  if command -v codex >/dev/null 2>&1; then
    if existing="$(codex mcp get knowledge 2>&1)"; then
      verify_existing_target 'Codex' "$existing"
      printf 'Codex MCP `knowledge` already points to the stable wrapper; keeping registration.\n'
    else
      codex mcp add knowledge -- "$wrapper"
    fi
    verified="$(codex mcp get knowledge 2>&1)"
    verify_existing_target 'Codex' "$verified"
    registered=$((registered + 1))
  elif client_required; then
    printf 'ERROR: selected Knowledge client is not installed: codex\n' >&2
    exit 69
  else
    printf 'WARN: codex not found; skipped Codex global MCP registration.\n' >&2
  fi
fi

if client_selected claude; then
  if command -v claude >/dev/null 2>&1; then
    if existing="$(claude mcp get knowledge 2>&1)"; then
      verify_existing_target 'Claude' "$existing"
      printf 'Claude MCP `knowledge` already points to the stable wrapper; keeping registration.\n'
    else
      claude mcp add knowledge --scope user "$wrapper"
    fi
    verified="$(claude mcp get knowledge 2>&1)"
    verify_existing_target 'Claude' "$verified"
    registered=$((registered + 1))
  elif client_required; then
    printf 'ERROR: selected Knowledge client is not installed: claude\n' >&2
    exit 69
  else
    printf 'WARN: claude not found; skipped Claude user MCP registration.\n' >&2
  fi
fi

if ((registered == 0)); then
  printf 'ERROR: no selected/available client was available for Knowledge MCP registration.\n' >&2
  exit 69
fi

printf 'Knowledge MCP wrapper: %s\n' "$wrapper"
printf 'Knowledge store root: %s\n' "$store_root"
printf 'Knowledge clients: %s\n' "$clients"
printf 'Knowledge distillation skill: knowledge-distill\n'
printf 'Open a fresh agent session to load the user/global MCP registration and skill.\n'
