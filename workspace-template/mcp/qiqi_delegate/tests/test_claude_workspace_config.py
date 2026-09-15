from __future__ import annotations

import json
import unittest
from pathlib import Path


class ClaudeWorkspaceConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace_root = Path(__file__).resolve().parents[3]

    def test_workspace_uses_claude_project_instructions_without_root_mcp_json(self) -> None:
        claude_md = self.workspace_root / ".claude" / "CLAUDE.md"
        self.assertEqual(claude_md.read_text(encoding="utf-8"), "@../AGENTS.md\n")
        self.assertFalse(
            (self.workspace_root / ".mcp.json").exists(),
            "qiqi_delegate must not be project-scoped through workspace/.mcp.json",
        )

    def test_workspace_disables_coordinator_auto_memory_and_allows_delegate_tool(self) -> None:
        settings = json.loads(
            (self.workspace_root / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        self.assertIs(settings.get("autoMemoryEnabled"), False)
        allow = settings.get("permissions", {}).get("allow", [])
        self.assertIn("mcp__qiqi_delegate__delegate_repo_task", allow)

    def test_setup_registers_qiqi_delegate_at_local_scope_only(self) -> None:
        text = (self.workspace_root / "scripts" / "setup-claude.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("claude mcp add --scope local", text)
        self.assertIn("qiqi_delegate", text)
        self.assertIn("scripts/qiqi-mcp-server.sh", text)
        self.assertNotIn("--scope project", text)
        self.assertNotIn("--scope user", text)

    def test_delegate_server_disables_claude_child_auto_memory(self) -> None:
        text = (self.workspace_root / "scripts" / "qiqi-mcp-server.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("export CLAUDE_CODE_DISABLE_AUTO_MEMORY=1", text)


if __name__ == "__main__":
    unittest.main()
