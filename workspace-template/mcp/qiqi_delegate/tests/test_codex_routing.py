import tomllib
import unittest
from pathlib import Path


class CodexDirectDelegationRoutingTest(unittest.TestCase):
    def test_qiqi_delegate_is_direct_only_code_mode_namespace(self):
        workspace_root = Path(__file__).resolve().parents[3]
        config_path = workspace_root / ".codex" / "config.toml"
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(
            config["features"]["code_mode"]["direct_only_tool_namespaces"],
            ["mcp__qiqi_delegate"],
        )


if __name__ == "__main__":
    unittest.main()
