from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MAPPING = {
    "WORK_ITEM.md": "00_WORK_ITEM.md",
    "intake.md": "10_intake.md",
    "investigation.md": "20_investigation.md",
    "plan.md": "30_plan.md",
    "review.md": "40_review.md",
    "report.textile": "90_report.textile",
}


class WorkItemFilenameMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace_template = Path(__file__).resolve().parents[3]
        cls.script = cls.workspace_template / "scripts" / "migrate-work-item-filenames-v27.py"

    def make_workspace(self, root: Path) -> Path:
        workspace = root / "multi-repo"
        workspace.mkdir()
        (workspace / "repos.yaml").write_text("repositories: []\n", encoding="utf-8")
        (workspace / "identity.md").write_text("name: test\n", encoding="utf-8")
        (workspace / "work-items").mkdir()
        return workspace

    def run_migration(self, workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.script), "--workspace", str(workspace), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def seed_legacy_dossier(self, workspace: Path) -> Path:
        dossier = workspace / "work-items" / "redmine~111605"
        dossier.mkdir()
        for old_name in MAPPING:
            (dossier / old_name).write_text(f"content:{old_name}\n", encoding="utf-8")
        references = dossier / "references"
        references.mkdir()
        (references / "spec.pdf.txt").write_text("reference\n", encoding="utf-8")
        return dossier

    def test_dry_run_then_migrate_is_ordered_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.make_workspace(Path(directory))
            dossier = self.seed_legacy_dossier(workspace)

            dry_run = self.run_migration(workspace, "--dry-run")
            self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
            for old_name, new_name in MAPPING.items():
                self.assertTrue((dossier / old_name).is_file())
                self.assertFalse((dossier / new_name).exists())

            result = self.run_migration(workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            for old_name, new_name in MAPPING.items():
                self.assertFalse((dossier / old_name).exists())
                self.assertEqual(
                    (dossier / new_name).read_text(encoding="utf-8"),
                    f"content:{old_name}\n",
                )
            self.assertEqual(
                (dossier / "references" / "spec.pdf.txt").read_text(encoding="utf-8"),
                "reference\n",
            )

            second = self.run_migration(workspace)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("already current", second.stdout)

    def test_old_new_collision_fails_before_any_rename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.make_workspace(Path(directory))
            dossier = self.seed_legacy_dossier(workspace)
            (dossier / "00_WORK_ITEM.md").write_text("new\n", encoding="utf-8")

            result = self.run_migration(workspace)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((dossier / "WORK_ITEM.md").is_file())
            self.assertTrue((dossier / "intake.md").is_file())
            self.assertFalse((dossier / "10_intake.md").exists())

    def test_dangling_symlink_fails_before_any_rename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.make_workspace(Path(directory))
            dossier = self.seed_legacy_dossier(workspace)
            (dossier / "review.md").unlink()
            (dossier / "review.md").symlink_to(dossier / "missing-review.md")

            result = self.run_migration(workspace)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((dossier / "WORK_ITEM.md").is_file())
            self.assertTrue((dossier / "intake.md").is_file())
            self.assertFalse((dossier / "00_WORK_ITEM.md").exists())
            self.assertFalse((dossier / "10_intake.md").exists())


if __name__ == "__main__":
    unittest.main()
