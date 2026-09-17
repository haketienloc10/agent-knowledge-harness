from __future__ import annotations

import unittest
from pathlib import Path


class ClaudeWorkspaceConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace_root = Path(__file__).resolve().parents[3]
        cls.setup_script = (
            cls.workspace_root / "scripts" / "setup-claude.sh"
        ).read_text(encoding="utf-8")

    def test_template_does_not_prebake_claude_project_or_mcp_files(self) -> None:
        self.assertFalse(
            (self.workspace_root / "CLAUDE.md").exists(),
            "workspace-root CLAUDE.md would leak coordinator policy into nested repos",
        )
        self.assertFalse(
            (self.workspace_root / ".mcp.json").exists(),
            "qiqi_delegate must not be project-scoped through workspace/.mcp.json",
        )
        self.assertFalse(
            (self.workspace_root / ".claude" / "CLAUDE.md").exists(),
            "Claude coordinator adapter must be generated only when Claude is selected",
        )
        self.assertFalse(
            (self.workspace_root / ".claude" / "settings.json").exists(),
            "Claude coordinator settings must be generated only when Claude is selected",
        )

    def test_setup_registers_qiqi_delegate_at_claude_local_scope_only(self) -> None:
        self.assertIn("claude mcp add --scope local", self.setup_script)
        self.assertIn("scripts/qiqi-mcp-server.sh", self.setup_script)
        self.assertIn("@../AGENTS.md", self.setup_script)
        self.assertNotIn("--scope project", self.setup_script)
        self.assertNotIn("claude mcp add --scope user", self.setup_script)

    def test_coordinator_setup_disables_auto_memory(self) -> None:
        self.assertIn('data["autoMemoryEnabled"] = False', self.setup_script)
        self.assertIn(
            'env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"', self.setup_script
        )
        self.assertIn(
            'tool = "mcp__qiqi_delegate__delegate_repo_task"', self.setup_script
        )

    def test_setup_supports_child_only_execution_agent_mode(self) -> None:
        self.assertIn("--children-only", self.setup_script)
        self.assertIn("children_only=1", self.setup_script)
        self.assertIn("Claude Code child isolation configured", self.setup_script)

    def test_child_isolation_is_machine_local_and_worktree_safe(self) -> None:
        self.assertIn("settings.local.json", self.setup_script)
        self.assertIn("claudeMdExcludes", self.setup_script)
        self.assertIn("workspace_claude_md", self.setup_script)
        self.assertIn("ls-files --error-unmatch", self.setup_script)
        self.assertIn("rev-parse --git-path info/exclude", self.setup_script)
        self.assertIn(
            'env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"', self.setup_script
        )
        self.assertNotIn("/tmp/qiqi-claude-e2e", self.setup_script)


if __name__ == "__main__":
    unittest.main()
