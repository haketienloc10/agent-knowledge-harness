from pathlib import Path
import unittest


class TaskPacketMinimalityPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace_root = Path(__file__).resolve().parents[3]
        cls.identity = (cls.workspace_root / "identity.md").read_text(encoding="utf-8")

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


if __name__ == "__main__":
    unittest.main()
