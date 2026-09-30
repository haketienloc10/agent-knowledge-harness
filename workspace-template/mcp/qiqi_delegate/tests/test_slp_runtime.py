from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import SessionStore, build_task_packet, task_packet_work_item_ref  # noqa: E402


class SlpRuntimeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "qiqi_delegate.sqlite3"
        self.store = SessionStore(self.db_path)
        self.packet = build_task_packet(
            objective="Implement a tracked repository change.",
            scope=["repository implementation"],
            acceptance_criteria=["focused verification passes"],
            context={
                "trusted_facts": [
                    {
                        "fact": (
                            "work_item_path=/tmp/work-items/e2e-008; "
                            "id=e2e:008; revision=3"
                        ),
                        "source": "canonical Work Item locator",
                    }
                ]
            },
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _record_turn(self, *, response: str = "native response") -> None:
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

    def test_work_item_reference_is_derived_only_from_canonical_locator_fact(self) -> None:
        self.assertEqual(task_packet_work_item_ref(self.packet), ("e2e:008", 3))
        unrelated = build_task_packet(
            objective="Inspect behavior.",
            scope=["behavior"],
            acceptance_criteria=["evidence exists"],
            context={
                "trusted_facts": [
                    {
                        "fact": "id=e2e:999; revision=9",
                        "source": "not a Work Item locator",
                    }
                ]
            },
        )
        self.assertEqual(task_packet_work_item_ref(unrelated), (None, None))

    def test_peer_response_event_references_raw_turn_without_copying_response(self) -> None:
        response = "RAW-PEER-RESPONSE-" + ("x" * 2000)
        dispatch_seq = self.store.record_slp_event(
            event_type="peer.dispatched",
            turn_id="turn-1",
            repository="repo-a",
            route="claude-balanced",
            work_item_id="e2e:008",
            work_item_revision=3,
        )
        self._record_turn(response=response)

        events = self.store.list_slp_events()
        self.assertEqual(
            [(item["seq"], item["event_type"]) for item in events],
            [(dispatch_seq, "peer.dispatched"), (dispatch_seq + 1, "peer.response")],
        )
        peer_response = events[-1]
        self.assertEqual(peer_response["turn_id"], "turn-1")
        self.assertEqual(peer_response["work_item_id"], "e2e:008")
        self.assertEqual(peer_response["work_item_revision"], 3)
        self.assertEqual(peer_response["payload"], {"runtime_state": "settled"})
        self.assertNotIn(response, str(peer_response))

        turn = self.store.get_turn("turn-1")
        self.assertEqual(turn["agent_response"], response)

        with sqlite3.connect(self.db_path) as conn:
            event_payloads = "\n".join(
                row[0] for row in conn.execute("SELECT payload_json FROM slp_events")
            )
        self.assertNotIn(response, event_payloads)

    def test_lead_disposition_is_fk_backed_idempotent_and_emits_one_event(self) -> None:
        self._record_turn()

        first = self.store.record_lead_disposition(
            turn_id="turn-1",
            action="accept",
            reason="verification matches the requirement",
            candidate_id="sha256:abc",
        )
        second = self.store.record_lead_disposition(
            turn_id="turn-1",
            action="accept",
            reason="verification matches the requirement",
            candidate_id="sha256:abc",
        )

        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["disposition_id"], second["disposition_id"])
        self.assertEqual(first["event_seq"], second["event_seq"])
        self.assertEqual(first["work_item_id"], "e2e:008")
        self.assertEqual(first["work_item_revision"], 3)

        events = self.store.list_slp_events()
        self.assertEqual(
            [item["event_type"] for item in events],
            ["peer.response", "lead.disposition", "candidate.accepted"],
        )
        self.assertEqual(
            events[1]["payload"],
            {"action": "accept", "disposition_id": first["disposition_id"]},
        )
        self.assertEqual(
            events[2]["payload"],
            {"disposition_id": first["disposition_id"]},
        )

        with self.assertRaisesRegex(RuntimeError, "different Lead disposition"):
            self.store.record_lead_disposition(
                turn_id="turn-1",
                action="reject",
                reason="different decision",
            )

    def test_disposition_for_unknown_peer_turn_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unknown turn_id"):
            self.store.record_lead_disposition(
                turn_id="missing",
                action="defer",
                reason="awaiting evidence",
            )

    def test_event_replay_is_sequence_bounded(self) -> None:
        first = self.store.record_slp_event(
            event_type="peer.dispatched",
            turn_id="turn-a",
            repository="repo-a",
            route="claude-balanced",
        )
        second = self.store.record_slp_event(
            event_type="peer.signal",
            turn_id="turn-a",
            repository="repo-a",
            route="claude-balanced",
            payload={"signal": "runtime_blocked"},
        )
        replay = self.store.list_slp_events(after_seq=first)
        self.assertEqual([item["seq"] for item in replay], [second])

    def test_ambiguous_capture_emits_reference_event_not_candidate_content(self) -> None:
        self.store.register_session("session-1", "repo-a", "claude")
        self.store.record_capture_review(
            capture_review_id="capture-1",
            session_id="session-1",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            events=[
                {
                    "hook_event": "Stop",
                    "state": "pending_async",
                    "agent_response": "candidate A raw body",
                    "background_task_count": 1,
                    "captured_at_ns": 10,
                },
                {
                    "hook_event": "Stop",
                    "state": "settled",
                    "agent_response": "candidate B raw body",
                    "background_task_count": 0,
                    "captured_at_ns": 20,
                },
            ],
        )
        event = self.store.list_slp_events()[0]
        self.assertEqual(event["event_type"], "peer.capture_ambiguous")
        self.assertEqual(event["capture_review_id"], "capture-1")
        self.assertEqual(event["payload"], {"candidate_count": 2})
        self.assertNotIn("candidate A raw body", str(event))
        self.assertNotIn("candidate B raw body", str(event))


if __name__ == "__main__":
    unittest.main()
