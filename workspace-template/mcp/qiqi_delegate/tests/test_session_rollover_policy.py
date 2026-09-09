from pathlib import Path
import unittest


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def read_workspace_file(relative_path: str) -> str:
    return (WORKSPACE_ROOT / relative_path).read_text(encoding="utf-8")


def markdown_section(text: str, heading: str) -> str:
    start = text.index(f"{heading}\n")
    next_heading = text.find("\n## ", start + len(heading) + 1)
    return text[start:] if next_heading < 0 else text[start:next_heading]


class SessionRolloverPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.agents = read_workspace_file("AGENTS.md")
        cls.model_routing = read_workspace_file("instructions/model-routing.md")
        cls.rollover = markdown_section(cls.agents, "## START/RESUME")
        cls.before_delegation = markdown_section(cls.agents, "## Trước delegation")

    def test_known_session_id_does_not_imply_resume(self) -> None:
        self.assertIn("Known `session_id` tự nó **không phải** lý do để RESUME", self.rollover)
        self.assertIn("RESUME cần một affirmative continuity reason", self.rollover)
        self.assertIn("**START fresh mặc định**", self.rollover)
        self.assertIn("immediate follow-up vẫn cùng narrow objective", self.rollover)

    def test_blocked_and_preserved_recovery_keep_exact_session(self) -> None:
        self.assertIn("previous call `blocked` trước native final response", self.rollover)
        self.assertIn("preserved resume key", self.rollover)

        after_delegation = markdown_section(self.agents, "## Sau delegation")
        self.assertIn("Với `blocked`, `agent_response=null`", after_delegation)
        self.assertIn("Giữ exact `session_id`", after_delegation)

    def test_independent_verifier_starts_fresh_even_on_same_native_family(self) -> None:
        self.assertIn("Independent verifier/reviewer **MUST START fresh by default**", self.rollover)
        self.assertIn("cùng underlying native agent family", self.rollover)

        verifier_start = self.model_routing.index("### `claude-verifier`")
        verifier_end = self.model_routing.index("### `codex-balanced`", verifier_start)
        verifier = self.model_routing[verifier_start:verifier_end]
        self.assertIn("**MUST START fresh by default**", verifier)
        self.assertIn("cùng underlying native agent family", verifier)

    def test_rollover_decision_precedes_taskpacket_referential_closure(self) -> None:
        choose_mode = self.before_delegation.index("Chọn START/RESUME")
        finalize_closure = self.before_delegation.index("finalize referential closure")
        delegate = self.before_delegation.index("Delegate bằng `delegate_repo_task`")

        self.assertLess(choose_mode, finalize_closure)
        self.assertLess(finalize_closure, delegate)

    def test_rollover_does_not_require_runtime_state_polling(self) -> None:
        self.assertIn("QiQi không đọc/sửa/poll runtime DB để quyết định rollover", self.rollover)
        self.assertIn("Task continuity/canonical mutable truth thuộc QiQi + Work Item", self.rollover)

    def test_route_policy_keeps_semantic_and_runtime_ownership_separate(self) -> None:
        boundary = markdown_section(self.model_routing, "## Boundary")
        self.assertIn("semantic START/RESUME rollover decision → `AGENTS.md`", boundary)
        self.assertIn("Herdr lifecycle, native session identity, Stop-hook capture", boundary)
        self.assertIn("SQLite runtime state → MCP", boundary)


if __name__ == "__main__":
    unittest.main()
