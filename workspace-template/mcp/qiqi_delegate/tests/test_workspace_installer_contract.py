from __future__ import annotations

import unittest
from pathlib import Path


class WorkspaceInstallerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace_root = Path(__file__).resolve().parents[3]
        cls.harness_root = cls.workspace_root.parent
        cls.installer = (
            cls.harness_root / "scripts" / "setup-workspace.sh"
        ).read_text(encoding="utf-8")
        cls.work_item_installer = (
            cls.harness_root / "work-item-template" / "scripts" / "install-workspace-skill.sh"
        ).read_text(encoding="utf-8")
        cls.knowledge_installer = (
            cls.harness_root / "knowledge-template" / "scripts" / "install-user-mcp.sh"
        ).read_text(encoding="utf-8")

    def test_installer_exposes_independent_client_and_route_choices(self) -> None:
        self.assertIn("--coordinators claude|codex|both", self.installer)
        self.assertIn("--agents claude|codex|both", self.installer)
        self.assertIn("--default-route claude|codex", self.installer)
        self.assertIn("QiQi coordinator clients", self.installer)
        self.assertIn("Herdr execution agents", self.installer)
        self.assertIn("Default delegation route", self.installer)

    def test_current_main_work_item_is_workspace_skill_not_mcp(self) -> None:
        self.assertIn("work-item-template/scripts/install-workspace-skill.sh", self.installer)
        self.assertIn('--clients "$coordinators"', self.installer)
        self.assertNotIn("work-item-template/scripts/install-user-mcp.sh", self.installer)
        self.assertIn("removed legacy Work Item MCP", self.installer)
        self.assertIn("--clients claude|codex|both", self.work_item_installer)

    def test_knowledge_is_registered_for_union_of_parent_and_execution_clients(self) -> None:
        self.assertIn('knowledge_clients="both"', self.installer)
        self.assertIn("knowledge-template/scripts/install-user-mcp.sh", self.installer)
        self.assertIn('--clients "$knowledge_clients"', self.installer)
        self.assertIn("--clients available|claude|codex|both", self.knowledge_installer)

    def test_claude_child_only_topology_is_first_class(self) -> None:
        self.assertIn('scripts/setup-claude.sh" --children-only', self.installer)
        self.assertIn('herdr integration install claude', self.installer)
        self.assertIn('herdr integration install codex', self.installer)

    def test_installer_persists_machine_local_route_preference(self) -> None:
        self.assertIn(".qiqi/config.local.json", self.installer)
        self.assertIn('"coordinators"', self.installer)
        self.assertIn('"execution_agents"', self.installer)
        self.assertIn('"default_route"', self.installer)
        self.assertIn("claude-balanced", self.installer)
        self.assertIn("codex-balanced", self.installer)

    def test_model_routing_honors_local_preference_only_for_delegation(self) -> None:
        policy = (
            self.workspace_root / "instructions" / "model-routing.md"
        ).read_text(encoding="utf-8")
        self.assertIn(".qiqi/config.local.json", policy)
        self.assertIn("execution_agents", policy)
        self.assertIn("default_route", policy)
        self.assertIn("Turn không delegate **không đọc**", policy)
        self.assertIn("fallback = claude-balanced", policy)


if __name__ == "__main__":
    unittest.main()
