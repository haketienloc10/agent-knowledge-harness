#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


MIN_PYTHON = (3, 8)


def die(message: str) -> "None":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_supported_python() -> None:
    if sys.version_info < MIN_PYTHON:
        current = ".".join(str(part) for part in sys.version_info[:3])
        die(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required; current interpreter is {current}")


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True, text: bool = True):
    result = subprocess.run(cmd, cwd=cwd, text=text, capture_output=True)
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        die(f"command failed ({' '.join(cmd)}): {detail}")
    return result


def git(root: Path, *args: str, check: bool = True):
    return run(["git", "-C", str(root), *args], check=check)


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        die(f"missing required command: {name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate a QiQi workspace and its child repositories.")
    parser.add_argument("workspace_path")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="archive and replace merge-conflicting managed files")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--to-version", type=int)
    args = parser.parse_args()
    if args.to_version is not None and args.to_version < 0:
        parser.error("--to-version must be non-negative")
    if args.dry_run and args.verify:
        parser.error("--verify cannot be combined with --dry-run")
    return args


def migration_number(path: Path) -> int:
    head = path.name.split("-", 1)[0]
    if len(head) != 4 or not head.isdigit():
        die(f"invalid migration filename: {path.name}")
    return int(head)


def load_migrations(directory: Path) -> list[dict]:
    paths = sorted(directory.glob("[0-9][0-9][0-9][0-9]-*.json"))
    if not paths:
        die(f"no migration definitions found in {directory}")
    migrations: list[dict] = []
    for expected, path in enumerate(paths, 1):
        version = migration_number(path)
        if version != expected:
            die(f"migration sequence gap: expected {expected:04d}, found {version:04d}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != version:
            die(f"VERSION mismatch in {path.name}")
        for key in ("from_ref", "to_ref", "description", "workspace", "repo"):
            if key not in data:
                die(f"missing {key} in {path.name}")
        for scope in ("workspace", "repo"):
            for strategy in ("merge", "replace", "delete", "manual_review"):
                value = data[scope].get(strategy)
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    die(f"{path.name}: {scope}.{strategy} must be an array of strings")
        data["_path"] = path
        migrations.append(data)
    return migrations


def read_repo_paths(workspace: Path) -> list[str]:
    require_command("yq")
    version = run(["yq", "--version"]).stdout
    if "version v4." not in version and "version 4." not in version:
        die("yq v4 is required")
    result = run(["yq", "-r", ".repositories[].path", str(workspace / "repos.yaml")])
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip() and line.strip() != "null"]
    if not paths:
        die("repos.yaml must contain at least one repository")
    if len(paths) != len(set(paths)):
        die("repos.yaml contains duplicate repository paths")
    return paths


def resolve_repo_roots(workspace: Path, repo_paths: list[str]) -> list[Path]:
    roots: list[Path] = []
    for rel in repo_paths:
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts:
            die(f"repository path must be relative and must not contain '..': {rel}")
        root = (workspace / path).resolve()
        if not root.is_dir():
            die(f"repository path does not exist: {rel}")
        resolved = Path(git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
        if resolved != root:
            die(f"repository path is not the exact Git root: {rel}")
        roots.append(root)
    return roots


def read_state(path: Path) -> dict[str, int]:
    state: dict[str, int] = {}
    if not path.exists():
        return state
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw:
            continue
        parts = raw.split("\t")
        if len(parts) != 2 or not parts[1].isdigit():
            die(f"invalid migration state row: {raw}")
        state[parts[0]] = int(parts[1])
    return state


def write_state(path: Path, state: dict[str, int], repo_paths: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"workspace\t{state.get('workspace', 0)}"]
    rows.extend(f"repo:{rel}\t{state.get(f'repo:{rel}', 0)}" for rel in repo_paths)
    fd, temp_name = tempfile.mkstemp(prefix=".migrations.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(rows) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def ref_exists(harness: Path, ref: str) -> bool:
    return git(harness, "cat-file", "-e", f"{ref}^{{commit}}", check=False).returncode == 0


def ref_file_exists(harness: Path, ref: str, source: str) -> bool:
    return git(harness, "cat-file", "-e", f"{ref}:{source}", check=False).returncode == 0


def ref_bytes(harness: Path, ref: str, source: str) -> bytes:
    result = subprocess.run(["git", "-C", str(harness), "show", f"{ref}:{source}"], capture_output=True)
    if result.returncode:
        die(f"cannot read {source} at {ref}")
    return result.stdout


def ref_mode(harness: Path, ref: str, source: str) -> int:
    output = git(harness, "ls-tree", ref, "--", source).stdout.strip()
    if not output:
        die(f"cannot determine mode for {source} at {ref}")
    mode = output.split()[0]
    if mode == "100644":
        return 0o644
    if mode == "100755":
        return 0o755
    die(f"unsupported Git mode {mode} for {source} at {ref}")


def regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def target_matches_ref(harness: Path, target: Path, ref: str, source: str) -> bool:
    if not regular_file(target) or not ref_file_exists(harness, ref, source):
        return False
    if target.read_bytes() != ref_bytes(harness, ref, source):
        return False
    expected_exec = bool(ref_mode(harness, ref, source) & 0o111)
    actual_exec = bool(target.stat().st_mode & stat.S_IXUSR)
    return expected_exec == actual_exec


def diff_status(harness: Path, migration: dict, source: str) -> str:
    result = git(harness, "diff", "--no-renames", "--name-status", migration["from_ref"], migration["to_ref"], "--", source)
    rows = [line for line in result.stdout.splitlines() if line]
    if len(rows) != 1:
        die(f"migration manifest path must have exactly one diff row: {source}")
    status, changed = rows[0].split("\t", 1)
    if changed != source:
        die(f"unexpected diff path for {source}: {changed}")
    return status


def assert_strategy_status(strategy: str, status: str, source: str) -> None:
    allowed = {"merge": {"M"}, "replace": {"A", "M"}, "delete": {"D"}}
    if status not in allowed[strategy]:
        die(f"migration strategy '{strategy}' does not match Git status '{status}' for {source}")


def relative_source(prefix: str, source: str) -> Path:
    marker = prefix + "/"
    if not source.startswith(marker):
        die(f"migration path outside {prefix}: {source}")
    return Path(source[len(marker):])


def backup_path(workspace: Path, key: str, version: int, relative: Path) -> Path:
    base = workspace / ".qiqi" / "migration-backups" / f"v{version:04d}"
    if key == "workspace":
        return base / "workspace" / relative
    repo_prefix = "repo:"
    if not key.startswith(repo_prefix):
        die(f"invalid migration scope key: {key}")
    return base / "repos" / key[len(repo_prefix):] / relative


def check_backup(source: Path, backup: Path) -> bool:
    if not regular_file(source):
        print(f"CONFLICT: {source}\n  cannot archive non-regular path safely.", file=sys.stderr)
        return False
    if not backup.exists() and not backup.is_symlink():
        return True
    if regular_file(backup) and source.read_bytes() == backup.read_bytes():
        return True
    print(f"CONFLICT: {backup}\n  migration backup already exists with different content/type.", file=sys.stderr)
    return False


def copy_backup(source: Path, backup: Path) -> None:
    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists() or backup.is_symlink():
        if not regular_file(backup) or source.read_bytes() != backup.read_bytes():
            die(f"migration backup already exists with different content: {backup}")
        return
    shutil.copy2(source, backup)


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".migrate.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def render_merge(harness: Path, migration: dict, source: str, target: Path) -> tuple[int, bytes]:
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        current = tmp / "current"
        base = tmp / "base"
        incoming = tmp / "incoming"
        current.write_bytes(target.read_bytes())
        base.write_bytes(ref_bytes(harness, migration["from_ref"], source))
        incoming.write_bytes(ref_bytes(harness, migration["to_ref"], source))
        result = subprocess.run([
            "git", "merge-file", "-p",
            "-L", f"local:{source}",
            "-L", f"template-base:{source}",
            "-L", f"template-target:{source}",
            str(current), str(base), str(incoming),
        ], capture_output=True)
        return result.returncode, result.stdout


def preflight_file(harness: Path, workspace: Path, migration: dict, key: str, prefix: str, root: Path, strategy: str, source: str, force: bool) -> bool:
    status = diff_status(harness, migration, source)
    assert_strategy_status(strategy, status, source)
    relative = relative_source(prefix, source)
    target = root / relative
    version = migration["version"]

    if strategy in {"merge", "replace"}:
        ref_mode(harness, migration["to_ref"], source)

    if strategy == "merge":
        if (not target.exists() and not target.is_symlink()) or target_matches_ref(harness, target, migration["from_ref"], source) or target_matches_ref(harness, target, migration["to_ref"], source):
            return True
        if regular_file(target):
            rc, _ = render_merge(harness, migration, source, target)
            if rc == 0:
                return True
        if force and regular_file(target):
            return check_backup(target, backup_path(workspace, key, version, relative))
        print(f"CONFLICT: {target}\n  local edits overlap template changes; automatic three-way merge has conflicts.\n  merge it manually or rerun with --force to archive local content and replace it.", file=sys.stderr)
        return False

    if strategy == "replace":
        if (not target.exists() and not target.is_symlink()) or target_matches_ref(harness, target, migration["from_ref"], source) or target_matches_ref(harness, target, migration["to_ref"], source):
            return True
        return check_backup(target, backup_path(workspace, key, version, relative))

    if strategy == "delete":
        if (not target.exists() and not target.is_symlink()) or target_matches_ref(harness, target, migration["from_ref"], source):
            return True
        return check_backup(target, backup_path(workspace, key, version, relative))

    die(f"unknown strategy: {strategy}")


def apply_file(harness: Path, workspace: Path, migration: dict, key: str, prefix: str, root: Path, strategy: str, source: str, force: bool, dry_run: bool) -> None:
    relative = relative_source(prefix, source)
    target = root / relative
    backup = backup_path(workspace, key, migration["version"], relative)
    incoming = migration["to_ref"]
    base = migration["from_ref"]

    if strategy == "merge":
        if target_matches_ref(harness, target, incoming, source):
            print(f"  = {relative}")
        elif (not target.exists() and not target.is_symlink()) or target_matches_ref(harness, target, base, source):
            print(f"  + {relative}")
            if not dry_run:
                atomic_write(target, ref_bytes(harness, incoming, source), ref_mode(harness, incoming, source))
        elif force:
            print(f"  B {relative} -> {backup.relative_to(workspace)}")
            print(f"  + {relative} (force replace)")
            if not dry_run:
                copy_backup(target, backup)
                atomic_write(target, ref_bytes(harness, incoming, source), ref_mode(harness, incoming, source))
        else:
            rc, merged = render_merge(harness, migration, source, target)
            if rc != 0:
                die(f"unexpected merge failure after preflight: {target}")
            print(f"  ~ {relative} (clean 3-way merge)")
            if not dry_run:
                atomic_write(target, merged, ref_mode(harness, incoming, source))
        return

    if strategy == "replace":
        if target_matches_ref(harness, target, incoming, source):
            print(f"  = {relative}")
        elif (not target.exists() and not target.is_symlink()) or target_matches_ref(harness, target, base, source):
            print(f"  + {relative}")
            if not dry_run:
                atomic_write(target, ref_bytes(harness, incoming, source), ref_mode(harness, incoming, source))
        else:
            print(f"  B {relative} -> {backup.relative_to(workspace)}")
            print(f"  + {relative} (replace template-owned artifact)")
            if not dry_run:
                copy_backup(target, backup)
                atomic_write(target, ref_bytes(harness, incoming, source), ref_mode(harness, incoming, source))
        return

    if strategy == "delete":
        if not target.exists() and not target.is_symlink():
            print(f"  = {relative} (already absent)")
        elif target_matches_ref(harness, target, base, source):
            print(f"  - {relative}")
            if not dry_run:
                target.unlink()
        else:
            print(f"  B {relative} -> {backup.relative_to(workspace)}")
            print(f"  - {relative}")
            if not dry_run:
                copy_backup(target, backup)
                target.unlink()
        return


def scope_config(migration: dict, prefix: str) -> dict:
    return migration["workspace" if prefix == "workspace-template" else "repo"]


def preflight_scope(harness: Path, workspace: Path, migration: dict, key: str, prefix: str, root: Path, force: bool) -> bool:
    ok = True
    config = scope_config(migration, prefix)
    for strategy in ("merge", "replace", "delete"):
        for source in config[strategy]:
            ok = preflight_file(harness, workspace, migration, key, prefix, root, strategy, source, force) and ok
    return ok


def apply_scope(harness: Path, workspace: Path, migration: dict, key: str, prefix: str, root: Path, force: bool, dry_run: bool) -> None:
    action = "dry-run" if dry_run else "apply"
    print(f"{key}: {action} migration {migration['version']} - {migration['description']}")
    config = scope_config(migration, prefix)
    for strategy in ("merge", "replace", "delete"):
        for source in config[strategy]:
            apply_file(harness, workspace, migration, key, prefix, root, strategy, source, force, dry_run)
    if config["manual_review"]:
        print(f"{key}: manual review (not overwritten automatically):")
        for source in config["manual_review"]:
            print(f"  ! {relative_source(prefix, source)}")


def main() -> int:
    require_supported_python()
    args = parse_args()
    for name in ("git", "yq"):
        require_command(name)

    script_dir = Path(__file__).resolve().parent
    harness = Path(git(script_dir.parent, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if not (harness / "workspace-template").is_dir() or not (harness / "repo-template").is_dir():
        die(f"invalid harness checkout: {harness}")

    workspace = Path(args.workspace_path).expanduser().resolve()
    if not workspace.is_dir() or not (workspace / "repos.yaml").is_file():
        die(f"workspace is missing or has no repos.yaml: {workspace}")

    migrations = load_migrations(harness / "migrations")
    latest = migrations[-1]["version"]
    target_version = latest if args.to_version is None else args.to_version
    if target_version > latest:
        die(f"requested version {target_version} exceeds latest migration {latest}")

    repo_paths = read_repo_paths(workspace)
    repo_roots = resolve_repo_roots(workspace, repo_paths)
    state_path = workspace / ".qiqi" / "agent-knowledge-harness-migrations.tsv"
    state = read_state(state_path)

    if args.status:
        print(f"Harness migrations: latest={latest} target={target_version}")
        print(f"workspace\t{state.get('workspace', 0)}")
        for rel in repo_paths:
            print(f"repo:{rel}\t{state.get(f'repo:{rel}', 0)}")
        return 0

    for migration in migrations:
        version = migration["version"]
        if version > target_version:
            continue
        if not ref_exists(harness, migration["from_ref"]) or not ref_exists(harness, migration["to_ref"]):
            die(f"migration {version} references unavailable Git commits")

        scopes: list[tuple[str, str, Path]] = []
        if state.get("workspace", 0) < version:
            scopes.append(("workspace", "workspace-template", workspace))
        for rel, root in zip(repo_paths, repo_roots):
            key = f"repo:{rel}"
            if state.get(key, 0) < version:
                scopes.append((key, "repo-template", root))
        if not scopes:
            continue

        failed = False
        for key, prefix, root in scopes:
            print(f"{key}: preflight migration {version} - {migration['description']}")
            if not preflight_scope(harness, workspace, migration, key, prefix, root, args.force):
                failed = True
        if failed:
            die(f"migration {version} has conflicts; no files for this migration were changed")

        for key, prefix, root in scopes:
            apply_scope(harness, workspace, migration, key, prefix, root, args.force, args.dry_run)
            state[key] = version

    if args.verify:
        print("verification: workspace")
        run(["bash", str(workspace / "scripts" / "workspace-check.sh")], cwd=workspace, check=True)
        for root in repo_roots:
            print(f"verification: {root}")
            run(["bash", str(root / "scripts" / "repo-check.sh")], cwd=root, check=True)

    if args.dry_run:
        print(f"dry-run complete; migration state remains unchanged at {state_path}")
    else:
        write_state(state_path, state, repo_paths)
        print(f"migration complete; state recorded at {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())