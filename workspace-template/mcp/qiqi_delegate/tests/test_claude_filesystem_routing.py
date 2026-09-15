import os
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from server import _build_filesystem_args, _load_execution_config


class SharedFilesystemRoutingTests(unittest.TestCase):
    def test_codex_and_claude_use_common_required_work_items_env(self):
        agents, _ = _load_execution_config()
        expected = [{"env": "QIQI_WORK_ITEMS_DIR", "required": True}]
        self.assertEqual(agents["codex"]["filesystem"]["additional_dirs"], expected)
        self.assertEqual(agents["claude"]["filesystem"]["additional_dirs"], expected)

    def test_common_work_items_env_becomes_native_add_dir_for_both_adapters(self):
        agents, _ = _load_execution_config()
        with tempfile.TemporaryDirectory() as directory:
            previous = os.environ.get("QIQI_WORK_ITEMS_DIR")
            os.environ["QIQI_WORK_ITEMS_DIR"] = directory
            try:
                expected = ["--add-dir", str(Path(directory).resolve())]
                self.assertEqual(_build_filesystem_args(agents["codex"]), expected)
                self.assertEqual(_build_filesystem_args(agents["claude"]), expected)
            finally:
                if previous is None:
                    os.environ.pop("QIQI_WORK_ITEMS_DIR", None)
                else:
                    os.environ["QIQI_WORK_ITEMS_DIR"] = previous


if __name__ == "__main__":
    unittest.main()
