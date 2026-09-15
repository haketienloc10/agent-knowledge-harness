from __future__ import annotations

import unittest
from pathlib import Path


class CodexMcpConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace_root = Path(__file__).resolve().parents[3]
        cls.config_path = cls.workspace_root / ".codex" / "config.toml"

    def test_qiqi_delegate_forwards_claude_additional_dir_env(self) -> None:
        text = self.config_path.read_text(encoding="utf-8")
        heading = "[mcp_servers.qiqi_delegate]"
        start = text.index(heading)
        next_section = text.find("\n[", start + len(heading))
        section = text[start:] if next_section < 0 else text[start:next_section]

        self.assertIn(
            'env_vars = ["QIQI_CLAUDE_ADDITIONAL_DIR"]',
            section,
            "Codex must forward QIQI_CLAUDE_ADDITIONAL_DIR to qiqi_delegate stdio MCP",
        )


if __name__ == "__main__":
    unittest.main()
