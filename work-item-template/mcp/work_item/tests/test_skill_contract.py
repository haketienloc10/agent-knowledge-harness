from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


TEMPLATE_ROOT = Path(__file__).resolve().parents[3]
SKILL = TEMPLATE_ROOT / "skills" / "work-item" / "SKILL.md"
INSTALLER = TEMPLATE_ROOT / "scripts" / "install-user-skill.sh"
MCP_INSTALLER = TEMPLATE_ROOT / "scripts" / "install-user-mcp.sh"


class WorkItemSkillContractTests(unittest.TestCase):
    def test_skill_preserves_operational_contract_without_auto_opt_in(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        lowered = text.lower()

        for required in (
            "name: work-item",
            "operational protocol for global work item mcp",
            "do not decide that a generic",
            "before any `work_item_*` tool call",
            "work_item_get(id)",
            "work_item_create",
            "expected_revision",
            "arrays replace atomically",
            "revision conflict: reread → reconcile → retry",
            "current effective repo truth",
            "accumulated material phase/milestone history",
            "artifact creation never substitutes",
            "implementation **must reconcile the work item even when no artifact is created**",
            "review detail belongs in a review artifact",
            "a report artifact is presentation/detail",
            "questions[]",
            "decisions[]",
            "changes[]",
            "## before final",
        ):
            self.assertIn(required, lowered)

        self.assertNotIn("ticket-work-item", lowered)
        self.assertIn("role authority still comes from the active `agents.md`", lowered)

    def test_main_mcp_installer_installs_shared_skill(self) -> None:
        text = MCP_INSTALLER.read_text(encoding="utf-8")
        self.assertIn("managed user-scope `work-item` Agent Skill", text)
        self.assertIn('bash "$home/scripts/install-user-skill.sh"', text)
        self.assertIn("user/global MCP registration and skill", text)

    def test_user_skill_installer_installs_exact_managed_copy_for_both_clients(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            codex_root = root / "codex"
            claude_root = root / "claude"
            cmd = [
                "bash",
                str(INSTALLER),
                "--codex-root",
                str(codex_root),
                "--claude-root",
                str(claude_root),
            ]

            first = subprocess.run(cmd, text=True, capture_output=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr or first.stdout)

            for skill_root in (codex_root, claude_root):
                target = skill_root / "work-item"
                self.assertEqual(
                    (target / "SKILL.md").read_text(encoding="utf-8"),
                    SKILL.read_text(encoding="utf-8"),
                )
                self.assertTrue((target / ".agent-knowledge-harness-managed").is_file())

            second = subprocess.run(cmd, text=True, capture_output=True, check=False)
            self.assertEqual(second.returncode, 0, second.stderr or second.stdout)

    def test_user_skill_installer_refuses_unmanaged_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            codex_root = root / "codex"
            claude_root = root / "claude"
            conflict = codex_root / "work-item"
            conflict.mkdir(parents=True)
            (conflict / "SKILL.md").write_text("unmanaged\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "bash",
                    str(INSTALLER),
                    "--codex-root",
                    str(codex_root),
                    "--claude-root",
                    str(claude_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 78)
            self.assertIn("not managed by this harness", result.stderr)


if __name__ == "__main__":
    unittest.main()
