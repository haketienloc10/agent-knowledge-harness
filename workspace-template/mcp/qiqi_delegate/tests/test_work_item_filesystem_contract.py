from pathlib import Path
import unittest
import yaml


class WorkItemFilesystemContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = Path(__file__).resolve().parents[3]
        cls.routing = yaml.safe_load(
            (cls.workspace / "instructions" / "agent-routing.yaml").read_text(encoding="utf-8")
        )

    def test_workspace_has_precreated_work_items_directory_marker(self):
        self.assertTrue((self.workspace / "work-items" / ".gitkeep").is_file())

    def test_codex_and_claude_share_native_filesystem_contract(self):
        expected = [{"env": "QIQI_WORK_ITEMS_DIR", "required": True}]
        codex = self.routing["agents"]["codex"]
        claude = self.routing["agents"]["claude"]

        self.assertEqual(codex["command"], "codex")
        self.assertEqual(claude["command"], "claude")
        self.assertEqual(codex["filesystem"]["additional_dirs"], expected)
        self.assertEqual(claude["filesystem"]["additional_dirs"], expected)
        self.assertFalse((self.workspace / "scripts" / "qiqi-codex-agent.sh").exists())

    def test_parent_work_item_policy_does_not_require_child_env(self):
        agents = (self.workspace / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<workspace>/work-items", agents)
        self.assertIn("parent không phụ thuộc vào env do MCP child export", agents)
        self.assertIn("delegated-runtime mount alias", agents)

    def test_current_policy_is_not_work_history(self):
        agents = (self.workspace / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Không persist turn history", agents)
        self.assertIn("Multi-turn continuity", agents)
        self.assertIn("Requirement change", agents)


if __name__ == "__main__":
    unittest.main()
