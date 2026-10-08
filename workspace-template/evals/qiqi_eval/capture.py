from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Any

from .fixture import MaterializedWorkspace
from .scenario import VerificationCommand


@dataclass(frozen=True)
class VerificationResult:
    repo: str
    command: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(repo: Path, args: list[str]) -> str:
    completed = subprocess.run(args, cwd=repo, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def repository_evidence(workspace: MaterializedWorkspace) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for name, fixture in workspace.repositories.items():
        tracked = _run(
            fixture.path,
            ["git", "diff", "--name-only", fixture.initial_head, "--"],
        ).splitlines()
        untracked = _run(
            fixture.path,
            ["git", "ls-files", "--others", "--exclude-standard"],
        ).splitlines()
        changed_files = sorted({item for item in [*tracked, *untracked] if item})
        status = _run(fixture.path, ["git", "status", "--porcelain=v1"])
        evidence[name] = {
            "path": str(fixture.path),
            "initial_head": fixture.initial_head,
            "final_head": _run(fixture.path, ["git", "rev-parse", "HEAD"]),
            "changed_files": changed_files,
            "status": status.splitlines() if status else [],
        }
    return evidence


def _dump_sqlite(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.is_file():
        return {}
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        available = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        allowed = {
            "sessions",
            "turns",
            "graph_runs",
            "graph_node_states",
            "graph_attempts",
        }
        result: dict[str, list[dict[str, Any]]] = {}
        for table in sorted(available & allowed):
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            decoded: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                for key, value in list(item.items()):
                    if key.endswith("_json") and isinstance(value, str):
                        try:
                            item[key] = json.loads(value)
                        except json.JSONDecodeError:
                            pass
                decoded.append(item)
            result[table] = decoded
        return result
    finally:
        conn.close()


def runtime_evidence(workspace_root: Path) -> dict[str, Any]:
    db = workspace_root / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
    return {"database": str(db), "tables": _dump_sqlite(db)}


def work_item_evidence(workspace_root: Path) -> dict[str, Any]:
    root = workspace_root / "work-items"
    if not root.is_dir():
        return {"files": []}
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != ".gitkeep":
            files.append(str(path.relative_to(root)))
    return {"files": files}


def run_verification(
    workspace: MaterializedWorkspace,
    commands: tuple[VerificationCommand, ...],
) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    for item in commands:
        fixture = workspace.repositories.get(item.repo)
        if fixture is None:
            results.append(
                VerificationResult(
                    repo=item.repo,
                    command=item.command,
                    returncode=127,
                    stdout="",
                    stderr="unknown fixture repository",
                )
            )
            continue
        try:
            completed = subprocess.run(
                item.command,
                cwd=fixture.path,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=item.timeout_seconds,
            )
            results.append(
                VerificationResult(
                    repo=item.repo,
                    command=item.command,
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            )
        except subprocess.TimeoutExpired as exc:
            results.append(
                VerificationResult(
                    repo=item.repo,
                    command=item.command,
                    returncode=124,
                    stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                    stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
                    timed_out=True,
                )
            )
    return results
