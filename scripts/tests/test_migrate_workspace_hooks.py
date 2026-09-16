from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "migrate_workspace.py"
SPEC = importlib.util.spec_from_file_location("migrate_workspace", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
migrate_workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migrate_workspace)

HOOK = b'''#!/usr/bin/env python3
import argparse
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--workspace", required=True)
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()
workspace = Path(args.workspace)
old = workspace / "work-items" / "redmine~1" / "WORK_ITEM.md"
new = workspace / "work-items" / "redmine~1" / "00_WORK_ITEM.md"
if old.exists() and new.exists():
    raise SystemExit("collision")
if old.exists() and not args.dry_run:
    os.replace(old, new)
print("hook-ok")
'''


class WorkspaceMigrationHookTests(unittest.TestCase):
    def make_workspace(self, root: Path) -> Path:
        workspace = root / "workspace"
        dossier = workspace / "work-items" / "redmine~1"
        dossier.mkdir(parents=True)
        (workspace / "scripts").mkdir()
        (dossier / "WORK_ITEM.md").write_text("legacy\n", encoding="utf-8")
        return workspace

    def migration(self) -> dict:
        return {
            "version": 27,
            "to_ref": "target",
            "workspace_hook": "scripts/hook.py",
        }

    def test_preflight_uses_pinned_hook_without_mutating_then_apply_uses_materialized_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.make_workspace(Path(directory))
            migration = self.migration()

            with mock.patch.object(migrate_workspace, "ref_file_exists", return_value=True), mock.patch.object(
                migrate_workspace, "ref_bytes", return_value=HOOK
            ):
                self.assertTrue(
                    migrate_workspace.preflight_workspace_hook(Path(directory), workspace, migration)
                )

            dossier = workspace / "work-items" / "redmine~1"
            self.assertTrue((dossier / "WORK_ITEM.md").is_file())
            self.assertFalse((dossier / "00_WORK_ITEM.md").exists())

            hook_path = workspace / "scripts" / "hook.py"
            hook_path.write_bytes(HOOK)
            migrate_workspace.apply_workspace_hook(workspace, migration, dry_run=False)

            self.assertFalse((dossier / "WORK_ITEM.md").exists())
            self.assertEqual((dossier / "00_WORK_ITEM.md").read_text(encoding="utf-8"), "legacy\n")

    def test_hook_collision_fails_in_preflight_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.make_workspace(Path(directory))
            dossier = workspace / "work-items" / "redmine~1"
            (dossier / "00_WORK_ITEM.md").write_text("current\n", encoding="utf-8")

            with mock.patch.object(migrate_workspace, "ref_file_exists", return_value=True), mock.patch.object(
                migrate_workspace, "ref_bytes", return_value=HOOK
            ):
                self.assertFalse(
                    migrate_workspace.preflight_workspace_hook(
                        Path(directory), workspace, self.migration()
                    )
                )

            self.assertEqual((dossier / "WORK_ITEM.md").read_text(encoding="utf-8"), "legacy\n")
            self.assertEqual((dossier / "00_WORK_ITEM.md").read_text(encoding="utf-8"), "current\n")

    def test_dry_run_apply_does_not_execute_materialized_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.make_workspace(Path(directory))
            hook_path = workspace / "scripts" / "hook.py"
            hook_path.write_bytes(HOOK)

            migrate_workspace.apply_workspace_hook(workspace, self.migration(), dry_run=True)

            dossier = workspace / "work-items" / "redmine~1"
            self.assertTrue((dossier / "WORK_ITEM.md").is_file())
            self.assertFalse((dossier / "00_WORK_ITEM.md").exists())


if __name__ == "__main__":
    unittest.main()
