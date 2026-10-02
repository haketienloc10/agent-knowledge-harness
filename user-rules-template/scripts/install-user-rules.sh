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
import signal
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


class InstallInterrupted(BaseException):
    def __init__(self, signum):
        super().__init__(f"interrupted by signal {signum}")
        self.signum = signum


managed_signals = [
    sig
    for sig in (
        getattr(signal, "SIGHUP", None),
        getattr(signal, "SIGINT", None),
        getattr(signal, "SIGTERM", None),
    )
    if sig is not None
]


def interrupt_handler(signum, _frame):
    raise InstallInterrupted(signum)


for sig in managed_signals:
    signal.signal(sig, interrupt_handler)


def validate_path_ancestors(client, requested):
    parent = os.path.dirname(requested)
    components = []
    probe = parent
    while probe and probe != os.path.dirname(probe):
        components.append(probe)
        probe = os.path.dirname(probe)

    for component in reversed(components):
        if os.path.islink(component):
            if not os.path.exists(component):
                sys.stderr.write(
                    f"ERROR: {client} instruction path has a dangling symlink ancestor: {component}\n"
                )
                sys.exit(65)
            if not os.path.isdir(component):
                sys.stderr.write(
                    f"ERROR: {client} instruction path symlink ancestor is not a directory: {component}\n"
                )
                sys.exit(65)
        elif os.path.lexists(component) and not os.path.isdir(component):
            sys.stderr.write(
                f"ERROR: {client} instruction path has a non-directory ancestor: {component}\n"
            )
            sys.exit(65)


def stat_signature(path):
    st = os.stat(path, follow_symlinks=True)
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns)


def read_text(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


plans = []
for client, requested in zip(raw_pairs[0::2], raw_pairs[1::2]):
    requested = os.path.abspath(os.path.expanduser(requested))
    validate_path_ancestors(client, requested)
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
    snapshot = None
    if os.path.exists(target):
        if not os.path.isfile(target):
            sys.stderr.write(f"ERROR: {client} instruction target is not a regular file: {target}\n")
            sys.exit(65)
        snapshot = stat_signature(target)
        text = read_text(target)

    bom = "\ufeff" if text is not None and text.startswith("\ufeff") else ""
    body = text[len(bom):] if text is not None else None

    if body:
        match = re.search(r"\r\n|\n|\r", body)
        eol = match.group(0) if match else "\n"
    else:
        eol = "\n"

    managed_block = block.replace("\n", eol)
    managed_core = f"{start}{eol}{managed_block}{eol}{end}"

    if body is None:
        new_body = managed_core + eol
    else:
        starts, ends = body.count(start), body.count(end)
        if starts == 0 and ends == 0:
            new_body = managed_core + eol + (eol + body if body else "")
        elif starts == 1 and ends == 1 and body.index(start) < body.index(end):
            i = body.index(start)
            marker_end = body.index(end) + len(end)
            if body.startswith("\r\n", marker_end):
                terminator = "\r\n"
            elif body[marker_end:marker_end + 1] in ("\n", "\r"):
                terminator = body[marker_end:marker_end + 1]
            else:
                terminator = ""
            j = marker_end + len(terminator)
            new_body = body[:i] + managed_core + terminator + body[j:]
        else:
            sys.stderr.write(
                f"ERROR: {client} file has malformed marker block ({start} x{starts}, {end} x{ends}): {requested}\n"
            )
            sys.exit(65)

    new = bom + new_body
    plans.append((client, requested, target, text, snapshot, new))

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


def assert_target_unchanged(client, requested, target, original_text, snapshot):
    validate_path_ancestors(client, requested)

    if os.path.realpath(requested) != target:
        raise RuntimeError(
            f"{client} instruction path changed after preflight: {requested}"
        )

    if original_text is None:
        if os.path.lexists(target):
            raise RuntimeError(
                f"{client} instruction target appeared after preflight: {target}"
            )
        return

    if not os.path.isfile(target) or os.path.islink(target):
        raise RuntimeError(
            f"{client} instruction target identity changed after preflight: {target}"
        )

    if stat_signature(target) != snapshot or read_text(target) != original_text:
        raise RuntimeError(
            f"{client} instruction target changed after preflight: {target}"
        )


def block_commit_signals():
    if hasattr(signal, "pthread_sigmask"):
        return signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
    return None


def restore_commit_signals(previous):
    if previous is not None:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


# Prepare every replacement and rollback backup before any target is changed.
prepared = []
temps = set()
committed = []
try:
    try:
        for client, requested, target, text, snapshot, new in plans:
            if new == text:
                prepared.append(
                    (client, requested, target, None, text, snapshot, None, new)
                )
                continue

            parent = os.path.dirname(target)
            os.makedirs(parent, exist_ok=True)

            fd, tmp = tempfile.mkstemp(dir=parent, prefix=".akh-rules.")
            temps.add(tmp)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                    f.write(new)
            except BaseException:
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise

            backup = None
            if text is not None:
                shutil.copymode(target, tmp)

                backup_fd, backup = tempfile.mkstemp(
                    dir=parent, prefix=".akh-rules.backup."
                )
                os.close(backup_fd)
                temps.add(backup)
                shutil.copy2(target, backup)

            prepared.append(
                (client, requested, target, tmp, text, snapshot, backup, new)
            )

        for item in prepared:
            client, requested, target, tmp, text, snapshot, backup, new = item
            if tmp is None:
                print(f"{client} rules unchanged: {requested}")
                continue

            assert_target_unchanged(
                client, requested, target, text, snapshot
            )

            previous_mask = block_commit_signals()
            try:
                os.replace(tmp, target)
                installed_snapshot = stat_signature(target)
                temps.discard(tmp)
                committed.append((item, installed_snapshot))
            finally:
                restore_commit_signals(previous_mask)

            print(f"{client} rules installed: {requested}")

    except BaseException as commit_error:
        # Do not let a second HUP/INT/TERM interrupt rollback.
        if hasattr(signal, "pthread_sigmask"):
            signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)

        rollback_errors = []
        for committed_item, installed_snapshot in reversed(committed):
            (
                client,
                requested,
                target,
                tmp,
                text,
                snapshot,
                backup,
                new,
            ) = committed_item
            try:
                if (
                    not os.path.isfile(target)
                    or stat_signature(target) != installed_snapshot
                    or read_text(target) != new
                ):
                    raise RuntimeError(
                        "target changed again after this installer committed it"
                    )

                if text is not None:
                    if backup is None:
                        raise RuntimeError("missing rollback backup")
                    os.replace(backup, target)
                    temps.discard(backup)
                else:
                    os.unlink(target)
            except BaseException as rollback_error:
                rollback_errors.append(
                    f"{client} ({requested}): {rollback_error}"
                )

        if rollback_errors:
            sys.stderr.write(
                "ERROR: rule install failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
                + "\n"
            )

        if isinstance(commit_error, InstallInterrupted):
            raise SystemExit(128 + commit_error.signum)
        raise

finally:
    for tmp in list(temps):
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

PY

printf 'Open a fresh agent session to load the updated rules.\n'
