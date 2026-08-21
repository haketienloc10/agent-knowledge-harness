from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (
    SessionStore,
    build_task_packet,
    normalize_hook_payload,
    render_task_prompt,
    select_capture_event,
)


class TaskPacketTests(unittest.TestCase):
    def packet(self):
        return build_task_packet(
            user_request="Giữ backward compatibility và sửa consumer.",
            objective="Update the consumer without breaking the legacy field.",
            scope=["Consumer schema handling"],
            out_of_scope=["Producer API changes"],
            required_context=[
                {
                    "fact": "legacy_id must remain for two releases",
                    "source": "repo-a turn 123",
                    "certainty": "verified",
                }
            ],
            constraints=["Do not remove legacy_id"],
            acceptance_criteria=["Existing consumers remain compatible"],
            verification=["Run compatibility tests"],
            known_unknowns=["Deployment date is unknown"],
        )

    def test_prompt_preserves_original_intent_and_closed_world_boundary(self):
        prompt = render_task_prompt(self.packet())
        self.assertIn("Giữ backward compatibility", prompt)
        self.assertIn("legacy_id must remain for two releases", prompt)
        self.assertIn("Provenance: repo-a turn 123", prompt)
        self.assertIn("You do not share QiQi's hidden conversation", prompt)
        self.assertIn("Do not invent an omitted external fact", prompt)
        self.assertIn("there are no required result headings", prompt)
        self.assertNotIn("### Outcome", prompt)
        self.assertNotIn("result Markdown artifact:", prompt)

    def test_scope_and_acceptance_are_required(self):
        kwargs = self.packet().as_dict()
        kwargs["scope"] = []
        with self.assertRaisesRegex(ValueError, "scope must contain"):
            build_task_packet(**kwargs)
        kwargs = self.packet().as_dict()
        kwargs["acceptance_criteria"] = []
        with self.assertRaisesRegex(ValueError, "acceptance_criteria must contain"):
            build_task_packet(**kwargs)

    def test_context_requires_provenance_and_calibrated_certainty(self):
        kwargs = self.packet().as_dict()
        kwargs["required_context"] = [{"fact": "x", "source": "y"}]
        with self.assertRaisesRegex(ValueError, "invalid fields"):
            build_task_packet(**kwargs)
        kwargs = self.packet().as_dict()
        kwargs["required_context"][0]["certainty"] = "probably"
        with self.assertRaisesRegex(ValueError, "certainty must be one of"):
            build_task_packet(**kwargs)


class HookPayloadTests(unittest.TestCase):
    def test_claude_stop_preserves_long_unicode_response(self):
        response = ("Đây là kết quả dài.\n" * 9000) + "END"
        event = normalize_hook_payload(
            adapter="claude",
            nonce="n",
            payload={
                "hook_event_name": "Stop",
                "session_id": "session-1",
                "cwd": "/repo",
                "last_assistant_message": response,
            },
            captured_at_ns=1,
        )
        self.assertEqual(event["agent_response"], response)
        self.assertTrue(event["agent_response"].endswith("END"))

    def test_codex_stop_keeps_native_turn_id(self):
        event = normalize_hook_payload(
            adapter="codex",
            nonce="n",
            payload={
                "hook_event_name": "Stop",
                "session_id": "thread-1",
                "turn_id": "turn-native",
                "cwd": "/repo",
                "last_assistant_message": "done",
            },
            captured_at_ns=2,
        )
        self.assertEqual(event["native_turn_id"], "turn-native")

    def test_latest_matching_root_event_wins(self):
        events = [
            {
                "version": 1,
                "adapter": "claude",
                "session_id": "wrong-subagent",
                "state": "settled",
                "agent_response": "wrong",
                "captured_at_ns": 30,
            },
            {
                "version": 1,
                "adapter": "claude",
                "session_id": "root",
                "state": "settled",
                "agent_response": "intermediate",
                "captured_at_ns": 10,
            },
            {
                "version": 1,
                "adapter": "claude",
                "session_id": "root",
                "state": "settled",
                "agent_response": "final",
                "captured_at_ns": 20,
            },
        ]
        chosen = select_capture_event(events, adapter="claude", session_id="root")
        self.assertEqual(chosen["agent_response"], "final")


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SessionStore(Path(self.temp.name) / "state.sqlite3")
        self.packet = TaskPacketTests().packet()

    def tearDown(self):
        self.temp.cleanup()

    def test_records_and_resumes_without_markdown_artifact(self):
        response = "R" * 250_000
        self.store.record_turn(
            turn_id="turn-1",
            session_id="session-1",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=self.packet,
            agent_response=response,
        )
        self.store.require_resume("session-1", "repo-a", "claude")
        turn = self.store.get_turn("turn-1")
        self.assertIsNotNone(turn)
        self.assertEqual(turn["agent_response"], response)
        self.assertFalse(any(Path(self.temp.name).glob("*.md")))

    def test_registered_blocked_session_can_resume_without_fake_turn_result(self):
        created = self.store.register_session("blocked-session", "repo-a", "claude")
        self.assertTrue(created)
        self.store.require_resume("blocked-session", "repo-a", "claude")
        self.assertIsNone(self.store.get_turn("blocked-turn"))

    def test_resume_rejects_repository_or_agent_mismatch(self):
        self.store.import_legacy_session("s", "repo-a", "claude")
        with self.assertRaisesRegex(RuntimeError, "repository mismatch"):
            self.store.require_resume("s", "repo-b", "claude")
        with self.assertRaisesRegex(RuntimeError, "cross-agent"):
            self.store.require_resume("s", "repo-a", "codex")


if __name__ == "__main__":
    unittest.main()
