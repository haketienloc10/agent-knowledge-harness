#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_rules="$home/rules/response-rules.md"
marker="AKH: response-rules"
claude_file="${HOME}/.claude/CLAUDE.md"
codex_file="${CODEX_HOME:-${HOME}/.codex}/AGENTS.md"

usage() {
  cat <<'USAGE'
Usage: install-user-rules.sh [--claude-file PATH] [--codex-file PATH]

Writes rules/response-rules.md into the block delimited by
`<!-- AKH: response-rules -->` ... `<!-- /AKH: response-rules -->` in the
Claude Code and Codex user instruction files. Only the marker block is replaced.
Content outside the block is preserved. If the file has no block, the block is
prepended. A missing file is created. Symlinked instruction files keep their
symlink and update the linked file.
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

python3 - "$source_rules" "$marker" \
  'Claude' "$claude_file" \
  'Codex' "$codex_file" <<'PY'
import os
import shutil
import sys
import tempfile

source, name = sys.argv[1:3]
raw_pairs = sys.argv[3:]
if len(raw_pairs) % 2:
    raise SystemExit("internal error: client/target pairs are incomplete")

with open(source, encoding="utf-8") as f:
    block = f.read().rstrip("\n")
start, end = f"<!-- {name} -->", f"<!-- /{name} -->"
managed = f"{start}\n{block}\n{end}\n"

plans = []
for client, requested in zip(raw_pairs[0::2], raw_pairs[1::2]):
    requested = os.path.abspath(os.path.expanduser(requested))
    target = requested

    if os.path.islink(requested):
        target = os.path.realpath(requested)
        if not os.path.exists(target):
            sys.stderr.write(f"ERROR: {client} instruction symlink is broken: {requested}\n")
            sys.exit(65)
        if not os.path.isfile(target):
            sys.stderr.write(
                f"ERROR: {client} instruction symlink does not point to a regular file: {requested} -> {target}\n"
            )
            sys.exit(65)

    text = None
    if os.path.exists(target):
        if not os.path.isfile(target):
            sys.stderr.write(f"ERROR: {client} instruction target is not a regular file: {target}\n")
            sys.exit(65)
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
                f"ERROR: {client} file has malformed marker block ({start} x{starts}, {end} x{ends}): {requested}\n"
            )
            sys.exit(65)

    plans.append((client, requested, target, text, new))

# All targets are valid before any target is changed.
prepared = []
try:
    for client, requested, target, text, new in plans:
        if new == text:
            prepared.append((client, requested, target, text, new, None))
            continue

        parent = os.path.dirname(target)
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=".akh-rules.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new)
        if text is not None:
            shutil.copymode(target, tmp)
        prepared.append((client, requested, target, text, new, tmp))

    for client, requested, target, text, new, tmp in prepared:
        if tmp is None:
            print(f"{client} rules unchanged: {requested}")
            continue
        os.replace(tmp, target)
        print(f"{client} rules installed: {requested}")
finally:
    for *_, tmp in prepared:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
PY

printf 'Open a fresh agent session to load the updated rules.\n'
