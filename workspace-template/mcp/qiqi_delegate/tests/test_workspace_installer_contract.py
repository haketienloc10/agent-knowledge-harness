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

    def test_installer_exposes_coordinator_agent_and_default_route_choices(self) -> None:
        self.assertIn("--coordinators claude|codex|both", self.installer)
        self.assertIn("--agents claude|codex|both", self.installer)
        self.assertIn("--default-route claude|codex", self.installer)
        self.assertIn("Coordinator clients", self.installer)
        self.assertIn("Herdr execution agents", self.installer)
        self.assertIn("Default delegation route", self.installer)

    def test_installer_owns_global_mcp_and_runtime_setup(self) -> None:
        self.assertIn("work-item-template/scripts/install-user-mcp.sh", self.installer)
        self.assertIn("knowledge-template/scripts/install-user-mcp.sh", self.installer)
        self.assertIn('--clients "$mcp_clients"', self.installer)
        self.assertIn("scripts/setup-claude.sh", self.installer)
        self.assertIn("--children-only", self.installer)
        self.assertIn("codex mcp get qiqi_delegate", self.installer)
        self.assertIn("herdr integration install claude", self.installer)
        self.assertIn("herdr integration install codex", self.installer)

    def test_installer_persists_machine_local_route_preference(self) -> None:
        self.assertIn(".qiqi/config.local.json", self.installer)
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
        self.assertIn("Không đọc `.qiqi/config.local.json` cho turn không delegate", policy)


if __name__ == "__main__":
    unittest.main()
