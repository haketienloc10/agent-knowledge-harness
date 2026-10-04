from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from qiqi_eval.fixture import FixtureManager


class FixtureTests(unittest.TestCase):
    def test_each_materialization_is_clean_and_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "template"
            template.mkdir()
            (template / "work-items").mkdir()
            (template / "repos.yaml").write_text("repositories: []\n", encoding="utf-8")
            fixture = root / "fixture.yaml"
            fixture.write_text(
                """version: 1
workspace_name: demo
repositories:
  - name: repo-a
    path: repos/repo-a
    files:
      file.txt: |
        baseline
""",
                encoding="utf-8",
            )
            manager = FixtureManager(template)
            first = manager.materialize(fixture)
            second = manager.materialize(fixture)
            try:
                first_file = first.repositories["repo-a"].path / "file.txt"
                second_file = second.repositories["repo-a"].path / "file.txt"
                first_file.write_text("changed\n", encoding="utf-8")
                self.assertEqual(second_file.read_text(encoding="utf-8"), "baseline\n")
                self.assertNotEqual(first.root, second.root)
                self.assertTrue(first.repositories["repo-a"].initial_head)
            finally:
                first.cleanup()
                second.cleanup()


if __name__ == "__main__":
    unittest.main()
