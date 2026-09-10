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
        cls.workspace_setup = read_workspace_file("docs/WORKSPACE_SETUP.md")

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

    def test_rollover_requires_affirmative_resume_reason_and_supports_work_itemless_boundaries(self) -> None:
        rollover = markdown_section(self.agents, "## START/RESUME")

        self.assertIn("Known `session_id` tự nó **không phải** lý do để RESUME", rollover)
        self.assertIn("RESUME cần một affirmative continuity reason", rollover)
        self.assertIn("**START fresh mặc định**", rollover)
        self.assertIn("Với task không dùng Work Item", rollover)
        self.assertIn("không tạo Work Item chỉ để biện minh cho rollover", rollover)

    def test_rollover_decision_precedes_taskpacket_referential_closure(self) -> None:
        before_delegation = markdown_section(self.agents, "## Trước delegation")
        choose_mode = before_delegation.index("Chọn START/RESUME")
        finalize_closure = before_delegation.index("finalize TaskPacket referential closure")
        delegate = before_delegation.index("Delegate bằng `delegate_repo_task`")

        self.assertLess(choose_mode, finalize_closure)
        self.assertLess(finalize_closure, delegate)

    def test_blocked_rollover_is_conditional_and_keeps_exact_recovery_identity(self) -> None:
        rollover = markdown_section(self.agents, "## START/RESUME")
        after_delegation = markdown_section(self.agents, "## Sau delegation")
        smoke = markdown_section(self.workspace_setup, "## 12. Fresh-session acceptance smoke")

        self.assertIn("`blocked` trước native final response giữ exact `session_id`", rollover)
        self.assertIn("RESUME exact session khi cần tiếp tục exact interactive blocker", rollover)
        self.assertIn("START/redelegate hợp lệ", rollover)
        self.assertIn("Với `blocked`, `agent_response=null`", after_delegation)
        self.assertIn("Giữ exact `session_id`", after_delegation)
        self.assertIn("exact RESUME chỉ khi interactive blocker continuity còn material", smoke)
        self.assertIn("MAY START/redelegate", smoke)

    def test_independent_verifier_starts_fresh_even_on_same_native_family(self) -> None:
        rollover = markdown_section(self.agents, "## START/RESUME")
        verifier_start = self.model_routing.index("### `claude-verifier`")
        verifier_end = self.model_routing.index("### `codex-balanced`", verifier_start)
        verifier = self.model_routing[verifier_start:verifier_end]

        self.assertIn("Independent verifier/reviewer **MUST START fresh by default**", rollover)
        self.assertIn("**MUST START fresh by default**", verifier)
        self.assertIn("cùng underlying native agent family", verifier)

    def test_fresh_child_does_not_depend_on_canonical_work_item_state(self) -> None:
        smoke = markdown_section(self.workspace_setup, "## 12. Fresh-session acceptance smoke")

        self.assertIn("QiQi distill relevant canonical/task semantics vào self-sufficient TaskPacket", smoke)
        self.assertIn("child reconstruct task meaning chỉ từ packet + current repo/stable policy", smoke)
        self.assertIn("không nhận hoặc dereference current canonical Work Item state", smoke)

    def test_rollover_does_not_require_runtime_state_polling(self) -> None:
        rollover = markdown_section(self.agents, "## START/RESUME")
        self.assertIn("QiQi không đọc/sửa/poll", rollover)
        self.assertIn("`.qiqi/state/qiqi_delegate.sqlite3`", rollover)
        self.assertIn("để quyết định rollover", rollover)


if __name__ == "__main__":
    unittest.main()
