from __future__ import annotations

import json
import unittest
from pathlib import Path


class ClaudeWorkspaceConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace_root = Path(__file__).resolve().parents[3]
        cls.setup_script = (
            cls.workspace_root / "scripts" / "setup-claude.sh"
        ).read_text(encoding="utf-8")

    def test_workspace_uses_claude_project_instructions_without_ancestor_files(self) -> None:
        claude_md = self.workspace_root / ".claude" / "CLAUDE.md"
        if claude_md.exists():
            self.assertEqual(claude_md.read_text(encoding="utf-8"), "@../AGENTS.md\n")
        else:
            self.assertIn("@../AGENTS.md", self.setup_script)
        self.assertFalse(
            (self.workspace_root / "CLAUDE.md").exists(),
            "workspace-root CLAUDE.md would leak coordinator policy into nested repo children",
        )
        self.assertFalse(
            (self.workspace_root / ".mcp.json").exists(),
            "qiqi_delegate must not be project-scoped through workspace/.mcp.json",
        )

    def test_workspace_disables_coordinator_auto_memory_and_allows_delegate_tool(self) -> None:
        settings_path = self.workspace_root / ".claude" / "settings.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertIs(settings.get("autoMemoryEnabled"), False)
            self.assertEqual(
                settings.get("env", {}).get("CLAUDE_CODE_DISABLE_AUTO_MEMORY"),
                "1",
            )
            allow = settings.get("permissions", {}).get("allow", [])
            self.assertIn("mcp__qiqi_delegate__delegate_repo_task", allow)
        else:
            self.assertIn('data["autoMemoryEnabled"] = False', self.setup_script)
            self.assertIn(
                'env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"', self.setup_script
            )
            self.assertIn(
                'tool = "mcp__qiqi_delegate__delegate_repo_task"', self.setup_script
            )

    def test_setup_registers_qiqi_delegate_at_local_scope_only(self) -> None:
        self.assertIn("claude mcp add --scope local", self.setup_script)
        self.assertIn("qiqi_delegate", self.setup_script)
        self.assertIn("scripts/qiqi-mcp-server.sh", self.setup_script)
        self.assertIn('data["autoMemoryEnabled"] = False', self.setup_script)
        self.assertIn(
            'env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"', self.setup_script
        )
        self.assertIn("@../AGENTS.md", self.setup_script)
        self.assertNotIn("--scope project", self.setup_script)
        self.assertNotIn("--scope user", self.setup_script)

    def test_setup_supports_child_only_execution_agent_mode(self) -> None:
        self.assertIn("--children-only", self.setup_script)
        self.assertIn("children_only=1", self.setup_script)
        self.assertIn("Claude Code child isolation configured", self.setup_script)

    def test_setup_generates_machine_local_child_exclusion(self) -> None:
        self.assertIn("settings.local.json", self.setup_script)
        self.assertIn("claudeMdExcludes", self.setup_script)
        self.assertIn("workspace_claude_md", self.setup_script)
        self.assertIn(".git/info/exclude", self.setup_script)
        self.assertIn(".claude/settings.local.json", self.setup_script)
        self.assertIn(
            'env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"', self.setup_script
        )

    def test_delegate_server_disables_claude_child_auto_memory(self) -> None:
        text = (self.workspace_root / "scripts" / "qiqi-mcp-server.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("export CLAUDE_CODE_DISABLE_AUTO_MEMORY=1", text)


if __name__ == "__main__":
    unittest.main()
