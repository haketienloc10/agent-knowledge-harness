"""Phase-0 direct delegation regression baseline kept in migrated workspaces."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import SessionStore  # noqa: E402
from server import TaskContextInput, delegate_repo_task  # noqa: E402


class DelegateRepoTaskRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo-a"
        self.store = SessionStore(self.root / "qiqi_delegate.sqlite3")
        self.work_item_locator = (
            "work_item_path=/workspace/work-items/WI-1; id=WI-1; revision=7"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _execution_stack(
        self,
        *,
        status: str = "done",
        native_session_id: str = "native-session-1",
        capture_event: dict | None = None,
    ) -> tuple[ExitStack, dict[str, object]]:
        if capture_event is None:
            capture_event = {
                "state": "settled",
                "agent_response": "native final response",
                "native_turn_id": "native-turn-1",
            }

        stack = ExitStack()
        mocks: dict[str, object] = {}
        stack.enter_context(patch("server._store", self.store))
        stack.enter_context(patch("server._resolve_repo", return_value=self.repo))
        stack.enter_context(
            patch(
                "server._resolve_route",
                return_value=(
                    "claude",
                    {
                        "adapter": "claude",
                        "command": "claude",
                        "start_args": ["{handoff_args}"],
                        "resume_args": ["--resume", "{session_id}", "{handoff_args}"],
                    },
                    {"model": "sonnet", "args": []},
                ),
            )
        )
        stack.enter_context(patch("server.shutil.which", return_value="/usr/bin/claude"))
        stack.enter_context(
            patch("server._ensure_herdr_server", new=AsyncMock(return_value=None))
        )
        stack.enter_context(
            patch("server._require_current_integration", new=AsyncMock(return_value=None))
        )
        stack.enter_context(
            patch("server._claim_resources", new=AsyncMock(return_value=None))
        )
        stack.enter_context(
            patch("server._release_resources", new=AsyncMock(return_value=None))
        )
        stack.enter_context(
            patch(
                "server._register_active_capture",
                return_value=self.root / "active-capture.json",
            )
        )
        stack.enter_context(patch("server._remove_active_capture"))
        stack.enter_context(patch("server._build_handoff_args", return_value=[]))
        stack.enter_context(
            patch(
                "server._create_herdr_workspace",
                new=AsyncMock(return_value=("workspace-1", "pane-1")),
            )
        )
        start_interactive_agent = stack.enter_context(
            patch(
                "server._start_interactive_agent",
                new=AsyncMock(
                    return_value=("managed-agent-1", {"agent_status": "idle"})
                ),
            )
        )
        mocks["start_interactive_agent"] = start_interactive_agent
        stack.enter_context(
            patch("server._validate_reported_session_if_present", return_value=None)
        )
        stack.enter_context(
            patch(
                "server._prompt_and_wait",
                new=AsyncMock(return_value=(status, {"agent_status": status})),
            )
        )
        stack.enter_context(
            patch(
                "server._wait_for_native_session",
                new=AsyncMock(return_value=native_session_id),
            )
        )
        wait_for_result = stack.enter_context(
            patch(
                "server._wait_for_result_capture",
                new=AsyncMock(return_value=capture_event),
            )
        )
        mocks["wait_for_result"] = wait_for_result
        stack.enter_context(
            patch("server._close_herdr_workspace", new=AsyncMock(return_value=None))
        )
        return stack, mocks

    async def _delegate(self, *, session_id: str | None = None) -> dict:
        return await delegate_repo_task(
            repository="repo-a",
            route="claude-balanced",
            objective="Implement the current repository-local change.",
            scope=["repository-local implementation"],
            acceptance_criteria=["focused verification passes"],
            context=TaskContextInput(
                trusted_facts=[
                    {
                        "fact": self.work_item_locator,
                        "source": "QiQi Work Item locator",
                    }
                ]
            ),
            session_id=session_id,
        )

    async def test_start_settled_preserves_final_response_and_delegated_revision(self) -> None:
        stack, _ = self._execution_stack()
        with stack:
            result = await self._delegate()

        self.assertEqual(result["state"], "settled")
        self.assertEqual(result["session_id"], "native-session-1")
        self.assertEqual(result["agent_response"], "native final response")

        turn = self.store.get_turn(result["turn_id"])
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn["state"], "settled")
        self.assertEqual(turn["agent_response"], "native final response")

        packet = json.loads(turn["task_packet_json"])
        fact = packet["context"]["trusted_facts"][0]["fact"]
        self.assertEqual(fact, self.work_item_locator)
        self.store.require_resume("native-session-1", "repo-a", "claude")

    async def test_resume_reuses_exact_native_session(self) -> None:
        self.store.register_session("native-session-1", "repo-a", "claude")
        stack, mocks = self._execution_stack(native_session_id="native-session-1")
        with stack:
            result = await self._delegate(session_id="native-session-1")

        self.assertEqual(result["state"], "settled")
        start_interactive_agent = mocks["start_interactive_agent"]
        assert isinstance(start_interactive_agent, AsyncMock)
        self.assertEqual(
            start_interactive_agent.await_args.args,
            ("pane-1", "claude", ["--resume", "native-session-1"]),
        )
        self.store.require_resume("native-session-1", "repo-a", "claude")

    async def test_blocked_start_preserves_session_without_fake_turn_result(self) -> None:
        stack, mocks = self._execution_stack(status="blocked")
        with stack:
            result = await self._delegate()

        self.assertEqual(
            result,
            {
                "session_id": "native-session-1",
                "turn_id": result["turn_id"],
                "state": "blocked",
                "agent_response": None,
                "blocker_type": "agent_blocked",
            },
        )
        wait_for_result = mocks["wait_for_result"]
        assert isinstance(wait_for_result, AsyncMock)
        wait_for_result.assert_not_awaited()
        self.store.require_resume("native-session-1", "repo-a", "claude")
        self.assertIsNone(self.store.get_turn(result["turn_id"]))

    async def test_failed_native_turn_is_returned_and_persisted_as_runtime_failure(self) -> None:
        stack, _ = self._execution_stack(
            capture_event={
                "state": "failed",
                "agent_response": "native failure evidence",
                "native_turn_id": "native-turn-failed",
            }
        )
        with stack:
            result = await self._delegate()

        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["agent_response"], "native failure evidence")
        turn = self.store.get_turn(result["turn_id"])
        self.assertIsNotNone(turn)
        assert turn is not None
        self.assertEqual(turn["state"], "failed")
        self.assertEqual(turn["native_turn_id"], "native-turn-failed")
        self.assertEqual(turn["agent_response"], "native failure evidence")


if __name__ == "__main__":
    unittest.main()
