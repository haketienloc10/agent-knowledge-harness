#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_rules="$home/rules/response-rules.md"
marker="AKH: response-rules"
claude_file="${HOME}/.claude/CLAUDE.md"
codex_file="${HOME}/.codex/AGENTS.md"

usage() {
  cat <<'USAGE'
Usage: install-user-rules.sh [--claude-file PATH] [--codex-file PATH]

Writes rules/response-rules.md into the block delimited by
`<!-- AKH: response-rules -->` ... `<!-- /AKH: response-rules -->` in the
Claude Code and Codex user instruction files. Only the marker block is replaced.
Content outside the block is preserved. If the file has no block, the block is
prepended. A missing file is created.
USAGE
}

while (($#)); do
  case "$1" in
    --claude-file) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; claude_file="$2"; shift 2 ;;
    --codex-file) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; codex_file="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: unknown argument: %s\n' "$1" >&2; usage >&2; exit 64 ;;
  esac
done

[[ -f "$source_rules" ]] || {
  printf 'ERROR: missing source rules: %s\n' "$source_rules" >&2
  exit 66
}

command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: missing command: python3\n' >&2
  exit 69
}

install_rules() {
  local client="$1" target="$2"
  python3 - "$source_rules" "$target" "$marker" "$client" <<'PY'
import os
import shutil
import sys
import tempfile

source, target, name, client = sys.argv[1:5]
target = os.path.abspath(os.path.expanduser(target))
start, end = f"<!-- {name} -->", f"<!-- /{name} -->"

with open(source, encoding="utf-8") as f:
    block = f.read().rstrip("\n")
managed = f"{start}\n{block}\n{end}\n"

text = None
if os.path.exists(target):
    with open(target, encoding="utf-8") as f:
        text = f.read()

if text is None:
    new = managed
else:
    starts, ends = text.count(start), text.count(end)
    if starts == 0 and ends == 0:
        new = managed + ("\n" + text if text else "")
    elif starts == 1 and ends == 1 and text.index(start) < text.index(end):
        i = text.index(start)
        j = text.index(end) + len(end)
        if text[j:j + 1] == "\n":
            j += 1
        new = text[:i] + managed + text[j:]
    else:
        sys.stderr.write(
            f"ERROR: {client} file has malformed marker block ({start} x{starts}, {end} x{ends}): {target}\n"
        )
        sys.exit(65)

if new == text:
    print(f"{client} rules unchanged: {target}")
    sys.exit(0)

os.makedirs(os.path.dirname(target), exist_ok=True)
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".akh-rules.")
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write(new)
if text is not None:
    shutil.copymode(target, tmp)
os.replace(tmp, target)
print(f"{client} rules installed: {target}")
PY
}

install_rules 'Claude' "$claude_file"
install_rules 'Codex' "$codex_file"

printf 'Open a fresh agent session to load the updated rules.\n'
