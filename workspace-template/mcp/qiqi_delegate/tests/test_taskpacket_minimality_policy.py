from pathlib import Path
import unittest


class TaskPacketMinimalityPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace_root = Path(__file__).resolve().parents[3]
        cls.identity = (cls.workspace_root / "identity.md").read_text(encoding="utf-8")
        cls.agents = (cls.workspace_root / "AGENTS.md").read_text(encoding="utf-8")

    def test_orchestration_meta_instructions_stay_out_of_taskpacket_constraints(self):
        self.assertIn(
            "tách task-specific constraint khỏi orchestration/stable-policy meta-instruction",
            self.identity,
        )
        for example in (
            "không tạo/dùng Work Item",
            "child tự discover/chọn verification strategy",
            "delegate bằng qiqi_delegate",
            "không poll",
        ):
            self.assertIn(example, self.identity)
        self.assertIn(
            "chúng ở QiQi/stable-policy side trừ khi method itself là material user/product/system requirement",
            self.identity,
        )

    def test_work_item_completion_uses_revision_guarded_fast_path(self):
        for required in (
            "ưu tiên delegated-revision CAS",
            "work_item_update(expected_revision=<delegated revision>)",
            "không reread trước",
            "Update success chứng minh canonical revision không đổi",
            "revision conflict → reread latest bounded state",
            "completion được guard bởi successful delegated-revision CAS mutation",
        ):
            self.assertIn(required, self.agents)

        self.assertNotIn(
            "reread latest bounded current state trước dependent orchestration decision",
            self.agents,
        )
        self.assertNotIn(
            "1. reread canonical latest bounded current revision/state;",
            self.agents,
        )


if __name__ == "__main__":
    unittest.main()
