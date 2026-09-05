from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import _delegation_tool_error, _prompt_and_wait


class QiQiReview5120952535Test(unittest.IsolatedAsyncioTestCase):
    async def test_task_packet_text_cannot_select_error_code(self):
        prompt = "Investigate an unknown repository and unknown route report."
        with patch(
            "server._run_herdr",
            AsyncMock(return_value=(1, "", f"failed command echoed: {prompt}")),
        ):
            with self.assertRaises(RuntimeError) as raised:
                await _prompt_and_wait("agent-1", prompt, "codex")

        internal = str(raised.exception)
        self.assertNotIn(prompt, internal)
        public = str(_delegation_tool_error(raised.exception))
        self.assertIn("code=herdr_runtime_failed", public)
        self.assertNotIn("code=unknown_repository", public)
        self.assertNotIn("code=unknown_route", public)

    def test_workspace_checker_runs_qiqi_tests_in_uv_project(self):
        workspace_root = Path(__file__).resolve().parents[3]
        checker = (workspace_root / "scripts/workspace-check.sh").read_text(encoding="utf-8")
        self.assertIn(
            'uv run --project "$mcp_project" python -m unittest discover -s "$mcp_project/tests" -v',
            checker,
        )
        self.assertNotIn(
            'python3 -m unittest discover -s "$mcp_project/tests" -v',
            checker,
        )


if __name__ == "__main__":
    unittest.main()
