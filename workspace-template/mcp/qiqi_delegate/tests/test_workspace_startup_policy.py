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
        cls.readme = read_workspace_file("README.md")
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

    def test_graph_qualified_work_cannot_bypass_graph_runtime(self) -> None:
        orchestration = markdown_section(self.agents, "## Orchestration + delegation")
        self.assertIn("### Direct vs Graph execution", orchestration)
        self.assertIn("MUST dùng TaskGraph outer loop", orchestration)
        self.assertIn("scope chạm nhiều repository", orchestration)
        self.assertIn("start_graph", orchestration)
        self.assertIn("delegate_next", orchestration)
        self.assertIn("submit_decisions", orchestration)
        self.assertIn("reconcile_graph", orchestration)
        self.assertIn(
            "không bypass Graph Runtime bằng cách gọi `delegate_repo_task` trực tiếp",
            orchestration,
        )

    def test_route_policy_targets_graph_node_for_graph_execution(self) -> None:
        self.assertIn("GraphNode.route", self.model_routing)
        self.assertIn("direct-vs-Graph orchestration", self.model_routing)
        self.assertIn(
            "GraphNode.route` cho TaskGraph hoặc `delegate_repo_task` cho direct single-repo flow",
            self.model_routing,
        )

    def test_graph_restart_recovery_is_fail_closed_and_narrow(self) -> None:
        orchestration = markdown_section(self.agents, "## Orchestration + delegation")
        self.assertIn("#### Runtime restart recovery", orchestration)
        self.assertIn("code=graph_definition_unavailable", orchestration)
        self.assertIn("fresh TaskGraph cho remaining work", orchestration)
        self.assertIn("recovery bridge cho đúng node đó", orchestration)
        self.assertIn("exact prior `session_id`", orchestration)
        self.assertIn("không mở rộng exception này thành direct orchestration", orchestration)

    def test_workspace_readme_matches_graph_boundary_and_recovery_contract(self) -> None:
        delegation = markdown_section(self.readme, "## Delegation")
        self.assertIn("direct `delegate_repo_task`", delegation)
        self.assertIn("TaskGraph: bắt buộc", delegation)
        self.assertIn("start_graph", delegation)
        self.assertIn("submit_decisions", delegation)
        self.assertIn("code=graph_definition_unavailable", delegation)
        self.assertIn("re-author fresh TaskGraph", delegation)

    def test_blocked_delegation_preserves_resume_identity_before_semantic_read(self) -> None:
        after = markdown_section(self.agents, "## Sau delegation")
        inspect_state = after.index('Inspect runtime `state`')
        blocked = after.index('Nếu `state="blocked"`')
        response = after.index("Nếu turn có native `agent_response`")
        self.assertLess(inspect_state, blocked)
        self.assertLess(blocked, response)
        self.assertIn("giữ exact returned `session_id`", after)
        self.assertIn("không invent blocker/content", after)
        self.assertIn("RESUME exact session", after)


if __name__ == "__main__":
    unittest.main()
