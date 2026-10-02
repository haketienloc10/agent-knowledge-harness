#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_rules="$home/rules/response-rules.md"
marker="AKH: response-rules"
claude_file="${CLAUDE_CONFIG_DIR:-${HOME}/.claude}/CLAUDE.md"
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
import hashlib
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


def stat_fingerprint(st):
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
    )


def read_stable_bytes(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        before = os.fstat(fd)
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)

    payload = b"".join(chunks)
    if stat_fingerprint(before) != stat_fingerprint(after):
        raise RuntimeError(f"source rules changed while being read: {path}")
    if len(payload) != after.st_size:
        raise RuntimeError(f"source rules size changed while being read: {path}")

    current = os.stat(path, follow_symlinks=True)
    if (current.st_dev, current.st_ino) != (after.st_dev, after.st_ino):
        raise RuntimeError(f"source rules identity changed while being read: {path}")

    return payload, stat_fingerprint(after), hashlib.sha256(payload).digest()


source_bytes, source_snapshot, source_digest = read_stable_bytes(source)
source_block = source_bytes.decode("utf-8")
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


def object_signature(path):
    st = os.lstat(path)
    if os.path.islink(path):
        payload = ("symlink", os.readlink(path))
    elif os.path.isfile(path):
        with open(path, "rb") as handle:
            payload = ("file", handle.read())
    elif os.path.isdir(path):
        payload = ("directory", None)
    else:
        payload = ("other", None)
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_size,
        st.st_mtime_ns,
        payload,
    )


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


# The staged output is derived only from source_bytes. Revalidate the source
# immediately before any transaction material is created so an in-place writer
# cannot make a mixed/truncated read look successful.
current_source_bytes, current_source_snapshot, current_source_digest = read_stable_bytes(
    source
)
if (
    current_source_snapshot != source_snapshot
    or current_source_digest != source_digest
    or current_source_bytes != source_bytes
):
    raise RuntimeError("source rules changed after snapshot; retry installation")


def block_commit_signals():
    if hasattr(signal, "pthread_sigmask"):
        return signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
    return None


def restore_commit_signals(previous):
    if previous is not None:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


# Prepare every replacement and rollback placeholder before any target is changed.
prepared = []
temps = set()
preserved_backups = set()

def quarantine_installed_target(item):
    """Remove our installed object without deleting a concurrent writer's replacement."""
    target = item["target"]
    if not os.path.lexists(target):
        return

    parent = os.path.dirname(target)
    quarantine_fd, quarantine = tempfile.mkstemp(
        dir=parent, prefix=".akh-rules.rollback."
    )
    os.close(quarantine_fd)
    temps.add(quarantine)

    try:
        # Move whatever occupies target now. If another writer won the race
        # after our last observation, its object is moved rather than deleted.
        os.replace(target, quarantine)
    except FileNotFoundError:
        try:
            os.unlink(quarantine)
        except FileNotFoundError:
            pass
        temps.discard(quarantine)
        return

    is_ours = (
        os.path.isfile(quarantine)
        and not os.path.islink(quarantine)
        and stat_signature(quarantine) == item["installed_snapshot"]
        and read_text(quarantine) == item["new"]
    )
    if is_ours:
        os.unlink(quarantine)
        temps.discard(quarantine)
        return

    # A concurrent writer replaced our published file. Never delete it. For a
    # regular file, publish it back with a no-clobber hard link; otherwise retain
    # the quarantined object and report its exact path.
    republished = False
    if os.path.isfile(quarantine) and not os.path.islink(quarantine):
        try:
            os.link(quarantine, target, follow_symlinks=False)
        except (FileExistsError, OSError):
            pass
        else:
            os.unlink(quarantine)
            temps.discard(quarantine)
            republished = True

    if republished:
        raise RuntimeError(
            "installed target changed after commit; concurrent replacement was preserved"
        )

    temps.discard(quarantine)
    preserved_backups.add(quarantine)
    raise RuntimeError(
        "installed target changed after commit; concurrent replacement retained at "
        f"{quarantine}"
    )


try:
    try:
        for client, requested, target, text, snapshot, new in plans:
            if new == text:
                prepared.append(
                    {
                        "client": client,
                        "requested": requested,
                        "target": target,
                        "text": text,
                        "snapshot": snapshot,
                        "new": new,
                        "tmp": None,
                        "backup": None,
                        "moved_aside": False,
                        "backup_signature": None,
                        "installed": False,
                        "installed_snapshot": None,
                    }
                )
                continue

            # Revalidate before creating any per-target transaction material.
            assert_target_unchanged(
                client, requested, target, text, snapshot
            )

            parent = os.path.dirname(target)
            os.makedirs(parent, exist_ok=True)

            previous_temp_mask = block_commit_signals()
            try:
                fd, tmp = tempfile.mkstemp(dir=parent, prefix=".akh-rules.")
                temps.add(tmp)
            finally:
                restore_commit_signals(previous_temp_mask)

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

                previous_backup_mask = block_commit_signals()
                try:
                    backup_fd, backup = tempfile.mkstemp(
                        dir=parent, prefix=".akh-rules.backup."
                    )
                    temps.add(backup)
                finally:
                    restore_commit_signals(previous_backup_mask)
                os.close(backup_fd)

            prepared.append(
                {
                    "client": client,
                    "requested": requested,
                    "target": target,
                    "text": text,
                    "snapshot": snapshot,
                    "new": new,
                    "tmp": tmp,
                    "backup": backup,
                    "moved_aside": False,
                    "backup_signature": None,
                    "installed": False,
                    "installed_snapshot": None,
                }
            )

        for item in prepared:
            client = item["client"]
            requested = item["requested"]
            target = item["target"]
            text = item["text"]
            snapshot = item["snapshot"]
            tmp = item["tmp"]
            backup = item["backup"]
            new = item["new"]

            if tmp is None:
                # A no-op target still participates in the two-client
                # transaction. Revalidate it before allowing another client to
                # commit so both clients remain on the same preflight snapshot.
                assert_target_unchanged(
                    client, requested, target, text, snapshot
                )
                print(f"{client} rules unchanged: {requested}")
                continue

            assert_target_unchanged(
                client, requested, target, text, snapshot
            )

            previous_mask = block_commit_signals()
            try:
                # Revalidate again under the signal mask. For an existing file,
                # move the exact object aside before installing the replacement.
                assert_target_unchanged(
                    client, requested, target, text, snapshot
                )

                if text is not None:
                    os.replace(target, backup)
                    item["moved_aside"] = True
                    item["backup_signature"] = object_signature(backup)

                    # If another writer won the race between revalidation and
                    # the move, abort. Rollback restores exactly what we moved.
                    if (
                        not os.path.isfile(backup)
                        or os.path.islink(backup)
                        or stat_signature(backup) != snapshot
                        or read_text(backup) != text
                    ):
                        raise RuntimeError(
                            f"{client} instruction target changed during commit"
                        )

                if os.path.lexists(target):
                    raise RuntimeError(
                        f"{client} instruction target appeared during commit: {target}"
                    )

                # tmp and target share a parent/filesystem. Hard-link creation is
                # atomic and fails if target appeared, so it cannot clobber an
                # unrelated file in the final race window.
                os.link(tmp, target, follow_symlinks=False)
                item["installed"] = True
                item["installed_snapshot"] = stat_signature(target)

                if read_text(target) != new:
                    raise RuntimeError(
                        f"{client} installed rules differ from staged content"
                    )

                os.unlink(tmp)
                temps.discard(tmp)
            finally:
                restore_commit_signals(previous_mask)

            print(f"{client} rules installed: {requested}")

        # Verify the complete two-client result before backups are discarded.
        # This catches a no-op target (or a freshly installed target) changing
        # while the other client is being committed.
        for item in prepared:
            if item["tmp"] is None:
                assert_target_unchanged(
                    item["client"],
                    item["requested"],
                    item["target"],
                    item["text"],
                    item["snapshot"],
                )
                continue

            target = item["target"]
            if (
                not item["installed"]
                or not os.path.isfile(target)
                or os.path.islink(target)
                or stat_signature(target) != item["installed_snapshot"]
                or read_text(target) != item["new"]
            ):
                raise RuntimeError(
                    f"{item['client']} instruction target changed before "
                    "transaction completion"
                )

    except BaseException as commit_error:
        # Do not let a second HUP/INT/TERM interrupt rollback.
        if hasattr(signal, "pthread_sigmask"):
            signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)

        rollback_errors = []
        for item in reversed(prepared):
            client = item["client"]
            requested = item["requested"]
            target = item["target"]
            text = item["text"]
            backup = item["backup"]

            try:
                if item["installed"]:
                    quarantine_installed_target(item)
                    item["installed"] = False

                if item["moved_aside"]:
                    if backup is None or not os.path.lexists(backup):
                        raise RuntimeError("rollback backup is missing")
                    if object_signature(backup) != item["backup_signature"]:
                        raise RuntimeError(
                            f"rollback backup changed; retained at {backup}"
                        )
                    if os.path.lexists(target):
                        raise RuntimeError(
                            f"target is occupied; original retained at {backup}"
                        )

                    # Publish the original without clobbering a target that
                    # appeared after the occupancy check.
                    os.link(backup, target, follow_symlinks=False)
                    os.unlink(backup)
                    temps.discard(backup)
                    item["moved_aside"] = False

            except BaseException as rollback_error:
                retained = ""
                if backup is not None and os.path.lexists(backup):
                    temps.discard(backup)
                    preserved_backups.add(backup)
                    retained = f"; original backup retained at {backup}"
                rollback_errors.append(
                    f"{client} ({requested}): {rollback_error}{retained}"
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
    # Cleanup is best-effort but should not be interrupted by another managed
    # signal. Failed rollback backups were removed from `temps` above.
    previous_cleanup_mask = block_commit_signals()
    try:
        for tmp in list(temps):
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                sys.stderr.write(
                    f"WARNING: could not remove temporary file {tmp}: {cleanup_error}\n"
                )
    finally:
        restore_commit_signals(previous_cleanup_mask)

PY

printf 'Open a fresh agent session to load the updated rules.\n'
