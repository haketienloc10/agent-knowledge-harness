from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "result_hook.py"


class ResultHookTests(unittest.TestCase):
    def run_direct_hook(self, adapter: str, payload: dict):
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

    def run_static_hook(
        self,
        adapter: str,
        payload: dict,
        *,
        expected_session_id: str | None = None,
    ):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        state_root = root / "state"
        capture_dir = state_root / "active-captures"
        capture_dir.mkdir(parents=True)
        sink = root / "sink"
        repo = root / "repo"
        repo.mkdir()
        payload = dict(payload)
        payload["cwd"] = str(repo)
        key = hashlib.sha256(f"{adapter}\0{repo.resolve()}".encode("utf-8")).hexdigest()
        descriptor = capture_dir / f"{key}.json"
        descriptor.write_text(
            json.dumps(
                {
                    "version": 1,
                    "adapter": adapter,
                    "repo": str(repo.resolve()),
                    "sink": str(sink.resolve()),
                    "nonce": "static-nonce",
                    "expected_session_id": expected_session_id,
                }
            ),
            encoding="utf-8",
        )
        os.chmod(descriptor, 0o600)
        completed = subprocess.run(
            [
                sys.executable,
                str(HOOK),
                "--adapter",
                adapter,
                "--state-root",
                str(state_root),
            ],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
        )
        return temp, sink, completed

    def test_writes_full_native_message_atomically(self):
        response = ("Một dòng unicode rất dài — ✓\n" * 5000) + "THE-END"
        temp, sink, completed = self.run_direct_hook(
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

    def test_static_hook_routes_through_active_capture_descriptor(self):
        response = "STATIC-BEGIN\nTiếng Việt ✓\nSTATIC-END"
        temp, sink, completed = self.run_static_hook(
            "claude",
            {
                "hook_event_name": "Stop",
                "session_id": "claude-session",
                "last_assistant_message": response,
            },
        )
        try:
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout.strip(), "{}")
            files = list(sink.glob("event-*.json"))
            self.assertEqual(len(files), 1)
            event = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(event["nonce"], "static-nonce")
            self.assertEqual(event["agent_response"], response)
        finally:
            temp.cleanup()

    def test_static_resume_rejects_wrong_native_session(self):
        temp, sink, completed = self.run_static_hook(
            "codex",
            {
                "hook_event_name": "Stop",
                "session_id": "wrong-session",
                "last_assistant_message": "must not be captured",
            },
            expected_session_id="expected-session",
        )
        try:
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout.strip(), "{}")
            self.assertEqual(list(sink.glob("event-*.json")), [])
            self.assertIn("native session mismatch", completed.stderr)
        finally:
            temp.cleanup()

    def test_malformed_hook_input_does_not_block_agent(self):
        temp, sink, completed = self.run_direct_hook(
            "claude", {"hook_event_name": "Stop"}
        )
        try:
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout.strip(), "{}")
            self.assertEqual(list(sink.glob("event-*.json")), [])
            self.assertIn("capture failed", completed.stderr)
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
