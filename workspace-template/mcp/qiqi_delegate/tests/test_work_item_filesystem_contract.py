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

    def test_codex_and_claude_share_semantic_env_contract(self):
        claude = self.routing["agents"]["claude"]
        self.assertEqual(
            claude["filesystem"]["additional_dirs"],
            [{"env": "QIQI_WORK_ITEMS_DIR", "required": True}],
        )
        codex = self.routing["agents"]["codex"]
        self.assertEqual(codex["command"], "qiqi-codex-agent.sh")
        wrapper = (self.workspace / "scripts" / "qiqi-codex-agent.sh").read_text(encoding="utf-8")
        self.assertIn('codex --add-dir "$QIQI_WORK_ITEMS_DIR"', wrapper)

    def test_current_policy_is_not_work_history(self):
        agents = (self.workspace / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Không persist turn history", agents)
        self.assertIn("Multi-turn continuity", agents)
        self.assertIn("Requirement change", agents)


if __name__ == "__main__":
    unittest.main()
