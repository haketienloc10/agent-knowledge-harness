from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import SessionStore, build_task_packet  # noqa: E402
from supervisor_broker import (  # noqa: E402
    HerdrEventsLost,
    HerdrLifecycleSubscriber,
    SupervisorBroker,
    resolve_herdr_socket,
)


class SupervisorBrokerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "qiqi_delegate.sqlite3"
        self.store = SessionStore(self.db_path)
        self.broker = SupervisorBroker(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def packet(*, work_item_id: str | None = None, revision: int | None = None):
        context = None
        if work_item_id is not None and revision is not None:
            context = {
                "trusted_facts": [
                    {
                        "fact": (
                            f"work_item_path=/tmp/work-items/{work_item_id}; "
                            f"id={work_item_id}; revision={revision}"
                        ),
                        "source": "canonical Work Item locator",
                    }
                ]
            }
        return build_task_packet(
            objective="Produce one bounded repository result.",
            scope=["repository implementation"],
            acceptance_criteria=["focused verification passes"],
            context=context,
        )

    def record_turn(
        self,
        turn_id: str,
        *,
        work_item_id: str | None = None,
        revision: int | None = None,
        response: str = "Peer result",
    ) -> None:
        self.store.record_turn(
            turn_id=turn_id,
            session_id=f"session-{turn_id}",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=self.packet(work_item_id=work_item_id, revision=revision),
            agent_response=response,
        )

    def cases(self, rule: str) -> list[dict]:
        return [item for item in self.broker.list_cases() if item["rule"] == rule]

    def test_r1_peer_response_opens_exactly_one_case_and_disposition_closes_it(self) -> None:
        self.record_turn("turn-r1", work_item_id="e2e:008", revision=1)

        first = self.broker.process_pending()
        second = self.broker.process_pending()

        self.assertEqual(first["opened"], 1)
        self.assertEqual(second["processed"], 0)
        cases = self.cases("R1")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["status"], "OPEN")
        self.assertEqual(cases[0]["turn_id"], "turn-r1")

        self.store.record_lead_disposition(
            turn_id="turn-r1",
            action="accept",
            reason="candidate verified",
        )
        closed = self.broker.process_pending()

        self.assertEqual(closed["closed"], 1)
        cases = self.cases("R1")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["status"], "CLOSED")
        self.assertIsNotNone(cases[0]["closed_event_seq"])

    def test_restart_replays_from_durable_cursor(self) -> None:
        self.record_turn("turn-restart")
        first = self.broker.process_pending()
        cursor = first["last_processed_seq"]
        self.assertGreater(cursor, 0)

        restarted = SupervisorBroker(self.db_path)
        self.assertEqual(restarted.last_processed_seq(), cursor)
        replay = restarted.process_pending()
        self.assertEqual(replay["processed"], 0)
        self.assertEqual(len(restarted.list_cases()), 1)

        self.store.record_lead_disposition(
            turn_id="turn-restart",
            action="reject",
            reason="candidate does not meet acceptance",
        )
        resumed = restarted.process_pending()
        self.assertGreater(resumed["last_processed_seq"], cursor)
        self.assertEqual(restarted.list_cases()[0]["status"], "CLOSED")

    def test_cursor_rollback_replay_does_not_duplicate_finding(self) -> None:
        self.record_turn("turn-dedupe")
        self.broker.process_pending()
        self.assertEqual(len(self.cases("R1")), 1)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE supervisor_broker_state SET last_processed_seq = 0 "
                "WHERE broker_id = 'slp-supervisor'"
            )

        replay = self.broker.process_pending()
        self.assertGreater(replay["processed"], 0)
        self.assertEqual(replay["opened"], 0)
        self.assertEqual(len(self.cases("R1")), 1)

    def test_r2_dependency_consumed_requires_explicit_accept(self) -> None:
        self.record_turn("turn-source")
        self.broker.process_pending()

        self.store.record_slp_event(
            event_type="dependency.consumed",
            turn_id="turn-consumer",
            repository="repo-b",
            payload={"source_turn_id": "turn-source"},
        )
        self.broker.process_pending()
        cases = self.cases("R2")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["status"], "OPEN")

        self.store.record_lead_disposition(
            turn_id="turn-source",
            action="accept",
            reason="upstream candidate explicitly accepted",
        )
        self.broker.process_pending()
        self.assertEqual(self.cases("R2")[0]["status"], "CLOSED")

    def test_r3_overlapping_active_write_scopes_open_and_release_closes_case(self) -> None:
        self.store.record_slp_event(
            event_type="write_scope.claimed",
            repository="repo-a",
            payload={
                "claim_id": "claim-a",
                "owner": "peer-a",
                "scope": ["src/pricing.py"],
            },
        )
        self.store.record_slp_event(
            event_type="write_scope.claimed",
            repository="repo-a",
            payload={
                "claim_id": "claim-b",
                "owner": "peer-b",
                "scope": ["src"],
            },
        )
        self.broker.process_pending()

        cases = self.cases("R3")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["status"], "OPEN")
        self.assertEqual(
            cases[0]["details"]["claim_ids"],
            ["claim-a", "claim-b"],
        )

        self.store.record_slp_event(
            event_type="write_scope.released",
            repository="repo-a",
            payload={"claim_id": "claim-a"},
        )
        self.broker.process_pending()
        self.assertEqual(self.cases("R3")[0]["status"], "CLOSED")

    def test_r4_runtime_blocked_is_normalized_to_blocked_signal(self) -> None:
        self.store.record_slp_event(
            event_type="peer.signal",
            turn_id="blocked-turn",
            repository="repo-a",
            payload={"signal": "runtime_blocked"},
        )
        self.broker.process_pending()

        cases = self.cases("R4")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["status"], "OPEN")
        self.assertEqual(cases[0]["details"]["signal"], "BLOCKED")

    def test_r5_newer_work_item_revision_marks_latest_peer_response_stale(self) -> None:
        self.record_turn(
            "turn-stale",
            work_item_id="e2e:009",
            revision=2,
        )
        self.broker.process_pending()

        self.store.record_slp_event(
            event_type="work_item.revision_changed",
            work_item_id="e2e:009",
            work_item_revision=3,
            payload={},
        )
        self.broker.process_pending()

        cases = self.cases("R5")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["status"], "OPEN")
        self.assertEqual(cases[0]["details"]["stale_revision"], 2)
        self.assertEqual(cases[0]["details"]["current_revision"], 3)

        self.record_turn(
            "turn-current",
            work_item_id="e2e:009",
            revision=3,
        )
        self.broker.process_pending()
        self.assertEqual(self.cases("R5")[0]["status"], "CLOSED")

    def test_phase2_cases_store_references_not_raw_peer_response(self) -> None:
        raw = "RAW-PEER-BODY-" + ("x" * 4000)
        self.record_turn("turn-raw", response=raw)
        self.broker.process_pending()

        with sqlite3.connect(self.db_path) as conn:
            stored = "\n".join(
                str(value)
                for row in conn.execute(
                    "SELECT finding_fingerprint, subject_key, details_json "
                    "FROM supervisor_cases"
                )
                for value in row
            )
        self.assertNotIn(raw, stored)


@unittest.skipIf(os.name == "nt", "Unix-domain Herdr socket test")
class HerdrLifecycleSubscriberTests(unittest.IsolatedAsyncioTestCase):
    async def test_subscriber_uses_snapshot_and_events_only_not_terminal_reads(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        socket_path = Path(temp.name) / "herdr.sock"
        seen: list[dict] = []
        completed = asyncio.Event()

        async def handler(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            try:
                snapshot = json.loads((await reader.readline()).decode("utf-8"))
                seen.append(snapshot)
                writer.write(
                    (
                        json.dumps(
                            {
                                "id": snapshot["id"],
                                "result": {
                                    "type": "session_snapshot",
                                    "workspaces": [
                                        {
                                            "workspace_id": "w1",
                                            "panes": [{"pane_id": "w1:p1"}],
                                        }
                                    ],
                                },
                            }
                        )
                        + "\n"
                    ).encode("utf-8")
                )
                await writer.drain()

                subscribe = json.loads((await reader.readline()).decode("utf-8"))
                seen.append(subscribe)
                writer.write(
                    (
                        json.dumps(
                            {
                                "id": subscribe["id"],
                                "result": {"type": "subscription_started"},
                            }
                        )
                        + "\n"
                    ).encode("utf-8")
                )
                writer.write(
                    (
                        json.dumps(
                            {
                                "event": "workspace_created",
                                "data": {"workspace_id": "w2"},
                            }
                        )
                        + "\n"
                    ).encode("utf-8")
                )
                await writer.drain()
                await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()
                completed.set()

        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        async with server:
            subscriber = HerdrLifecycleSubscriber(socket_path)
            stream = subscriber.stream_once()
            event = await anext(stream)
            self.assertEqual(event["event"], "workspace_created")
            await stream.aclose()
            await asyncio.wait_for(completed.wait(), timeout=2)

        self.assertEqual([item["method"] for item in seen], [
            "session.snapshot",
            "events.subscribe",
        ])
        encoded = json.dumps(seen)
        self.assertNotIn("pane.read", encoded)
        self.assertNotIn("agent.read", encoded)
        subscriptions = seen[1]["params"]["subscriptions"]
        self.assertIn(
            {
                "type": "pane.agent_status_changed",
                "pane_id": "w1:p1",
            },
            subscriptions,
        )

    async def test_events_lost_fails_to_reconnect_path_instead_of_guessing(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        socket_path = Path(temp.name) / "herdr.sock"

        async def handler(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            snapshot = json.loads((await reader.readline()).decode("utf-8"))
            writer.write(
                (
                    json.dumps({"id": snapshot["id"], "result": {"workspaces": []}})
                    + "\n"
                ).encode("utf-8")
            )
            await writer.drain()
            subscribe = json.loads((await reader.readline()).decode("utf-8"))
            writer.write(
                (
                    json.dumps(
                        {
                            "id": subscribe["id"],
                            "result": {"type": "subscription_started"},
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
            writer.write(
                (
                    json.dumps(
                        {
                            "id": subscribe["id"],
                            "error": {
                                "code": "events_lost",
                                "message": "retained lifecycle history was exceeded",
                            },
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        async with server:
            subscriber = HerdrLifecycleSubscriber(socket_path)
            stream = subscriber.stream_once()
            with self.assertRaises(HerdrEventsLost):
                await anext(stream)

    def test_named_session_socket_resolution_matches_herdr_contract(self) -> None:
        path = resolve_herdr_socket(
            session="qiqi-delegate",
            environ={"HOME": "/tmp/home"},
        )
        self.assertEqual(
            path,
            Path("/tmp/home/.config/herdr/sessions/qiqi-delegate/herdr.sock"),
        )


if __name__ == "__main__":
    unittest.main()
