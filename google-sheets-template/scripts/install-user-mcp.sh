#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$home/mcp/google_sheets"
bin_dir="${HOME}/.local/bin"
credentials=""
declare -a spreadsheet_ids=()

usage() {
  cat <<'EOF'
Usage: install-user-mcp.sh --credentials PATH --spreadsheet-id ID [--spreadsheet-id ID ...] [--bin-dir PATH]

Installs a user-level Codex MCP named `google_sheets_readonly`.

Security contract:
- Google service-account credentials only;
- Google Sheets OAuth scope is `spreadsheets.readonly`;
- at least one spreadsheet ID must be explicitly allowlisted;
- the service account should be shared as Viewer, never Editor;
- only bounded A1 reads are exposed; no Drive API or mutation tools are registered.

The credentials JSON stays outside this repository. Do not commit it.
EOF
}

while (($#)); do
  case "$1" in
    --credentials)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      credentials="$2"
      shift 2
      ;;
    --spreadsheet-id)
      [[ $# -ge 2 ]] || { usage >&2; exit 64; }
      spreadsheet_ids+=("$2")
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

[[ -n "$credentials" ]] || {
  printf 'ERROR: --credentials is required\n' >&2
  usage >&2
  exit 64
}
((${#spreadsheet_ids[@]} > 0)) || {
  printf 'ERROR: at least one --spreadsheet-id is required\n' >&2
  usage >&2
  exit 64
}

command -v uv >/dev/null 2>&1 || {
  printf 'ERROR: missing command: uv\n' >&2
  exit 69
}
command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: missing command: python3\n' >&2
  exit 69
}
command -v codex >/dev/null 2>&1 || {
  printf 'ERROR: missing command: codex\n' >&2
  exit 69
}

credentials="$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$credentials")"
bin_dir="$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$bin_dir")"

python3 - "$credentials" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit("ERROR: credentials path is not a readable file")
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    raise SystemExit(f"ERROR: credentials JSON is invalid: {exc}") from exc
if payload.get("type") != "service_account":
    raise SystemExit("ERROR: credentials JSON must be a Google service_account key")
for field in ("client_email", "private_key", "token_uri"):
    if not payload.get(field):
        raise SystemExit(f"ERROR: service-account credentials missing required field: {field}")
PY

allowed_ids="$(printf '%s\n' "${spreadsheet_ids[@]}" | python3 -c '
import re, sys
values=[]
for raw in sys.stdin:
    value=raw.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", value):
        raise SystemExit(f"ERROR: invalid spreadsheet ID: {value!r}; pass the document ID, not a full URL")
    if value not in values:
        values.append(value)
print(",".join(values))
')"

uv sync --project "$project"

mkdir -p "$bin_dir"
wrapper="$bin_dir/agent-google-sheets-readonly-mcp"

HOME_PATH="$home" CREDENTIALS_PATH="$credentials" ALLOWED_IDS="$allowed_ids" python3 - "$wrapper" <<'PY'
import os
import shlex
import sys
from pathlib import Path

wrapper = Path(sys.argv[1])
home = os.environ["HOME_PATH"]
credentials = os.environ["CREDENTIALS_PATH"]
allowed_ids = os.environ["ALLOWED_IDS"]
text = "\n".join(
    [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"export GOOGLE_APPLICATION_CREDENTIALS={shlex.quote(credentials)}",
        f"export GOOGLE_SHEETS_ALLOWED_IDS={shlex.quote(allowed_ids)}",
        f"exec {shlex.quote(home + '/scripts/google-sheets-mcp-server.sh')}",
        "",
    ]
)
wrapper.write_text(text, encoding="utf-8")
wrapper.chmod(0o755)
PY

verify_existing_target() {
  local output="$1"
  if ! printf '%s\n' "$output" | grep -Fq -- "$wrapper"; then
    printf 'ERROR: Codex MCP `google_sheets_readonly` already exists but does not point to %s\n' "$wrapper" >&2
    printf 'Remove/rename the conflicting registration explicitly, then rerun installer.\n' >&2
    return 78
  fi
}

if existing="$(codex mcp get google_sheets_readonly 2>&1)"; then
  verify_existing_target "$existing"
  printf 'Codex MCP `google_sheets_readonly` already points to the stable wrapper; keeping registration.\n'
else
  codex mcp add google_sheets_readonly -- "$wrapper"
fi

verified="$(codex mcp get google_sheets_readonly 2>&1)"
verify_existing_target "$verified"

printf 'Google Sheets readonly MCP wrapper: %s\n' "$wrapper"
printf 'Credentials: %s\n' "$credentials"
printf 'Allowlisted spreadsheet IDs: %s\n' "$allowed_ids"
printf 'Open a fresh Codex session to load the user/global MCP registration.\n'
