from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from qiqi_eval.runner import _retain_failed_workspace


class RunnerArtifactTests(unittest.TestCase):
    def test_rerun_replaces_existing_retained_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "artifacts" / "workspace"
            source.mkdir()
            (source / "state.txt").write_text("new\n", encoding="utf-8")
            destination.mkdir(parents=True)
            (destination / "state.txt").write_text("old\n", encoding="utf-8")
            (destination / "stale.txt").write_text("stale\n", encoding="utf-8")

            _retain_failed_workspace(source, destination)

            self.assertEqual(
                (destination / "state.txt").read_text(encoding="utf-8"),
                "new\n",
            )
            self.assertFalse((destination / "stale.txt").exists())


if __name__ == "__main__":
    unittest.main()
