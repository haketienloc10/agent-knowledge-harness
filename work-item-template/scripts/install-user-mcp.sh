#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/work_item"
db_path="${HOME}/.local/share/agent-work-items/work-items.sqlite3"
bin_dir="${HOME}/.local/bin"

usage() {
  cat <<'EOF'
Usage: install-user-mcp.sh [--db-path PATH] [--bin-dir PATH]

Installs the user-level Global Work Item MCP:
- stable `agent-work-item-mcp` wrapper;
- MCP registration named `work_item` for available Codex/Claude CLIs;
- one global SQLite database shared by QiQi and repository execution agents.

The installer refuses to replace an existing `work_item` MCP registration that
points somewhere else.
EOF
}

while (($#)); do
  case "$1" in
    --db-path)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      db_path="$2"
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

db_path="$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$db_path")"
bin_dir="$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$bin_dir")"
mkdir -p "$(dirname "$db_path")" "$bin_dir"

uv sync --project "$project"

wrapper="$bin_dir/agent-work-item-mcp"
HOME_PATH="$home" DB_PATH="$db_path" python3 - "$wrapper" <<'PY'
import os
import shlex
import sys
from pathlib import Path

wrapper = Path(sys.argv[1])
home = os.environ["HOME_PATH"]
db = os.environ["DB_PATH"]
text = "\n".join(
    [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"export WORK_ITEM_DB_PATH={shlex.quote(db)}",
        f"exec bash {shlex.quote(home + '/scripts/work-item-mcp-server.sh')}",
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
    printf 'ERROR: %s MCP `work_item` already exists but does not point to %s\n' \
      "$client" "$wrapper" >&2
    printf 'Remove/rename the conflicting registration explicitly, then rerun installer.\n' >&2
    return 78
  fi
}

registered=0
if command -v codex >/dev/null 2>&1; then
  if existing="$(codex mcp get work_item 2>&1)"; then
    verify_existing_target 'Codex' "$existing"
    printf 'Codex MCP `work_item` already points to the stable wrapper; keeping registration.\n'
  else
    codex mcp add work_item -- "$wrapper"
  fi
  verified="$(codex mcp get work_item 2>&1)"
  verify_existing_target 'Codex' "$verified"
  registered=$((registered + 1))
else
  printf 'WARN: codex not found; skipped Codex global MCP registration.\n' >&2
fi

if command -v claude >/dev/null 2>&1; then
  if existing="$(claude mcp get work_item 2>&1)"; then
    verify_existing_target 'Claude' "$existing"
    printf 'Claude MCP `work_item` already points to the stable wrapper; keeping registration.\n'
  else
    claude mcp add work_item --scope user "$wrapper"
  fi
  verified="$(claude mcp get work_item 2>&1)"
  verify_existing_target 'Claude' "$verified"
  registered=$((registered + 1))
else
  printf 'WARN: claude not found; skipped Claude user MCP registration.\n' >&2
fi

if ((registered == 0)); then
  printf 'ERROR: neither codex nor claude was available for MCP registration.\n' >&2
  exit 69
fi

printf 'Work Item MCP wrapper: %s\n' "$wrapper"
printf 'Work Item database: %s\n' "$db_path"
printf 'Open a fresh agent session to load the user/global MCP registration.\n'
