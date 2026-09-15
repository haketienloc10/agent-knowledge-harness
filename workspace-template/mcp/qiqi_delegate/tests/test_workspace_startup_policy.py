from pathlib import Path
import re
import unittest


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def read_workspace_file(relative_path: str) -> str:
    return (WORKSPACE_ROOT / relative_path).read_text(encoding="utf-8")


def markdown_section(text: str, heading: str) -> str:
    start = text.index(f"{heading}\n")
    next_heading = text.find("\n## ", start + len(heading) + 1)
    return text[start:] if next_heading < 0 else text[start:next_heading]


class WorkspaceStartupPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.agents = read_workspace_file("AGENTS.md")
        cls.model_routing = read_workspace_file("instructions/model-routing.md")

    def test_model_routing_is_lazy_but_mandatory_before_actual_delegation(self) -> None:
        startup = markdown_section(self.agents, "## Startup")

        self.assertIn("không phải mandatory startup read", startup)
        self.assertIn("Default delegation route = `claude-balanced`", startup)
        self.assertIn("Turn không delegate không hydrate route policy", startup)
        self.assertIn("just-in-time ngay trước route decision", startup)
        self.assertNotRegex(
            startup,
            re.compile(r"(?m)^\d+\.\s+Đọc `instructions/model-routing\.md`"),
        )

        self.assertIn("**không phải mandatory startup material**", self.model_routing)
        self.assertIn("đọc file này ngay trước route decision", self.model_routing)
        self.assertIn("Default delegation route = claude-balanced", self.model_routing)

    def test_orchestration_preserves_deterministic_default(self) -> None:
        orchestration = markdown_section(self.agents, "## Orchestration + delegation")
        self.assertIn("Default delegation route = `claude-balanced`", orchestration)
        self.assertIn("đọc `instructions/model-routing.md`", orchestration)
        self.assertIn("fallback/default", orchestration)


if __name__ == "__main__":
    unittest.main()
