from pathlib import Path
import unittest


class CodexMcpConfigTests(unittest.TestCase):
    def test_qiqi_delegate_does_not_depend_on_external_work_items_env_forwarding(self):
        workspace_root = Path(__file__).resolve().parents[3]
        text = (workspace_root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('args = ["scripts/qiqi-mcp-server.sh"]', text)
        self.assertNotIn("env_vars", text)
        self.assertNotIn("QIQI_CLAUDE_ADDITIONAL_DIR", text)

    def test_launcher_owns_only_delegated_work_items_env(self):
        workspace_root = Path(__file__).resolve().parents[3]
        text = (workspace_root / "scripts" / "qiqi-mcp-server.sh").read_text(encoding="utf-8")
        self.assertIn('work_items_dir="$workspace_root/work-items"', text)
        self.assertIn('export QIQI_WORK_ITEMS_DIR="$work_items_dir"', text)
        self.assertIn("Parent QiQi/$work-item", text)
        self.assertNotIn('export PATH="$workspace_root/scripts:$PATH"', text)


if __name__ == "__main__":
    unittest.main()
