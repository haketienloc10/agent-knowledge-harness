from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "result_hook.py"


class ResultHookTests(unittest.TestCase):
    def run_hook(self, adapter: str, payload: dict):
        temp = tempfile.TemporaryDirectory()
        sink = Path(temp.name) / "sink"
        completed = subprocess.run(
            [
                sys.executable,
                str(HOOK),
                "--adapter",
                adapter,
                "--sink",
                str(sink),
                "--nonce",
                "nonce-1",
            ],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
        )
        return temp, sink, completed

    def test_writes_full_native_message_atomically(self):
        response = ("Một dòng unicode rất dài — ✓\n" * 5000) + "THE-END"
        temp, sink, completed = self.run_hook(
            "codex",
            {
                "hook_event_name": "Stop",
                "session_id": "s",
                "turn_id": "t",
                "cwd": "/repo",
                "last_assistant_message": response,
            },
        )
        try:
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout.strip(), "{}")
            files = list(sink.glob("event-*.json"))
            self.assertEqual(len(files), 1)
            event = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(event["agent_response"], response)
            self.assertTrue(event["agent_response"].endswith("THE-END"))
            self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        finally:
            temp.cleanup()

    def test_malformed_hook_input_does_not_block_agent(self):
        temp, sink, completed = self.run_hook("claude", {"hook_event_name": "Stop"})
        try:
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout.strip(), "{}")
            self.assertEqual(list(sink.glob("event-*.json")), [])
            self.assertIn("capture failed", completed.stderr)
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
