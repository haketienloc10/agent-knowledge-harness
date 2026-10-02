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
Content outside the block is preserved, including its existing line endings.
If the file has no block, the block is prepended. A missing file is created.
Symlinked instruction files keep their symlink and update the linked file.
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
import re
import shutil
import sys
import tempfile

source, name = sys.argv[1:3]
raw_pairs = sys.argv[3:]
if len(raw_pairs) % 2:
    raise SystemExit("internal error: client/target pairs are incomplete")

with open(source, encoding="utf-8", newline="") as f:
    source_block = f.read()
block = source_block.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
start, end = f"<!-- {name} -->", f"<!-- /{name} -->"

plans = []
for client, requested in zip(raw_pairs[0::2], raw_pairs[1::2]):
    requested = os.path.abspath(os.path.expanduser(requested))
    target = os.path.realpath(requested)

    if os.path.islink(requested):
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
        with open(target, encoding="utf-8", newline="") as f:
            text = f.read()

    bom = "\ufeff" if text is not None and text.startswith("\ufeff") else ""
    body = text[len(bom):] if text is not None else None

    if body:
        match = re.search(r"\r\n|\n|\r", body)
        eol = match.group(0) if match else "\n"
    else:
        eol = "\n"

    managed_block = block.replace("\n", eol)
    managed = f"{start}{eol}{managed_block}{eol}{end}{eol}"

    if body is None:
        new_body = managed
    else:
        starts, ends = body.count(start), body.count(end)
        if starts == 0 and ends == 0:
            new_body = managed + (eol + body if body else "")
        elif starts == 1 and ends == 1 and body.index(start) < body.index(end):
            i = body.index(start)
            j = body.index(end) + len(end)
            if body.startswith("\r\n", j):
                j += 2
            elif body[j:j + 1] in ("\n", "\r"):
                j += 1
            new_body = body[:i] + managed + body[j:]
        else:
            sys.stderr.write(
                f"ERROR: {client} file has malformed marker block ({start} x{starts}, {end} x{ends}): {requested}\n"
            )
            sys.exit(65)

    new = bom + new_body
    plans.append((client, requested, target, text, new))

# Reject identical or nested resolved targets before parent directories are created.
for index, left in enumerate(plans):
    left_target = left[2]
    for right in plans[index + 1:]:
        right_target = right[2]
        try:
            common = os.path.commonpath([left_target, right_target])
        except ValueError:
            continue
        if common in (left_target, right_target):
            sys.stderr.write(
                "ERROR: instruction targets overlap after path resolution: "
                f"{left[0]}={left[1]} -> {left_target}; "
                f"{right[0]}={right[1]} -> {right_target}\n"
            )
            sys.exit(65)

# Prepare every replacement before any target is changed.
prepared = []
temps = set()
try:
    for client, requested, target, text, new in plans:
        if new == text:
            prepared.append((client, requested, target, None))
            continue

        parent = os.path.dirname(target)
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=".akh-rules.")
        temps.add(tmp)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(new)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

        if text is not None:
            shutil.copymode(target, tmp)
        prepared.append((client, requested, target, tmp))

    for client, requested, target, tmp in prepared:
        if tmp is None:
            print(f"{client} rules unchanged: {requested}")
            continue
        os.replace(tmp, target)
        temps.discard(tmp)
        print(f"{client} rules installed: {requested}")
finally:
    for tmp in list(temps):
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
PY

printf 'Open a fresh agent session to load the updated rules.\n'
