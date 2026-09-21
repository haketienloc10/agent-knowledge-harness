from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from qiqi_eval.parent_driver import _load_delegate_server, _workspace_environment


class ParentDriverTests(unittest.TestCase):
    def test_dynamic_delegate_server_registers_module_for_postponed_annotations(self) -> None:
        template_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            target = workspace / "mcp" / "qiqi_delegate"
            target.parent.mkdir(parents=True)
            shutil.copytree(template_root / "mcp" / "qiqi_delegate", target)

            module = None
            with _workspace_environment(workspace):
                module = _load_delegate_server(workspace)
                self.assertIs(sys.modules.get(module.__name__), module)
                self.assertTrue(hasattr(module, "delegate_repo_task"))
                self.assertTrue(hasattr(module, "TrustedFactInput"))
                self.assertTrue(hasattr(module, "TaskContextInput"))

            if module is not None:
                sys.modules.pop(module.__name__, None)


if __name__ == "__main__":
    unittest.main()
