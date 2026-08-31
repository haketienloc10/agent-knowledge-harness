#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/knowledge"
store_root="$home/store"
bin_dir="${HOME}/.local/bin"

usage() {
  cat <<'EOF'
Usage: install-user-mcp.sh [--store-root PATH] [--bin-dir PATH]

Installs the user-level Shared Knowledge runtime:
- managed `knowledge-distill` skill for Codex and Claude Code user scope;
- stable `agent-knowledge-mcp` wrapper;
- MCP registration named `knowledge` for available Codex/Claude CLIs.

The installer initializes then integrity-checks the target Knowledge store before changing
user-scope skill/wrapper/MCP registration. If an existing store is incompatible with the
current canonical contract, installation stops for manual repair/reindex first.

If an MCP registration or skill with the same name is owned by something else,
installation fails instead of silently replacing user configuration.
EOF
}

while (($#)); do
  case "$1" in
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

# Install MCP/core dependencies before invoking the maintenance CLI because the CLI
# imports the same filelock/PyYAML-backed core as the server.
uv sync --project "$project"
uv run --project "$project" python "$home/scripts/knowledge.py" init --root "$store_root" >/dev/null

# Public Knowledge contract changes may make formerly inert reserved-prefix text become
# canonical section syntax. Validate the entire existing store before changing any
# user-facing skill/wrapper/MCP registration so an incompatible legacy store never gets
# activated and only fails later in a fresh agent session.
if ! uv run --project "$project" python "$home/scripts/knowledge.py" check --root "$store_root"; then
  printf 'ERROR: Knowledge store compatibility preflight failed: %s\n' "$store_root" >&2
  printf 'Repair the reported canonical documents before enabling the new runtime.\n' >&2
  printf 'For reserved section-marker collisions, fence/escape illustrative `<!-- knowledge-section:` text or convert it to a valid semantic marker + H2-H6 heading.\n' >&2
  printf 'If the only issue is a stale index after valid document repair, run `knowledge.py reindex --root <store>` and rerun this installer.\n' >&2
  exit 78
fi

# Distillation is agent semantic policy, not MCP storage behavior. Install the same
# user-scoped skill for both supported agent families so QiQi and Herdr-launched
# children can discover it independent of current repository/CWD.
bash "$home/scripts/install-user-skill.sh"

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

registered=0
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
else
  printf 'WARN: codex not found; skipped Codex global MCP registration.\n' >&2
fi

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
else
  printf 'WARN: claude not found; skipped Claude user MCP registration.\n' >&2
fi

if ((registered == 0)); then
  printf 'ERROR: neither codex nor claude was available for MCP registration.\n' >&2
  exit 69
fi

printf 'Knowledge MCP wrapper: %s\n' "$wrapper"
printf 'Knowledge store root: %s\n' "$store_root"
printf 'Knowledge distillation skill: knowledge-distill\n'
printf 'Open a fresh agent session to load the user/global MCP registration and skill.\n'
