from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

import yaml


@dataclass(frozen=True)
class RepositoryFixture:
    name: str
    path: Path
    initial_head: str


@dataclass
class MaterializedWorkspace:
    root: Path
    repositories: dict[str, RepositoryFixture]
    _tempdir: tempfile.TemporaryDirectory[str]

    def cleanup(self) -> None:
        self._tempdir.cleanup()


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _safe_relative_path(raw: str, label: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError(f"{label} must be a relative path without traversal")
    if not path.parts:
        raise ValueError(f"{label} must not be empty")
    return path


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", ".pytest_cache", ".mypy_cache", ".eval-results"} & set(names)
    directory_path = Path(directory)
    if directory_path.name == ".qiqi":
        ignored |= {"state", "runs", "migration-backups"} & set(names)
    if directory_path.name == "artifacts" and directory_path.parent.name == "evals":
        ignored |= set(names)
    return ignored


class FixtureManager:
    def __init__(self, template_root: Path):
        self.template_root = template_root.resolve()

    def materialize(self, fixture_path: Path) -> MaterializedWorkspace:
        raw = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("fixture must be a mapping")
        unknown = sorted(set(raw) - {"version", "workspace_name", "repositories"})
        if unknown:
            raise ValueError(f"fixture has unsupported fields: {', '.join(unknown)}")
        if raw.get("version") != 1:
            raise ValueError("fixture.version must be 1")
        workspace_name = raw.get("workspace_name", "qiqi-eval")
        if not isinstance(workspace_name, str) or not workspace_name.strip():
            raise ValueError("fixture.workspace_name must be a non-empty string")
        repo_specs = raw.get("repositories")
        if not isinstance(repo_specs, list) or not repo_specs:
            raise ValueError("fixture.repositories must be a non-empty list")

        tempdir = tempfile.TemporaryDirectory(prefix="qiqi-eval-")
        root = Path(tempdir.name) / "workspace"
        shutil.copytree(self.template_root, root, ignore=_copy_ignore)

        state_root = root / ".qiqi" / "state"
        if state_root.exists():
            shutil.rmtree(state_root)
        work_items = root / "work-items"
        work_items.mkdir(parents=True, exist_ok=True)
        for child in list(work_items.iterdir()):
            if child.name != ".gitkeep":
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()

        repositories: dict[str, RepositoryFixture] = {}
        registry_entries: list[dict[str, Any]] = []
        for index, spec_raw in enumerate(repo_specs):
            if not isinstance(spec_raw, dict):
                raise ValueError(f"fixture.repositories[{index}] must be a mapping")
            allowed = {"name", "path", "role", "depends_on", "files"}
            unknown_repo = sorted(set(spec_raw) - allowed)
            if unknown_repo:
                raise ValueError(
                    f"fixture.repositories[{index}] has unsupported fields: {', '.join(unknown_repo)}"
                )
            name = spec_raw.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"fixture.repositories[{index}].name must be non-empty")
            name = name.strip()
            if name in repositories:
                raise ValueError(f"duplicate fixture repository name: {name}")
            rel = _safe_relative_path(
                spec_raw.get("path", f"repos/{name}"), f"fixture.repositories[{index}].path"
            )
            repo = (root / rel).resolve()
            if root not in repo.parents:
                raise ValueError(f"fixture repository escapes workspace: {name}")
            repo.mkdir(parents=True, exist_ok=False)
            files = spec_raw.get("files", {})
            if not isinstance(files, dict):
                raise ValueError(f"fixture.repositories[{index}].files must be a mapping")
            for file_name, content in files.items():
                if not isinstance(file_name, str) or not isinstance(content, str):
                    raise ValueError(
                        f"fixture.repositories[{index}].files must map paths to strings"
                    )
                file_rel = _safe_relative_path(file_name, f"fixture file {file_name!r}")
                destination = (repo / file_rel).resolve()
                if repo != destination and repo not in destination.parents:
                    raise ValueError(f"fixture file escapes repository: {file_name}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")

            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            _run_git(repo, "config", "user.email", "qiqi-eval@example.invalid")
            _run_git(repo, "config", "user.name", "QiQi Eval")
            _run_git(repo, "add", "-A")
            _run_git(repo, "commit", "-q", "-m", "eval fixture baseline")
            initial_head = _run_git(repo, "rev-parse", "HEAD")
            repositories[name] = RepositoryFixture(name=name, path=repo, initial_head=initial_head)
            depends_on = spec_raw.get("depends_on", [])
            if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
                raise ValueError(f"fixture.repositories[{index}].depends_on must be a string list")
            registry_entries.append(
                {
                    "name": name,
                    "path": rel.as_posix(),
                    "role": spec_raw.get("role", "evaluation fixture repository"),
                    "required_for": ["qiqi-eval"],
                    "depends_on": depends_on,
                }
            )

        registry = {
            "workspace": {"name": workspace_name.strip()},
            "repositories": registry_entries,
        }
        (root / "repos.yaml").write_text(
            yaml.safe_dump(registry, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        metadata = {
            "version": 1,
            "fixture": str(fixture_path.resolve()),
            "repositories": {
                name: {"path": str(item.path), "initial_head": item.initial_head}
                for name, item in repositories.items()
            },
        }
        meta_path = root / ".qiqi" / "eval-fixture.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return MaterializedWorkspace(root=root, repositories=repositories, _tempdir=tempdir)
