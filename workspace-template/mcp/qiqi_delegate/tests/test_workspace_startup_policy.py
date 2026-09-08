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
        cls.identity = read_workspace_file("identity.md")
        cls.model_routing = read_workspace_file("instructions/model-routing.md")

    def test_model_routing_is_not_an_unconditional_startup_read(self) -> None:
        startup = markdown_section(self.agents, "## Khởi động QiQi")

        self.assertIn("không phải mandatory startup read", startup)
        self.assertIn("Default delegation route = `claude-balanced`", startup)
        self.assertIn("Turn không delegate không hydrate route policy", startup)
        self.assertNotRegex(
            startup,
            re.compile(r"(?m)^\d+\.\s+Đọc `instructions/model-routing\.md`\.?$"),
        )

    def test_every_actual_delegation_hydrates_route_policy_just_in_time(self) -> None:
        startup = markdown_section(self.agents, "## Khởi động QiQi")
        before_delegation = markdown_section(self.agents, "## Trước delegation")

        self.assertIn("Khi một turn thực sự cần delegation", startup)
        self.assertIn("just-in-time ngay trước route decision", startup)
        self.assertIn("không yêu cầu QiQi đoán exception signal", startup)

        self.assertIn("Đọc `instructions/model-routing.md` ngay trước route decision", before_delegation)
        self.assertIn("exact route nhẹ nhất vẫn đủ tin cậy", before_delegation)
        self.assertIn("`claude-balanced` là fallback/default", before_delegation)

        self.assertIn("**không phải mandatory startup material**", self.model_routing)
        self.assertIn("Turn không delegate **không đọc** file này", self.model_routing)
        self.assertIn("đọc file này ngay trước route decision", self.model_routing)
        self.assertIn("Không yêu cầu always-on policy tự nhận diện trước", self.model_routing)
        self.assertIn("Default delegation route = claude-balanced", self.model_routing)

    def test_identity_dedup_preserves_always_on_semantic_boundaries(self) -> None:
        for required in (
            "Global Work Item MCP",
            "Knowledge MCP",
            "Repo source/test",
            "qiqi_delegate state",
            "referential closure",
            "smallest sufficient semantic scope",
            "knowledge_read_metadata",
            "knowledge_read_section",
            "material use/update",
            "delegate_repo_task",
            "TaskPacket phải tự đủ",
            "hidden QiQi conversation",
            "child tự đọc/sửa sibling repo",
        ):
            self.assertIn(required, self.identity)

        for duplicated_operational_detail in (
            "work_item_get",
            "work_item_update",
            "agent_response",
            "settled | failed | blocked",
        ):
            self.assertNotIn(duplicated_operational_detail, self.identity)

    def test_status_only_startup_does_not_require_route_policy_material(self) -> None:
        startup = markdown_section(self.agents, "## Khởi động QiQi")
        mandatory_reads = re.findall(r"(?m)^\d+\.\s+Đọc `([^`]+)`", startup)

        self.assertEqual(mandatory_reads, ["identity.md", "repos.yaml"])
        self.assertNotIn("instructions/model-routing.md", mandatory_reads)


if __name__ == "__main__":
    unittest.main()
