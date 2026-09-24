from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
from core import normalize_hook_payload


class ResultCaptureWaitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.sink = Path(self.temp.name)
        self.original_timeout = server.NATIVE_RESULT_WAIT_SECONDS
        self.original_pending_timeout = server.NATIVE_PENDING_RESULT_WAIT_SECONDS
        server.NATIVE_RESULT_WAIT_SECONDS = 0.05
        server.NATIVE_PENDING_RESULT_WAIT_SECONDS = 0.2

    def tearDown(self) -> None:
        server.NATIVE_RESULT_WAIT_SECONDS = self.original_timeout
        server.NATIVE_PENDING_RESULT_WAIT_SECONDS = self.original_pending_timeout
        self.temp.cleanup()

    def write_event(self, index: int, event: dict) -> None:
        (self.sink / f"event-{index}.json").write_text(
            json.dumps(event, ensure_ascii=False), encoding="utf-8"
        )

    def test_claude_handoff_args_register_only_root_result_hooks(self):
        args = server._build_handoff_args("claude")
        self.assertEqual(args[0], "--settings")
        settings = json.loads(args[1])
        self.assertEqual(set(settings["hooks"]), {"Stop", "StopFailure"})

    async def test_pending_background_stop_waits_then_returns_latest_substantial(self):
        self.write_event(
            1,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": "waiting for child",
                    "background_tasks": [{"id": "agent-1"}],
                },
                captured_at_ns=10,
            ),
        )
        waiter = asyncio.create_task(
            server._wait_for_result_capture(
                self.sink, "nonce-1", "claude", "session-1"
            )
        )
        await asyncio.sleep(0.12)
        self.assertFalse(waiter.done())
        self.write_event(
            2,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": "DONE — OK",
                    "background_tasks": [],
                },
                captured_at_ns=20,
            ),
        )
        result = await asyncio.wait_for(waiter, timeout=1)
        self.assertEqual(result["state"], "settled")
        self.assertEqual(result["agent_response"], "DONE — OK")

    async def test_full_report_survives_tiny_quiescent_housekeeping(self):
        report = "FULL SELF-CONTAINED REPORT\n" + ("evidence\n" * 900)
        self.write_event(
            1,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": report,
                    "background_tasks": [{"id": "agent-1"}],
                },
                captured_at_ns=10,
            ),
        )
        self.write_event(
            2,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": "Notification: agent finished; nothing new.",
                    "background_tasks": [],
                },
                captured_at_ns=20,
            ),
        )
        result = await server._wait_for_result_capture(
            self.sink, "nonce-1", "claude", "session-1"
        )
        self.assertEqual(result["state"], "settled")
        self.assertEqual(result["agent_response"], report)

    async def test_gray_zone_still_returns_ambiguous_capture(self):
        self.write_event(
            1,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": "A" * 5000,
                    "background_tasks": [{"id": "shell-1", "type": "shell"}],
                },
                captured_at_ns=10,
            ),
        )
        self.write_event(
            2,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": "B" * 1200,
                    "background_tasks": [],
                },
                captured_at_ns=20,
            ),
        )
        result = await server._wait_for_result_capture(
            self.sink, "nonce-1", "claude", "session-1"
        )
        self.assertEqual(result["state"], "capture_ambiguous")
        self.assertEqual(result["candidate_count"], 2)

    async def test_multiple_background_agents_choose_latest_substantial(self):
        values = [
            ("launch:", 250, [{"id": "a"}, {"id": "b"}]),
            ("partial-a:", 5000, [{"id": "b"}]),
            ("final-ab:", 2200, [{"id": "b"}]),
            ("notification:", 150, []),
        ]
        for index, (prefix, size, background) in enumerate(values, start=1):
            self.write_event(
                index,
                normalize_hook_payload(
                    adapter="claude",
                    nonce="nonce-1",
                    payload={
                        "hook_event_name": "Stop",
                        "session_id": "session-1",
                        "last_assistant_message": prefix + ("x" * size),
                        "background_tasks": background,
                    },
                    captured_at_ns=index * 10,
                ),
            )
        result = await server._wait_for_result_capture(
            self.sink, "nonce-1", "claude", "session-1"
        )
        self.assertEqual(result["state"], "settled")
        self.assertTrue(result["agent_response"].startswith("final-ab:"))

    async def test_stop_failure_keeps_exact_failure_response_after_prior_stop(self):
        self.write_event(
            1,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": "FULL SELF-CONTAINED REPORT",
                    "background_tasks": [{"id": "agent-1"}],
                },
                captured_at_ns=10,
            ),
        )
        self.write_event(
            2,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "StopFailure",
                    "session_id": "session-1",
                    "last_assistant_message": "Native failure evidence",
                    "error": "background task failed",
                },
                captured_at_ns=20,
            ),
        )
        result = await server._wait_for_result_capture(
            self.sink, "nonce-1", "claude", "session-1"
        )
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["agent_response"], "Native failure evidence")
        self.assertEqual(result["error"], "background task failed")

    async def test_single_no_async_stop_returns_native_response(self):
        self.write_event(
            1,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": "final result",
                    "background_tasks": [],
                },
                captured_at_ns=10,
            ),
        )
        result = await server._wait_for_result_capture(
            self.sink, "nonce-1", "claude", "session-1"
        )
        self.assertEqual(result["state"], "settled")
        self.assertEqual(result["agent_response"], "final result")

    async def test_pending_background_stop_has_bounded_failure_path(self):
        server.NATIVE_PENDING_RESULT_WAIT_SECONDS = 0.05
        self.write_event(
            1,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": "still waiting",
                    "background_tasks": [{"id": "agent-1"}],
                },
                captured_at_ns=10,
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "pending background work"):
            await asyncio.wait_for(
                server._wait_for_result_capture(
                    self.sink, "nonce-1", "claude", "session-1"
                ),
                timeout=1,
            )

    async def test_missing_background_task_capability_surfaces_actionable_error(self):
        self.write_event(
            1,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": "done",
                },
                captured_at_ns=10,
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "upgrade Claude Code"):
            await server._wait_for_result_capture(
                self.sink, "nonce-1", "claude", "session-1"
            )

    async def test_missing_capture_still_uses_initial_timeout(self):
        with self.assertRaisesRegex(RuntimeError, "native final response was not captured"):
            await server._wait_for_result_capture(
                self.sink, "nonce-1", "claude", "session-1"
            )


if __name__ == "__main__":
    unittest.main()
