from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server


class RepositoryRegistryTests(unittest.TestCase):
    def test_sibling_relative_path_resolves_to_exact_git_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            repository = root / "repo-con"
            workspace.mkdir()
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            (workspace / "repos.yaml").write_text(
                """workspace:\n  name: test\nrepositories:\n  - name: repo-con\n    path: ../repo-con\n""",
                encoding="utf-8",
            )

            with patch.object(server, "WORKSPACE_ROOT", workspace):
                self.assertEqual(server._resolve_repo("repo-con"), repository.resolve())

    def test_absolute_repository_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            repository = root / "repo-con"
            workspace.mkdir()
            repository.mkdir()
            (workspace / "repos.yaml").write_text(
                "\n".join(
                    [
                        "workspace:",
                        "  name: test",
                        "repositories:",
                        "  - name: repo-con",
                        f"    path: {repository}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(server, "WORKSPACE_ROOT", workspace):
                with self.assertRaisesRegex(RuntimeError, "path must be relative"):
                    server._load_repo_registry()


if __name__ == "__main__":
    unittest.main()
