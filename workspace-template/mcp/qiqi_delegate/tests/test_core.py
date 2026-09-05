from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (
    TASK_PACKET_MAX_CHARS,
    SessionStore,
    active_capture_filename,
    build_task_packet,
    codex_session_hook_key,
    codex_stop_hook_hash,
    normalize_hook_payload,
    render_task_prompt,
    select_capture_event,
)


class TaskPacketTests(unittest.TestCase):
    def packet(self):
        return build_task_packet(
            objective="Update the consumer without breaking the legacy field.",
            scope=["Consumer schema handling"],
            out_of_scope=["Producer API changes"],
            context={
                "trusted_facts": [
                    {
                        "fact": "legacy_id must remain for two releases",
                        "source": "customer compatibility decision",
                    }
                ],
                "claims_to_investigate": [
                    {
                        "claim": "The current consumer rejects records without legacy_id",
                        "source": "existing migration note",
                    }
                ],
            },
            constraints=["Do not remove legacy_id"],
            acceptance_criteria=["Existing consumers remain compatible"],
            known_unknowns=["Deployment date is unknown"],
        )

    def test_prompt_contains_only_task_specific_semantics(self):
        prompt = render_task_prompt(self.packet())
        self.assertIn("Update the consumer", prompt)
        self.assertIn("legacy_id must remain for two releases", prompt)
        self.assertIn("Provenance: customer compatibility decision", prompt)
        self.assertIn("Claims to investigate", prompt)
        self.assertIn("Do not remove legacy_id", prompt)
        self.assertNotIn("Original user request", prompt)
        self.assertNotIn("Required verification", prompt)
        self.assertNotIn("Context boundary", prompt)
        self.assertNotIn("Handoff contract", prompt)

    def test_optional_empty_sections_are_omitted(self):
        packet = build_task_packet(
            objective="Inspect retry behavior.",
            scope=["Retry behavior"],
            acceptance_criteria=["Current behavior is established with evidence"],
        )
        prompt = render_task_prompt(packet)
        self.assertNotIn("Out of scope", prompt)
        self.assertNotIn("Trusted facts", prompt)
        self.assertNotIn("Claims to investigate", prompt)
        self.assertNotIn("Constraints", prompt)
        self.assertNotIn("Known unknowns", prompt)
        self.assertEqual(
            set(packet.as_dict()), {"objective", "scope", "acceptance_criteria"}
        )

    def test_scope_and_acceptance_are_required(self):
        kwargs = self.packet().as_dict()
        kwargs["scope"] = []
        with self.assertRaisesRegex(ValueError, "scope must contain"):
            build_task_packet(**kwargs)
        kwargs = self.packet().as_dict()
        kwargs["acceptance_criteria"] = []
        with self.assertRaisesRegex(ValueError, "acceptance_criteria must contain"):
            build_task_packet(**kwargs)

    def test_trusted_fact_requires_fact_and_source_only(self):
        kwargs = self.packet().as_dict()
        kwargs["context"] = {
            "trusted_facts": [{"fact": "x", "source": "y", "certainty": "verified"}]
        }
        with self.assertRaisesRegex(ValueError, "unsupported certainty"):
            build_task_packet(**kwargs)
        kwargs["context"] = {"trusted_facts": [{"fact": "x"}]}
        with self.assertRaisesRegex(ValueError, "missing source"):
            build_task_packet(**kwargs)

    def test_claim_cannot_also_be_a_trusted_premise(self):
        with self.assertRaisesRegex(ValueError, "cannot be both"):
            build_task_packet(
                objective="Establish retry behavior.",
                scope=["Retry behavior"],
                context={
                    "trusted_facts": [{"fact": "Retry limit is 3", "source": "ticket"}],
                    "claims_to_investigate": [
                        {"claim": "retry LIMIT is 3", "source": "legacy note"}
                    ],
                },
                acceptance_criteria=["Retry behavior is established"],
            )

    def test_long_history_is_not_part_of_target_contract(self):
        packet = build_task_packet(
            objective="Fix retry handling.",
            scope=["Retry handling"],
            context={
                "trusted_facts": [
                    {"fact": "Retry limit is 3", "source": "current product decision"}
                ]
            },
            acceptance_criteria=["Retry stops after the third failure"],
        )
        payload = packet.to_json()
        self.assertNotIn("user_request", payload)
        self.assertNotIn("verification", payload)
        self.assertNotIn("work_item", payload)

    def test_aggregate_packet_size_boundary(self):
        small = build_task_packet(
            objective="x",
            scope=["y"],
            acceptance_criteria=["z"],
            constraints=["a" * (TASK_PACKET_MAX_CHARS // 2)],
        )
        self.assertLessEqual(len(small.to_json()), TASK_PACKET_MAX_CHARS)

        with self.assertRaisesRegex(ValueError, "task packet is too large"):
            build_task_packet(
                objective="x",
                scope=["y"],
                acceptance_criteria=["z"],
                constraints=["a" * TASK_PACKET_MAX_CHARS],
            )


class HookIdentityTests(unittest.TestCase):
    def test_codex_stop_hook_hash_matches_current_contract(self):
        command = (
            "/tmp/qiqi/.venv/bin/python3 /tmp/qiqi/result_hook.py "
            "--adapter codex --state-root /tmp/qiqi/.qiqi/state"
        )
        self.assertEqual(
            codex_stop_hook_hash(command),
            "sha256:c6808b60515aaa474478895528d24f597a5a0ccbd70509b104351bada756efcb",
        )

    def test_codex_session_hook_key_targets_only_session_stop_handler(self):
        key = codex_session_hook_key()
        self.assertIn("<session-flags>", key)
        self.assertTrue(key.endswith(":stop:0:0"))

    def test_active_capture_filename_is_adapter_and_repo_scoped(self):
        repo = Path("/tmp/qiqi-capture-key-test")
        codex_name = active_capture_filename("codex", repo)
        claude_name = active_capture_filename("claude", repo)
        self.assertNotEqual(codex_name, claude_name)
        self.assertRegex(codex_name, r"^[0-9a-f]{64}\.json$")
        self.assertRegex(claude_name, r"^[0-9a-f]{64}\.json$")


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
