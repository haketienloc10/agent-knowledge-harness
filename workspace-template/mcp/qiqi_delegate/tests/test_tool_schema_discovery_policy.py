from pathlib import Path
import unittest


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


class ToolSchemaDiscoveryPolicyTests(unittest.TestCase):
    def test_dynamic_discovery_is_exact_and_bounded(self) -> None:
        agents = (WORKSPACE_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        start = agents.index("## Dynamic tool-schema discovery\n")
        end = agents.index("\n## ", start + 4)
        policy = agents[start:end]

        self.assertIn("smallest sufficient exact tool schema", policy)
        self.assertIn("exact tool name", policy)
        self.assertIn("narrow discovery", policy)
        self.assertIn("sibling tools", policy)
        self.assertIn('ALL_TOOLS.filter(...includes("knowledge_"))', policy)
        self.assertIn('ALL_TOOLS.filter(...includes("work_item_"))', policy)
        self.assertIn("không thay đổi semantic protocol", policy)


if __name__ == "__main__":
    unittest.main()
