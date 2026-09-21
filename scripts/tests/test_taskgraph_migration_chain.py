from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
TEMPLATE_PREFIXES = ("workspace-template/", "repo-template/")
PHASE0_REGRESSION = (
    "workspace-template/mcp/qiqi_delegate/tests/"
    "test_delegate_repo_task_regression.py"
)
KNOWN_REPAIRED_GAPS = {
    (28, 29): {PHASE0_REGRESSION},
}


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


def _managed_template_paths(migration: dict) -> set[str]:
    return {
        path
        for scope in ("workspace", "repo")
        for strategy in ("merge", "replace", "delete")
        for path in migration[scope][strategy]
    }


def _template_diff(base: str, head: str) -> set[str]:
    return {
        path
        for path in _git(
            "diff",
            "--no-renames",
            "--name-only",
            base,
            head,
            "--",
            "workspace-template",
            "repo-template",
        ).splitlines()
        if path.startswith(TEMPLATE_PREFIXES)
    }


class TaskGraphMigrationChainTests(unittest.TestCase):
    def test_graph_era_has_no_unrepaired_template_gap_between_migrations(self) -> None:
        migrations = _load_graph_chain()
        self.assertGreaterEqual(len(migrations), 2)
        by_version = {item["version"]: item for item in migrations}

        for previous, current in zip(migrations, migrations[1:]):
            pair = (previous["version"], current["version"])
            with self.subTest(previous=pair[0], current=pair[1]):
                leaked = _template_diff(previous["to_ref"], current["from_ref"])
                expected = KNOWN_REPAIRED_GAPS.get(pair, set())
                self.assertEqual(
                    leaked,
                    expected,
                    (
                        "unexpected template changes bypass migration coverage between "
                        f"{pair[0]:04d} and {pair[1]:04d}: {sorted(leaked)}"
                    ),
                )

        repair = by_version[41]
        repaired_paths = _managed_template_paths(repair)
        for pair, paths in KNOWN_REPAIRED_GAPS.items():
            with self.subTest(repair_for=pair):
                self.assertTrue(
                    paths <= repaired_paths,
                    f"migration 0041 does not repair historical gap {pair}: {sorted(paths)}",
                )

    def test_historical_migration_0029_remains_immutable(self) -> None:
        by_version = {item["version"]: item for item in _load_graph_chain()}
        self.assertNotEqual(by_version[29]["from_ref"], by_version[28]["to_ref"])
        self.assertNotIn(PHASE0_REGRESSION, _managed_template_paths(by_version[29]))

    def test_latest_migration_target_is_ancestor_and_has_no_unmanaged_tail(self) -> None:
        latest = _load_graph_chain()[-1]
        subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "merge-base",
                "--is-ancestor",
                latest["to_ref"],
                "HEAD",
            ],
            check=True,
        )
        tail = _template_diff(latest["to_ref"], "HEAD")
        self.assertEqual(
            tail,
            set(),
            f"template changes after migration {latest['version']:04d} lack a migration: {sorted(tail)}",
        )


if __name__ == "__main__":
    unittest.main()
