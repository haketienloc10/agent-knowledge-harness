from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
TEMPLATE_PREFIXES = ("workspace-template/", "repo-template/")


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _load_graph_chain() -> list[dict]:
    result: list[dict] = []
    for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]-*.json")):
        migration = json.loads(path.read_text(encoding="utf-8"))
        if migration["version"] >= 28:
            migration["_path"] = path
            result.append(migration)
    return result


class TaskGraphMigrationChainTests(unittest.TestCase):
    def test_graph_era_has_no_unmanaged_template_gap_between_migrations(self) -> None:
        migrations = _load_graph_chain()
        self.assertGreaterEqual(len(migrations), 2)

        for previous, current in zip(migrations, migrations[1:]):
            with self.subTest(previous=previous["version"], current=current["version"]):
                changed = _git(
                    "diff",
                    "--no-renames",
                    "--name-only",
                    previous["to_ref"],
                    current["from_ref"],
                    "--",
                    "workspace-template",
                    "repo-template",
                ).splitlines()
                leaked = [
                    path
                    for path in changed
                    if path.startswith(TEMPLATE_PREFIXES)
                ]
                self.assertEqual(
                    leaked,
                    [],
                    (
                        f"template changes bypass migration coverage between "
                        f"{previous['version']:04d} and {current['version']:04d}: {leaked}"
                    ),
                )

    def test_migration_0029_backfills_phase0_regression_baseline(self) -> None:
        by_version = {item["version"]: item for item in _load_graph_chain()}
        self.assertEqual(by_version[29]["from_ref"], by_version[28]["to_ref"])
        self.assertIn(
            "workspace-template/mcp/qiqi_delegate/tests/test_delegate_repo_task_regression.py",
            by_version[29]["workspace"]["replace"],
        )


if __name__ == "__main__":
    unittest.main()
