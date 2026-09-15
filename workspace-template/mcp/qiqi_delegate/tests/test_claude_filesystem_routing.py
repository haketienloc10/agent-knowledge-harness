import os
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from server import _build_filesystem_args, _load_execution_config


class ClaudeFilesystemRoutingTests(unittest.TestCase):
    def test_claude_uses_common_required_work_items_env(self):
        agents, _ = _load_execution_config()
        self.assertEqual(
            agents["claude"]["filesystem"]["additional_dirs"],
            [{"env": "QIQI_WORK_ITEMS_DIR", "required": True}],
        )

    def test_common_work_items_env_becomes_add_dir(self):
        agents, _ = _load_execution_config()
        with tempfile.TemporaryDirectory() as directory:
            previous = os.environ.get("QIQI_WORK_ITEMS_DIR")
            os.environ["QIQI_WORK_ITEMS_DIR"] = directory
            try:
                self.assertEqual(
                    _build_filesystem_args(agents["claude"]),
                    ["--add-dir", str(Path(directory).resolve())],
                )
            finally:
                if previous is None:
                    os.environ.pop("QIQI_WORK_ITEMS_DIR", None)
                else:
                    os.environ["QIQI_WORK_ITEMS_DIR"] = previous


if __name__ == "__main__":
    unittest.main()
