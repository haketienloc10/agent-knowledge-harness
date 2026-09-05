from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


TEMPLATE_ROOT = Path(__file__).resolve().parents[3]
SKILL = TEMPLATE_ROOT / "skills" / "work-item" / "SKILL.md"
INSTALLER = TEMPLATE_ROOT / "scripts" / "install-user-skill.sh"
MCP_INSTALLER = TEMPLATE_ROOT / "scripts" / "install-user-mcp.sh"
CLI_DOC = TEMPLATE_ROOT / "CLI.md"
README = TEMPLATE_ROOT / "README.md"


class WorkItemSkillContractTests(unittest.TestCase):
    def test_skill_preserves_qiqi_side_operational_contract(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        lowered = text.lower()

        for required in (
            "name: work-item",
            "operational protocol for global work item mcp",
            "qiqi/orchestration side",
            "do not make work item a repository-child execution dependency",
            "before any qiqi `work_item_*` call",
            "work_item_get(id)",
            "work_item_history_read",
            "work_item_create",
            "workitemmutation",
            "mutation.state",
            "mutation.operations",
            "decision_upsert[]",
            "question_upsert[]",
            "change_upsert[]",
            "blocker_upsert[]",
            "handoff_upsert[]",
            "checkpoint_append[]",
            "at most 50 semantic records total",
            "all-or-nothing",
            "server does not auto-rebase",
            "compact receipt",
            "revision conflict: reread → reconcile → retry",
            "## taskpacket delegation boundary",
            "objective",
            "scope[]",
            "acceptance_criteria[]",
            "trusted_facts",
            "claims_to_investigate",
            "does **not** contain normal child-facing",
            "work_item_id / work_item_revision",
            "user_request",
            "verification command",
            "material semantics must survive distillation",
            "immutable semantic snapshot",
            "stale execution result **must not become current truth**",
            "runtime state (`settled`, `failed`, `blocked`",
            "it is **not semantic completion truth**",
            "do not add a second child-authored semantic status",
            "qiqi is the semantic interpreter/reconciliation layer",
            "artifact creation/finalization does not replace canonical work item reconciliation",
            "## before final qiqi response",
        ):
            self.assertIn(required, lowered)

        self.assertNotIn("ticket-work-item", lowered)
        self.assertNotIn("operations are applied in caller order", lowered)
        self.assertNotIn('"op": "checkpoint_append"', lowered)
        self.assertNotIn("child `work_item_get`", lowered)
        self.assertNotIn("taskpacket identifies a work item", lowered)

    def test_common_path_avoids_redundant_parent_inference_turns(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()

        for required in (
            "do **not** call `work_item_list` before `work_item_get(id)`",
            "successful `work_item_create` response is the authoritative current snapshot",
            "do not immediately reread it",
            "preserve the exact revision that produced the delegated taskpacket",
            "prefer optimistic cas",
            "delegated `expected_revision`",
            "update success proves the canonical revision stayed unchanged through commit",
            "revision conflict means stale risk",
            "routine repo-specific completion",
            "does **not** by itself require shared knowledge review",
            "do not read `$knowledge-distill`",
            "knowledge_write(entries=[])",
        ):
            self.assertIn(required, text)

        self.assertLessEqual(
            len(SKILL.read_bytes()),
            7000,
            "work-item skill exceeded the reviewed always-hydrated token budget",
        )

    def test_child_facing_taskpacket_does_not_require_work_item_identity(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()
        taskpacket = text.split("## taskpacket delegation boundary", 1)[1]
        self.assertIn("work_item_id / work_item_revision", taskpacket)
        self.assertIn("does **not** contain", taskpacket)
        self.assertIn("if child would need work item dereference", taskpacket)
        self.assertIn("taskpacket is incomplete", taskpacket)

    def test_main_mcp_installer_installs_qiqi_side_skill_without_child_dependency(self) -> None:
        text = MCP_INSTALLER.read_text(encoding="utf-8")
        lowered = text.lower()
        self.assertIn("managed user-scope `work-item` Agent Skill", text)
        self.assertIn("QiQi/orchestration", text)
        self.assertIn('bash "$home/scripts/install-user-skill.sh"', text)
        self.assertIn("user/global MCP registration and skill", text)
        self.assertIn("repo-local TaskPacket execution must not depend", text)
        self.assertNotIn("for qiqi/repository agents", lowered)
        self.assertNotIn("shared by qiqi and repository execution agents", lowered)

    def test_cli_and_readme_preserve_public_ownership_and_tool_names(self) -> None:
        cli = CLI_DOC.read_text(encoding="utf-8").lower()
        readme = README.read_text(encoding="utf-8")
        self.assertIn("work item store mà qiqi sử dụng qua mcp", cli)
        self.assertIn("repository child không dùng store này", cli)
        self.assertNotIn("qiqi và repository agents sử dụng qua mcp", cli)
        self.assertIn("work_item_artifact_list", readme)
        self.assertIn("work_item_artifact_get", readme)
        self.assertIn("work_item_artifact_read", readme)
        self.assertNotIn("\nartifact_list\n→ artifact_get", readme)

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
