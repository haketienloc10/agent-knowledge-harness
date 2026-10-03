#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
name="ste-vi"
source_skill="$home/skills/$name"
codex_root="${CODEX_HOME:-${HOME}/.codex}/skills"
claude_root="${CLAUDE_CONFIG_DIR:-${HOME}/.claude}/skills"

usage() {
  cat <<'USAGE'
Usage: install-user-skill.sh [--codex-root PATH] [--claude-root PATH]

Installs the managed `ste-vi` Agent Skill for user-scope discovery by
Codex and Claude Code. Existing unrelated skills with the same name are not
silently overwritten. Same-name symlinks and symlinked management markers are
rejected explicitly.
USAGE
}

while (($#)); do
  case "$1" in
    --codex-root) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; codex_root="$2"; shift 2 ;;
    --claude-root) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; claude_root="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: unknown argument: %s\n' "$1" >&2; usage >&2; exit 64 ;;
  esac
done

[[ -f "$source_skill/SKILL.md" ]] || {
  printf 'ERROR: missing source skill: %s/SKILL.md\n' "$source_skill" >&2
  exit 66
}

command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: missing command: python3\n' >&2
  exit 69
}

python3 - "$source_skill" "$name" "$codex_root" "$claude_root" <<'PY'
import ctypes
import errno
import hashlib
import os
import shutil
import signal
import stat
import sys
import tempfile

source_skill, name, raw_codex_root, raw_claude_root = sys.argv[1:5]
marker_name = ".agent-knowledge-harness-managed"


class InstallError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


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


def block_signals():
    if hasattr(signal, "pthread_sigmask"):
        return signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
    return None


def restore_signals(previous):
    if previous is not None:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def normalize_path(raw):
    return os.path.abspath(os.path.expanduser(raw))


def path_components(path):
    path = os.path.abspath(path)
    parts = []
    current = path
    while True:
        parts.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return reversed(parts)


def validate_root_path(client, requested_root):
    for component in path_components(requested_root):
        if not os.path.lexists(component):
            continue
        if os.path.islink(component):
            if not os.path.exists(component):
                raise InstallError(
                    78,
                    f"{client} skill root has a dangling symlink component: {component}",
                )
            if not os.path.isdir(component):
                raise InstallError(
                    78,
                    f"{client} skill root symlink component is not a directory: {component}",
                )
        elif not os.path.isdir(component):
            raise InstallError(
                78,
                f"{client} skill root has a non-directory component: {component}",
            )


def regular_non_symlink(path):
    return os.path.isfile(path) and not os.path.islink(path)


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def tree_fingerprint(root):
    if os.path.islink(root) or not os.path.isdir(root):
        raise RuntimeError(f"not a regular directory: {root}")

    digest = hashlib.sha256()

    def add_entry(relative, path):
        st = os.lstat(path)
        kind = stat.S_IFMT(st.st_mode)
        digest.update(
            (
                f"{relative}\0{kind}\0{stat.S_IMODE(st.st_mode)}\0"
                f"{st.st_dev}\0{st.st_ino}\0{st.st_size}\0"
            ).encode("utf-8", "surrogateescape")
        )
        if stat.S_ISLNK(st.st_mode):
            digest.update(os.readlink(path).encode("utf-8", "surrogateescape"))
        elif stat.S_ISREG(st.st_mode):
            digest.update(file_digest(path).encode("ascii"))

    add_entry(".", root)
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs.sort()
        files.sort()
        for entry in list(dirs):
            path = os.path.join(current, entry)
            relative = os.path.relpath(path, root)
            add_entry(relative, path)
            if os.path.islink(path):
                dirs.remove(entry)
        for entry in files:
            path = os.path.join(current, entry)
            relative = os.path.relpath(path, root)
            add_entry(relative, path)

    return digest.hexdigest()


def tree_content_fingerprint(root):
    if os.path.islink(root) or not os.path.isdir(root):
        raise RuntimeError(f"not a regular directory: {root}")

    digest = hashlib.sha256()

    def add_entry(relative, path):
        st = os.lstat(path)
        kind = stat.S_IFMT(st.st_mode)
        digest.update(
            (
                f"{relative}\0{kind}\0{stat.S_IMODE(st.st_mode)}\0"
            ).encode("utf-8", "surrogateescape")
        )
        if stat.S_ISLNK(st.st_mode):
            digest.update(os.readlink(path).encode("utf-8", "surrogateescape"))
        elif stat.S_ISREG(st.st_mode):
            digest.update(f"{st.st_size}\0".encode("ascii"))
            digest.update(file_digest(path).encode("ascii"))

    add_entry(".", root)
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs.sort()
        files.sort()
        for entry in list(dirs):
            path = os.path.join(current, entry)
            relative = os.path.relpath(path, root)
            add_entry(relative, path)
            if os.path.islink(path):
                dirs.remove(entry)
        for entry in files:
            path = os.path.join(current, entry)
            relative = os.path.relpath(path, root)
            add_entry(relative, path)

    return digest.hexdigest()


def root_signature(path):
    st = os.stat(path, follow_symlinks=True)
    return (st.st_dev, st.st_ino)


def path_overlap(left, right):
    try:
        common = os.path.commonpath([left, right])
    except ValueError:
        return False
    return common in (left, right)


def rename_noreplace(source, target):
    """Rename a directory without replacing a target that appeared in a race."""
    encoded_source = os.fsencode(source)
    encoded_target = os.fsencode(target)
    libc = ctypes.CDLL(None, use_errno=True)

    if sys.platform.startswith("linux"):
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is not None:
            renameat2.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            renameat2.restype = ctypes.c_int
            result = renameat2(
                -100, encoded_source, -100, encoded_target, 1
            )
            if result == 0:
                return
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise FileExistsError(error, os.strerror(error), target)
            if error not in (errno.ENOSYS, errno.EINVAL):
                raise OSError(error, os.strerror(error), target)

    if sys.platform == "darwin":
        renamex_np = getattr(libc, "renamex_np", None)
        if renamex_np is not None:
            renamex_np.argtypes = [
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            renamex_np.restype = ctypes.c_int
            # RENAME_EXCL from <sys/stdio.h>.
            result = renamex_np(encoded_source, encoded_target, 0x00000004)
            if result == 0:
                return
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise FileExistsError(error, os.strerror(error), target)
            if error not in (errno.ENOTSUP, errno.EINVAL):
                raise OSError(error, os.strerror(error), target)

    raise InstallError(
        78,
        "atomic no-replace directory rename is unavailable on this platform; "
        f"refusing to publish {target}",
    )


def ensure_source():
    skill_file = os.path.join(source_skill, "SKILL.md")
    if not regular_non_symlink(skill_file):
        raise InstallError(66, f"missing regular source skill: {skill_file}")
    source_marker = os.path.join(source_skill, marker_name)
    if os.path.lexists(source_marker):
        raise InstallError(
            66,
            f"source skill must not contain installer marker: {source_marker}",
        )


def create_source_snapshot(aux_dirs):
    ensure_source()
    before = tree_content_fingerprint(source_skill)

    previous = block_signals()
    try:
        parent = tempfile.mkdtemp(prefix=".akh-ste-vi-source.")
        aux_dirs.add(parent)
    finally:
        restore_signals(previous)

    snapshot = os.path.join(parent, name)
    shutil.copytree(source_skill, snapshot, symlinks=True)

    after = tree_content_fingerprint(source_skill)
    copied = tree_content_fingerprint(snapshot)
    if before != after or copied != before:
        raise RuntimeError(
            "source skill changed while creating the installation snapshot"
        )
    return snapshot, before


def cleanup_aux_dirs(aux_dirs, warnings):
    previous = block_signals()
    try:
        for path in list(aux_dirs):
            try:
                shutil.rmtree(path)
                aux_dirs.discard(path)
            except FileNotFoundError:
                aux_dirs.discard(path)
            except OSError as exc:
                warnings.append(
                    f"could not remove source snapshot {path}: {exc}"
                )
    finally:
        restore_signals(previous)


def build_state(client, raw_root):
    requested_root = normalize_path(raw_root)
    validate_root_path(client, requested_root)
    physical_root = os.path.realpath(requested_root)
    target = os.path.join(physical_root, name)
    display_target = os.path.join(requested_root, name)
    marker = os.path.join(target, marker_name)

    if os.path.islink(target):
        raise InstallError(
            78,
            f"{client} skill target is a symlink and will not be replaced: {display_target}",
        )
    if os.path.lexists(target) and not os.path.isdir(target):
        raise InstallError(
            78,
            f"{client} skill target exists and is not a directory: {display_target}",
        )

    original_exists = os.path.isdir(target)
    original_fingerprint = None
    if original_exists:
        if not regular_non_symlink(marker):
            detail = (
                "management marker is a symlink"
                if os.path.islink(marker)
                else "management marker is missing or not a regular file"
            )
            raise InstallError(
                78,
                f"{client} skill is not managed by this harness ({detail}): {display_target}",
            )
        original_fingerprint = tree_fingerprint(target)

    return {
        "client": client,
        "requested_root": requested_root,
        "physical_root": physical_root,
        "target": target,
        "display_target": display_target,
        "marker": marker,
        "original_exists": original_exists,
        "original_fingerprint": original_fingerprint,
        "root_existed": os.path.isdir(physical_root),
        "root_signature": (
            root_signature(physical_root) if os.path.isdir(physical_root) else None
        ),
        "stage_parent": None,
        "stage_target": None,
        "stage_fingerprint": None,
        "stage_content_fingerprint": None,
        "no_op": False,
        "backup_parent": None,
        "backup_target": None,
        "backup_fingerprint": None,
        "moved_aside": False,
        "installed": False,
        "installed_fingerprint": None,
        "rollback_failed": False,
        "rollback_current_parent": None,
        "rollback_current_target": None,
        "success_backup_retained": False,
    }


def assert_root_unchanged(state):
    validate_root_path(state["client"], state["requested_root"])
    resolved = os.path.realpath(state["requested_root"])
    if resolved != state["physical_root"]:
        raise RuntimeError(
            f"{state['client']} skill root changed after preflight: "
            f"{state['requested_root']} -> {resolved}"
        )
    if not os.path.isdir(state["physical_root"]):
        raise RuntimeError(
            f"{state['client']} skill root is no longer a directory: "
            f"{state['physical_root']}"
        )
    if state["root_signature"] is not None:
        if root_signature(state["physical_root"]) != state["root_signature"]:
            raise RuntimeError(
                f"{state['client']} skill root identity changed after preflight: "
                f"{state['physical_root']}"
            )


def assert_target_unchanged(state):
    target = state["target"]
    marker = state["marker"]
    if state["original_exists"]:
        if os.path.islink(target) or not os.path.isdir(target):
            raise RuntimeError(
                f"{state['client']} managed skill target changed type: "
                f"{state['display_target']}"
            )
        if not regular_non_symlink(marker):
            raise RuntimeError(
                f"{state['client']} management marker changed after preflight: "
                f"{state['display_target']}"
            )
        if tree_fingerprint(target) != state["original_fingerprint"]:
            raise RuntimeError(
                f"{state['client']} managed skill changed after preflight: "
                f"{state['display_target']}"
            )
    elif os.path.lexists(target):
        raise RuntimeError(
            f"{state['client']} skill target appeared after preflight: "
            f"{state['display_target']}"
        )


def create_tracked_dir(state, key, prefix):
    previous = block_signals()
    try:
        path = tempfile.mkdtemp(dir=state["physical_root"], prefix=prefix)
        state[key] = path
    finally:
        restore_signals(previous)
    return path


def stage_skill(state, source_snapshot, source_snapshot_fingerprint):
    assert_root_unchanged(state)
    if (
        tree_content_fingerprint(source_snapshot)
        != source_snapshot_fingerprint
    ):
        raise RuntimeError("shared source snapshot changed before staging")

    stage_parent = create_tracked_dir(
        state, "stage_parent", f".{name}.stage."
    )
    stage_target = os.path.join(stage_parent, name)
    state["stage_target"] = stage_target

    shutil.copytree(source_snapshot, stage_target, symlinks=True)
    if tree_content_fingerprint(stage_target) != source_snapshot_fingerprint:
        raise RuntimeError(
            f"{state['client']} staged source differs from shared snapshot"
        )

    marker = os.path.join(stage_target, marker_name)
    with open(marker, "xb"):
        pass

    state["stage_fingerprint"] = tree_fingerprint(stage_target)
    state["stage_content_fingerprint"] = tree_content_fingerprint(stage_target)


def mark_noop_if_current(state):
    if not state["original_exists"]:
        return
    assert_root_unchanged(state)
    assert_target_unchanged(state)
    assert_stage_unchanged(state)
    if (
        tree_content_fingerprint(state["target"])
        == state["stage_content_fingerprint"]
    ):
        state["no_op"] = True


def reserve_backup(state):
    if state["no_op"] or not state["original_exists"]:
        return
    backup_parent = create_tracked_dir(
        state, "backup_parent", f".{name}.backup."
    )
    state["backup_target"] = os.path.join(backup_parent, name)


def assert_stage_unchanged(state):
    stage_target = state["stage_target"]
    if (
        stage_target is None
        or os.path.islink(stage_target)
        or not os.path.isdir(stage_target)
        or tree_fingerprint(stage_target) != state["stage_fingerprint"]
    ):
        raise RuntimeError(
            f"{state['client']} staged skill changed before commit"
        )


def commit_one(state):
    if state["no_op"]:
        assert_root_unchanged(state)
        assert_target_unchanged(state)
        if (
            tree_content_fingerprint(state["target"])
            != state["stage_content_fingerprint"]
        ):
            raise RuntimeError(
                f"{state['client']} managed skill changed after no-op detection"
            )
        return

    assert_root_unchanged(state)
    assert_target_unchanged(state)
    assert_stage_unchanged(state)

    previous = block_signals()
    try:
        # Revalidate under the signal mask immediately before mutation.
        assert_root_unchanged(state)
        assert_target_unchanged(state)
        assert_stage_unchanged(state)

        if state["original_exists"]:
            rename_noreplace(state["target"], state["backup_target"])
            state["moved_aside"] = True
            state["backup_fingerprint"] = tree_fingerprint(
                state["backup_target"]
            )

            # Detect a race that changed the target between the pre-check and
            # rename. Rollback can still restore the exact object moved aside,
            # even when it no longer matches the preflight snapshot.
            if (
                state["backup_fingerprint"]
                != state["original_fingerprint"]
            ):
                raise RuntimeError(
                    f"{state['client']} managed skill changed during commit"
                )

        if os.path.lexists(state["target"]):
            raise RuntimeError(
                f"{state['client']} skill target appeared during commit: "
                f"{state['display_target']}"
            )

        # The staged fingerprint is the installer's expected identity.
        # Capture it before publish so a watcher that edits the target immediately
        # after rename cannot redefine externally modified content as "ours".
        expected_installed_fingerprint = state["stage_fingerprint"]
        rename_noreplace(state["stage_target"], state["target"])
        state["installed"] = True
        state["installed_fingerprint"] = expected_installed_fingerprint

        if (
            tree_fingerprint(state["target"])
            != expected_installed_fingerprint
        ):
            raise RuntimeError(
                f"{state['client']} installed skill differs from staged copy"
            )

        os.rmdir(state["stage_parent"])
        state["stage_parent"] = None
        state["stage_target"] = None
    finally:
        restore_signals(previous)


def target_matches_installed(state):
    target = state["target"]
    return (
        os.path.isdir(target)
        and not os.path.islink(target)
        and state["installed_fingerprint"] is not None
        and tree_fingerprint(target) == state["installed_fingerprint"]
    )


def remove_installed_for_rollback(state, errors, retained_backups):
    client = state["client"]
    target = state["target"]

    if not state["installed"]:
        return True
    if not os.path.lexists(target):
        state["installed"] = False
        return True

    parent = create_tracked_dir(
        state, "rollback_current_parent", f".{name}.rollback-current."
    )
    quarantine = os.path.join(parent, name)
    state["rollback_current_target"] = quarantine

    # Move the exact current object away atomically before deciding whether it
    # is still our installed copy. If another process removes the target in the
    # race window, clean the empty rollback parent immediately.
    try:
        rename_noreplace(target, quarantine)
    except FileNotFoundError:
        try:
            os.rmdir(parent)
        except FileNotFoundError:
            pass
        state["rollback_current_parent"] = None
        state["rollback_current_target"] = None
        state["installed"] = False
        return True

    matches_installed = (
        os.path.isdir(quarantine)
        and not os.path.islink(quarantine)
        and state["installed_fingerprint"] is not None
        and tree_fingerprint(quarantine) == state["installed_fingerprint"]
    )
    if matches_installed:
        # A point-in-time fingerprint cannot prove no external writer still has
        # an open descriptor inside this tree. Keep the quarantine instead of
        # deleting it so any late descriptor write remains recoverable.
        retained_backups.add(parent)
        state["installed"] = False
        return True

    # Another process changed the installed target. Put that exact current
    # object back rather than deleting or overwriting it.
    try:
        rename_noreplace(quarantine, target)
        os.rmdir(parent)
        state["rollback_current_parent"] = None
        state["rollback_current_target"] = None
        errors.append(
            f"{client}: installed target changed after commit; "
            "restored the externally changed current target"
        )
    except BaseException as restore_exc:
        retained_backups.add(parent)
        errors.append(
            f"{client}: installed target changed after commit and could not "
            f"be restored ({restore_exc}); current object retained at {quarantine}"
        )

    state["rollback_failed"] = True
    return False


def rollback_one(state, errors, retained_backups):
    client = state["client"]
    target = state["target"]

    if not remove_installed_for_rollback(
        state, errors, retained_backups
    ):
        if state["backup_parent"] and os.path.isdir(state["backup_parent"]):
            retained_backups.add(state["backup_parent"])
        return

    if state["moved_aside"]:
        backup = state["backup_target"]
        if backup is None or not os.path.isdir(backup):
            errors.append(f"{client}: rollback backup is missing")
            state["rollback_failed"] = True
            return

        expected_backup = state["backup_fingerprint"]
        if (
            expected_backup is None
            or tree_fingerprint(backup) != expected_backup
        ):
            errors.append(
                f"{client}: rollback backup changed after it was moved aside; "
                f"retained at {backup}"
            )
            retained_backups.add(state["backup_parent"])
            state["rollback_failed"] = True
            return

        if os.path.lexists(target):
            errors.append(
                f"{client}: target is occupied; original retained at {backup}"
            )
            retained_backups.add(state["backup_parent"])
            state["rollback_failed"] = True
            return

        rename_noreplace(backup, target)
        state["moved_aside"] = False

    if (
        state["backup_parent"]
        and os.path.isdir(state["backup_parent"])
        and state["backup_parent"] not in retained_backups
    ):
        os.rmdir(state["backup_parent"])
        state["backup_parent"] = None
        state["backup_target"] = None
        state["backup_fingerprint"] = None


def cleanup_stage(state, warnings):
    stage_parent = state["stage_parent"]
    if stage_parent and os.path.lexists(stage_parent):
        try:
            shutil.rmtree(stage_parent)
        except OSError as exc:
            warnings.append(
                f"{state['client']}: could not remove staging directory "
                f"{stage_parent}: {exc}"
            )


def cleanup_created_root(state, warnings):
    if state["root_existed"]:
        return
    root = state["physical_root"]
    try:
        os.rmdir(root)
    except FileNotFoundError:
        pass
    except OSError:
        # Keep a non-empty root. It may contain user data or a retained backup.
        pass


def cleanup_success_backups(states, warnings):
    for state in states:
        parent = state["backup_parent"]
        backup = state["backup_target"]
        if not parent or not os.path.lexists(parent):
            continue

        if state["moved_aside"] and backup and os.path.isdir(backup):
            # Do not delete a moved-aside tree after success. Another process may
            # still hold an open descriptor inside it and write after publish.
            # Keeping the backup preserves those late writes for recovery.
            if not state["success_backup_retained"]:
                warnings.append(
                    f"{state['client']}: retained replaced skill backup for "
                    f"descriptor-safe recovery: {parent}"
                )
                state["success_backup_retained"] = True
            continue

        try:
            shutil.rmtree(parent)
            state["backup_parent"] = None
            state["backup_target"] = None
        except OSError as exc:
            warnings.append(
                f"{state['client']}: could not remove completed backup "
                f"directory {parent}: {exc}"
            )


def ensure_roots(states):
    for state in states:
        validate_root_path(state["client"], state["requested_root"])
        current = os.path.realpath(state["requested_root"])
        if current != state["physical_root"]:
            raise RuntimeError(
                f"{state['client']} skill root changed before staging: "
                f"{state['requested_root']} -> {current}"
            )

        os.makedirs(state["physical_root"], exist_ok=True)
        if not os.path.isdir(state["physical_root"]):
            raise RuntimeError(
                f"{state['client']} skill root is not a directory: "
                f"{state['physical_root']}"
            )

        if state["root_signature"] is None:
            state["root_signature"] = root_signature(state["physical_root"])


def reject_source_overlaps(states):
    source_real = os.path.realpath(source_skill)
    for state in states:
        for candidate in (state["physical_root"], state["target"]):
            if path_overlap(candidate, source_real):
                raise InstallError(
                    78,
                    f"{state['client']} skill destination overlaps packaged "
                    f"source skill: {candidate} <-> {source_real}",
                )


def reject_overlaps(states):
    left, right = states
    left_paths = (left["physical_root"], left["target"])
    right_paths = (right["physical_root"], right["target"])
    for left_path in left_paths:
        for right_path in right_paths:
            if path_overlap(left_path, right_path):
                raise InstallError(
                    78,
                    "Codex and Claude skill destinations overlap after path "
                    f"resolution: {left_path} <-> {right_path}",
                )


def run():
    warnings = []
    retained_backups = set()
    aux_dirs = set()
    transaction_complete = False
    states = []

    try:
        source_snapshot, source_snapshot_fingerprint = create_source_snapshot(
            aux_dirs
        )

        states = [
            build_state("Codex", raw_codex_root),
            build_state("Claude", raw_claude_root),
        ]
        reject_overlaps(states)
        reject_source_overlaps(states)
        ensure_roots(states)

        # Both clients stage from the same verified snapshot. Each staged copy
        # must match its content fingerprint, so a repository source change
        # cannot split installed content between clients.
        for state in states:
            stage_skill(
                state, source_snapshot, source_snapshot_fingerprint
            )
            mark_noop_if_current(state)

        # Reserve backup parents only for clients that require replacement.
        for state in states:
            reserve_backup(state)

        for state in states:
            commit_one(state)

        # Verify both published targets before discarding rollback material.
        # A concurrent edit after one client commits therefore turns the whole
        # operation into a rollback attempt instead of a false success.
        for state in states:
            assert_root_unchanged(state)
            if state["no_op"]:
                assert_target_unchanged(state)
                if (
                    tree_content_fingerprint(state["target"])
                    != state["stage_content_fingerprint"]
                ):
                    raise RuntimeError(
                        f"{state['client']} managed skill changed before "
                        "transaction completion"
                    )
            elif not target_matches_installed(state):
                raise RuntimeError(
                    f"{state['client']} installed skill changed before "
                    "transaction completion"
                )

        # Both targets now contain the verified staged skill. From this point
        # onward, interruption must not roll back a successful install.
        transaction_complete = True

        # Block managed signals while deleting rollback material. If a signal
        # was already pending, it may be delivered when the mask is restored;
        # the exception path below sees transaction_complete=True and will not
        # attempt a destructive rollback without backups.
        previous = block_signals()
        try:
            cleanup_success_backups(states, warnings)
            for state in states:
                cleanup_stage(state, warnings)
            cleanup_aux_dirs(aux_dirs, warnings)
        finally:
            restore_signals(previous)

    except BaseException as exc:
        # Keep managed signals blocked for the remainder of error handling.
        # The process is exiting, so there is no need to restore the mask.
        block_signals()

        if transaction_complete:
            # Commit already succeeded for both clients. Never attempt rollback
            # after rollback material may have been deleted.
            cleanup_success_backups(states, warnings)
            for state in states:
                cleanup_stage(state, warnings)
            cleanup_aux_dirs(aux_dirs, warnings)

            for warning in warnings:
                sys.stderr.write(f"WARNING: {warning}\n")
            if isinstance(exc, InstallInterrupted):
                return 128 + exc.signum
            sys.stderr.write(
                f"ERROR: skill install completed but final cleanup failed: {exc}\n"
            )
            return 1

        rollback_errors = []
        for state in reversed(states):
            try:
                rollback_one(state, rollback_errors, retained_backups)
            except BaseException as rollback_exc:
                state["rollback_failed"] = True
                if (
                    state["backup_parent"]
                    and os.path.isdir(state["backup_parent"])
                ):
                    retained_backups.add(state["backup_parent"])
                rollback_errors.append(
                    f"{state['client']}: rollback raised {rollback_exc}"
                )

        for state in states:
            cleanup_stage(state, warnings)
            cleanup_created_root(state, warnings)
        cleanup_aux_dirs(aux_dirs, warnings)

        if rollback_errors:
            sys.stderr.write(
                "ERROR: skill install failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
                + "\n"
            )
        for parent in sorted(retained_backups):
            sys.stderr.write(
                f"ERROR: retained rollback backup for manual recovery: {parent}\n"
            )
        for warning in warnings:
            sys.stderr.write(f"WARNING: {warning}\n")

        if isinstance(exc, InstallInterrupted):
            return 128 + exc.signum
        if isinstance(exc, InstallError):
            sys.stderr.write(f"ERROR: {exc}\n")
            return exc.code
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    for warning in warnings:
        sys.stderr.write(f"WARNING: {warning}\n")
    for state in states:
        print(
            f"{state['client']} skill installed: "
            f"{state['display_target']}/SKILL.md"
        )
    print(
        "Open a fresh agent session if the skill is not already visible "
        "in the skills list."
    )
    return 0


try:
    exit_code = run()
except InstallInterrupted as exc:
    exit_code = 128 + exc.signum
except InstallError as exc:
    sys.stderr.write(f"ERROR: {exc}\n")
    exit_code = exc.code
except BaseException as exc:
    sys.stderr.write(f"ERROR: {exc}\n")
    exit_code = 1

raise SystemExit(exit_code)
PY
