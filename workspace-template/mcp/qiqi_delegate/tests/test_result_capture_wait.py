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
        server.NATIVE_RESULT_WAIT_SECONDS = 0.05

    def tearDown(self) -> None:
        server.NATIVE_RESULT_WAIT_SECONDS = self.original_timeout
        self.temp.cleanup()

    def write_event(self, index: int, event: dict) -> None:
        (self.sink / f"event-{index}.json").write_text(
            json.dumps(event, ensure_ascii=False), encoding="utf-8"
        )

    async def test_pending_background_stop_waits_past_initial_capture_timeout(self):
        self.write_event(
            1,
            normalize_hook_payload(
                adapter="claude",
                nonce="nonce-1",
                payload={
                    "hook_event_name": "Stop",
                    "session_id": "session-1",
                    "last_assistant_message": "Tôi sẽ chờ subagent hoàn tất.",
                    "background_tasks": [
                        {
                            "id": "agent-1",
                            "type": "subagent",
                            "status": "running",
                            "description": "wait then report",
                        }
                    ],
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

    async def test_missing_capture_still_uses_initial_timeout(self):
        with self.assertRaisesRegex(RuntimeError, "native final response was not captured"):
            await server._wait_for_result_capture(
                self.sink, "nonce-1", "claude", "session-1"
            )


if __name__ == "__main__":
    unittest.main()
