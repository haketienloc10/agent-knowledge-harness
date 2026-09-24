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
        cls.codex_config = read_workspace_file(".codex/config.toml")

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

    def test_qiqi_delegates_repo_discovery_but_allows_exact_bounded_reconciliation_read(self) -> None:
        boundary = markdown_section(self.agents, "## Repository discovery boundary")

        self.assertIn("control plane", boundary)
        self.assertIn("Repository child sở hữu discovery/investigation/implementation/verification", boundary)
        self.assertIn("MUST NOT mặc định chạy `rg`/`grep`/`find`", boundary)
        self.assertIn("broad code search", boundary)
        self.assertIn("exact bounded source locator", boundary)
        self.assertIn("smallest exact range", boundary)
        self.assertIn("không từ bounded read mở rộng sang search", boundary)
        self.assertIn("delegate question đó", boundary)
        self.assertIn("direct delegation và TaskGraph", boundary)

        self.assertIn("delegate discovery cho repository child", self.identity)
        self.assertIn("không mở rộng bounded read thành grep/search/call-chain investigation", self.identity)

    def test_taskgraph_progressive_disclosure_keeps_parent_context_compact(self) -> None:
        orchestration = markdown_section(self.agents, "## Orchestration + delegation")
        self.assertIn("TaskGraph progressive disclosure", orchestration)
        self.assertIn("smallest sufficient current surface", orchestration)
        self.assertIn("get_node_review", orchestration)
        self.assertIn("get_node_reviews", orchestration)
        self.assertIn("bounded", orchestration)
        self.assertIn("hard maximum 8", orchestration)
        self.assertIn("submit_decisions", orchestration)
        self.assertIn("just-in-time", orchestration)
        self.assertIn("upstream đã accepted", orchestration)
        self.assertIn("không hydrate accepted nodes như routine context", orchestration)
        self.assertIn("không xóa execution evidence khỏi store", orchestration)

    def test_work_item_startup_hydration_is_bounded_phase_aware_and_scope_locked(self) -> None:
        startup = markdown_section(self.agents, "## Startup")
        work_item = markdown_section(self.agents, "## Work Item")

        self.assertIn("bounded `00_WORK_ITEM.md` bootstrap", startup)
        self.assertIn("current-turn objective/acceptance slice", startup)
        self.assertIn("phase-aware matrix", startup)
        self.assertIn("không full-read dossier như startup ceremony", startup)

        self.assertIn("current-turn objective/acceptance slice", work_item)
        self.assertIn("Stable investigation follow-up", work_item)
        self.assertIn("không hydrate `10_intake.md`, planning hoặc review material mặc định", work_item)
        self.assertIn("Material requirement change", work_item)
        self.assertIn("Planning/review material chỉ hydrate", work_item)
        self.assertIn("truncation", work_item)
        self.assertIn("incomplete coverage", work_item)
        self.assertIn("output_budget_exceeded", work_item)

        scope_lock = startup.index("current-turn objective/acceptance slice")
        optional_hydration = startup.index("optional lifecycle material")
        self.assertLess(scope_lock, optional_hydration)

    def test_capture_review_tool_is_enabled_for_ambiguous_delegation(self) -> None:
        self.assertIn('"get_turn_capture_review"', self.codex_config)
        self.assertIn('"delegate_repo_task"', self.codex_config)
        self.assertIn('"get_node_review"', self.codex_config)

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
