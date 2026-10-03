from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import SessionStore, build_task_packet  # noqa: E402
from supervisor_broker import (  # noqa: E402
    BrokerInstanceLock,
    HerdrEventsLost,
    HerdrLifecycleSubscriber,
    HerdrSubscriptionError,
    SupervisorBroker,
    _drain_durable,
    main,
    resolve_herdr_socket,
    serve,
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

    def test_r2_dependency_consumed_before_accept_remains_a_temporal_violation(self) -> None:
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
        self.assertEqual(cases[0]["turn_id"], "turn-source")
        self.assertEqual(cases[0]["details"]["source_turn_id"], "turn-source")
        self.assertEqual(cases[0]["details"]["consumer_turn_id"], "turn-consumer")
        self.assertEqual(cases[0]["details"]["consumer_repository"], "repo-b")

        self.store.record_lead_disposition(
            turn_id="turn-source",
            action="accept",
            reason="upstream candidate explicitly accepted after consumption",
        )
        self.broker.process_pending()
        self.assertEqual(self.cases("R2")[0]["status"], "OPEN")

    def test_r2_explicit_consumption_resolution_closes_without_rewriting_history(
        self,
    ) -> None:
        self.record_turn("turn-r2-resolve")
        consumed_seq = self.store.record_slp_event(
            event_type="dependency.consumed",
            turn_id="turn-r2-consumer",
            repository="repo-b",
            payload={"source_turn_id": "turn-r2-resolve"},
        )
        self.broker.process_pending()
        case = self.cases("R2")[0]
        self.assertEqual(case["status"], "OPEN")
        self.assertEqual(
            case["details"]["consumption_event_seq"],
            consumed_seq,
        )

        resolution_seq = self.store.record_dependency_consumption_resolution(
            consumption_event_seq=consumed_seq,
            reason="Lead repaired the downstream premise and re-ran affected validation",
        )
        self.broker.process_pending()

        closed = self.cases("R2")[0]
        self.assertEqual(closed["status"], "CLOSED")
        self.assertEqual(closed["closed_event_seq"], resolution_seq)
        consumed = next(
            event
            for event in self.store.list_slp_events()
            if event["seq"] == consumed_seq
        )
        self.assertEqual(consumed["event_type"], "dependency.consumed")

    def test_r2_broker_lag_does_not_let_later_accept_hide_violation(self) -> None:
        self.record_turn("turn-lagged-source")
        self.store.record_slp_event(
            event_type="dependency.consumed",
            turn_id="turn-lagged-consumer",
            repository="repo-b",
            payload={"source_turn_id": "turn-lagged-source"},
        )
        self.store.record_lead_disposition(
            turn_id="turn-lagged-source",
            action="accept",
            reason="accepted only after downstream already consumed it",
        )

        self.broker.process_pending()

        cases = self.cases("R2")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["status"], "OPEN")
        self.assertEqual(
            cases[0]["details"]["source_turn_id"],
            "turn-lagged-source",
        )

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
        self.assertEqual(
            cases[0]["details"]["overlap_pairs"],
            [{"left": "src", "right": "src/pricing.py"}],
        )
        self.assertFalse(cases[0]["details"]["overlap_pairs_truncated"])

        self.store.record_slp_event(
            event_type="write_scope.released",
            repository="repo-a",
            payload={"claim_id": "claim-a"},
        )
        self.broker.process_pending()
        self.assertEqual(self.cases("R3")[0]["status"], "CLOSED")

    def test_r4_runtime_blocked_is_normalized_and_closes_on_same_session_response(self) -> None:
        self.store.register_session("native-blocked", "repo-a", "claude")
        self.store.record_slp_event(
            event_type="peer.signal",
            turn_id="blocked-turn",
            session_id="native-blocked",
            repository="repo-a",
            payload={"signal": "runtime_blocked"},
        )
        self.broker.process_pending()

        cases = self.cases("R4")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["status"], "OPEN")
        self.assertEqual(cases[0]["details"]["signal"], "BLOCKED")
        self.assertTrue(cases[0]["details"]["runtime_blocked"])
        self.assertEqual(cases[0]["details"]["session_id"], "native-blocked")

        self.store.record_turn(
            turn_id="resumed-turn",
            session_id="native-blocked",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=self.packet(),
            agent_response="resumed result",
        )
        self.broker.process_pending()
        self.assertEqual(self.cases("R4")[0]["status"], "CLOSED")

    def test_r4_runtime_blocked_can_be_explicitly_abandoned_without_turn_row(self) -> None:
        self.store.register_session("native-abandoned", "repo-a", "claude")
        self.store.record_slp_event(
            event_type="peer.signal",
            turn_id="blocked-abandoned-turn",
            session_id="native-abandoned",
            repository="repo-a",
            route="claude-balanced",
            payload={"signal": "runtime_blocked"},
        )
        self.broker.process_pending()
        case = self.cases("R4")[0]
        self.assertEqual(case["status"], "OPEN")
        self.assertTrue(case["details"]["runtime_blocked"])

        self.store.record_peer_signal_resolution(
            turn_id="blocked-abandoned-turn",
            signal="BLOCKED",
            reason="Lead abandoned continuity and will start fresh.",
        )
        self.broker.process_pending()

        self.assertEqual(self.cases("R4")[0]["status"], "CLOSED")
        self.assertIsNone(self.store.get_turn("blocked-abandoned-turn"))

    def test_r4_defer_then_explicit_signal_resolution_closes_case(self) -> None:
        self.record_turn("turn-deferred-signal")
        self.store.record_peer_signal(
            turn_id="turn-deferred-signal",
            signal="DEPENDENCY_REQUEST",
            details="Need upstream contract.",
        )
        self.broker.process_pending()
        self.assertEqual(self.cases("R4")[0]["status"], "OPEN")

        self.store.record_lead_disposition(
            turn_id="turn-deferred-signal",
            action="defer",
            reason="Owner assigned; return after upstream contract is accepted.",
            owner="lead",
            return_checkpoint="after upstream contract is accepted",
        )
        self.broker.process_pending()
        self.assertEqual(self.cases("R4")[0]["status"], "OPEN")

        self.store.record_peer_signal_resolution(
            turn_id="turn-deferred-signal",
            signal="DEPENDENCY_REQUEST",
            reason="Upstream contract is now accepted and available.",
        )
        self.broker.process_pending()
        self.assertEqual(self.cases("R4")[0]["status"], "CLOSED")

    def test_r4_preserves_bounded_peer_signal_details(self) -> None:
        self.record_turn("turn-signal")
        self.store.record_peer_signal(
            turn_id="turn-signal",
            signal="DEPENDENCY_REQUEST",
            details="Need accepted upstream contract and candidate identity.",
        )
        self.broker.process_pending()

        case = self.cases("R4")[0]
        self.assertEqual(
            case["details"]["signal_details"],
            "Need accepted upstream contract and candidate identity.",
        )
        self.assertFalse(case["details"]["signal_details_truncated"])

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
        self.assertEqual(self.cases("R5")[0]["status"], "OPEN")

        self.store.record_candidate_reconciliation(
            stale_turn_id="turn-stale",
            resolution="superseded",
            reason="revision 3 candidate replaces the stale revision 2 result",
            work_item_id="e2e:009",
            work_item_revision=3,
            replacement_turn_id="turn-current",
        )
        self.broker.process_pending()
        self.assertEqual(self.cases("R5")[0]["status"], "CLOSED")

    def test_r5_revision_change_opens_case_for_every_unreconciled_stale_turn(self) -> None:
        self.record_turn("turn-stale-a", work_item_id="e2e:multi", revision=2)
        self.record_turn("turn-stale-b", work_item_id="e2e:multi", revision=2)
        self.broker.process_pending()

        self.store.record_slp_event(
            event_type="work_item.revision_changed",
            work_item_id="e2e:multi",
            work_item_revision=3,
            payload={"reason": "material requirement change"},
        )
        self.broker.process_pending()

        cases = self.cases("R5")
        self.assertEqual(len(cases), 2)
        self.assertEqual(
            {case["turn_id"] for case in cases},
            {"turn-stale-a", "turn-stale-b"},
        )
        self.assertTrue(all(case["status"] == "OPEN" for case in cases))

    def test_r5_requirement_change_after_accept_still_opens_stale_candidate_case(self) -> None:
        self.record_turn(
            "turn-accepted-stale",
            work_item_id="e2e:010",
            revision=2,
        )
        self.broker.process_pending()
        self.store.record_lead_disposition(
            turn_id="turn-accepted-stale",
            action="accept",
            reason="candidate met revision 2 requirements",
            work_item_id="e2e:010",
            work_item_revision=2,
            candidate_id="candidate-r2",
        )
        self.broker.process_pending()

        self.store.record_slp_event(
            event_type="work_item.revision_changed",
            work_item_id="e2e:010",
            work_item_revision=3,
            payload={"reason": "material requirement change"},
        )
        self.broker.process_pending()

        cases = self.cases("R5")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["status"], "OPEN")
        self.assertEqual(cases[0]["turn_id"], "turn-accepted-stale")
        self.assertEqual(cases[0]["details"]["stale_revision"], 2)
        self.assertEqual(cases[0]["details"]["current_revision"], 3)

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


@unittest.skipIf(os.name == "nt", "broker singleton uses POSIX flock")
class BrokerInstanceLockTests(unittest.TestCase):
    def test_once_mode_uses_same_singleton_lock_as_daemon(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_db = Path(temp) / "qiqi_delegate.sqlite3"
            daemon_lock = BrokerInstanceLock(state_db)
            daemon_lock.acquire()
            try:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "another Supervisor broker already owns this state DB",
                ):
                    main(["--once", "--db", str(state_db)])
            finally:
                daemon_lock.release()

    def test_second_lock_for_same_state_db_fails_until_first_releases(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_db = Path(temp) / "qiqi_delegate.sqlite3"
            first = BrokerInstanceLock(state_db)
            second = BrokerInstanceLock(state_db)
            first.acquire()
            try:
                with self.assertRaisesRegex(
                    RuntimeError, "another Supervisor broker already owns this state DB"
                ):
                    second.acquire()
            finally:
                first.release()

            second.acquire()
            second.release()


class BrokerHealthTests(unittest.TestCase):
    def test_retry_health_is_durable_and_can_recover(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "qiqi_delegate.sqlite3"
            broker = SupervisorBroker(db_path)
            broker.mark_retrying(RuntimeError("capture failed"))

            retrying = SupervisorBroker(db_path).health_state()
            self.assertEqual(retrying["health_status"], "retrying")
            self.assertIn("capture failed", retrying["last_error"])
            self.assertIsNotNone(retrying["last_error_at_ns"])

            broker.mark_healthy()
            healthy = broker.health_state()
            self.assertEqual(healthy["health_status"], "healthy")
            self.assertIsNone(healthy["last_error"])
            self.assertIsNone(healthy["last_error_at_ns"])


class DurableDrainTests(unittest.IsolatedAsyncioTestCase):
    async def test_drain_replays_full_broker_backlog_before_reviewing_cases(self) -> None:
        call_order: list[str] = []

        class Broker:
            def __init__(self):
                self.calls = 0
                self.healthy = False

            def process_pending(self, *, limit):
                self.calls += 1
                call_order.append(f"broker-{self.calls}")
                processed = {1: limit, 2: 3}.get(self.calls, 0)
                return {
                    "from_seq": 0,
                    "last_processed_seq": self.calls,
                    "processed": processed,
                    "opened": 1 if self.calls == 1 else 0,
                    "closed": 1 if self.calls == 2 else 0,
                }

            def mark_healthy(self):
                self.healthy = True

            def health_state(self):
                return {
                    "health_status": "healthy" if self.healthy else "retrying",
                    "last_error": None,
                    "last_error_at_ns": None,
                    "updated_at_ns": 1,
                }

        class Runtime:
            def __init__(self):
                self.calls = 0

            async def handle_pending_cases(
                self,
                *,
                limit,
                review=True,
                deliver=True,
                before_delivery=None,
            ):
                self.calls += 1
                phase = "review" if review else "deliver"
                call_order.append(f"runtime-{phase}-{self.calls}")
                return {
                    "reviewed": 0,
                    "delivered_to_lead": 0,
                    "review_attempted": 0,
                    "delivery_attempted": 0,
                    "review_failures": 0,
                    "delivery_failures": 0,
                }

        broker = Broker()
        runtime = Runtime()
        result = await _drain_durable(broker, runtime)

        self.assertEqual(
            call_order,
            [
                "broker-1",
                "broker-2",
                "runtime-review-1",
                "broker-3",
                "runtime-deliver-2",
                "broker-4",
            ],
        )
        self.assertTrue(broker.healthy)
        self.assertEqual(result["broker"]["processed"], 1003)
        self.assertEqual(result["broker"]["opened"], 1)
        self.assertEqual(result["broker"]["closed"], 1)
        self.assertEqual(result["supervisor"]["reviewed"], 0)

    async def test_drain_replays_concurrent_closure_before_issue_delivery(self) -> None:
        call_order: list[str] = []

        class Broker:
            def __init__(self):
                self.calls = 0

            def process_pending(self, *, limit):
                self.calls += 1
                call_order.append(f"broker-{self.calls}")
                # The second replay represents a Lead closure committed while
                # Supervisor review was awaiting the model.
                return {
                    "from_seq": self.calls - 1,
                    "last_processed_seq": self.calls,
                    "processed": 1 if self.calls == 2 else 0,
                    "opened": 0,
                    "closed": 1 if self.calls == 2 else 0,
                }

            def mark_healthy(self):
                return None

            def health_state(self):
                return {
                    "health_status": "healthy",
                    "last_error": None,
                    "last_error_at_ns": None,
                    "updated_at_ns": 1,
                }

        class Runtime:
            async def handle_pending_cases(
                self,
                *,
                limit,
                review=True,
                deliver=True,
                before_delivery=None,
            ):
                phase = "review" if review else "deliver"
                call_order.append(f"runtime-{phase}")
                return {
                    "reviewed": 1 if review else 0,
                    "delivered_to_lead": 0,
                    "review_attempted": 1 if review else 0,
                    "delivery_attempted": 0,
                    "review_failures": 0,
                    "delivery_failures": 0,
                }

        await _drain_durable(Broker(), Runtime())

        self.assertEqual(
            call_order[:4],
            ["broker-1", "runtime-review", "broker-2", "runtime-deliver"],
        )

    async def test_drain_delivers_successful_findings_before_raising_review_failure(
        self,
    ) -> None:
        phases: list[str] = []

        class Broker:
            def process_pending(self, *, limit):
                return {
                    "from_seq": 0,
                    "last_processed_seq": 0,
                    "processed": 0,
                    "opened": 0,
                    "closed": 0,
                }

        class Runtime:
            async def handle_pending_cases(
                self,
                *,
                limit,
                review=True,
                deliver=True,
                before_delivery=None,
            ):
                if review:
                    phases.append("review")
                    return {
                        "reviewed": 1,
                        "delivered_to_lead": 0,
                        "review_attempted": 2,
                        "delivery_attempted": 0,
                        "review_failures": 1,
                        "delivery_failures": 0,
                        "last_error": "review case 'bad': RuntimeError: bad schema",
                    }
                phases.append("deliver")
                return {
                    "reviewed": 0,
                    "delivered_to_lead": 1,
                    "review_attempted": 0,
                    "delivery_attempted": 1,
                    "review_failures": 0,
                    "delivery_failures": 0,
                }

        with self.assertRaisesRegex(RuntimeError, "bad schema"):
            await _drain_durable(Broker(), Runtime())

        self.assertEqual(phases, ["review", "deliver"])

    async def test_drain_surfaces_underlying_supervisor_failure(self) -> None:
        class Broker:
            def process_pending(self, *, limit):
                return {
                    "from_seq": 0,
                    "last_processed_seq": 0,
                    "processed": 0,
                    "opened": 0,
                    "closed": 0,
                }

        class Runtime:
            async def handle_pending_cases(
                self,
                *,
                limit,
                review=True,
                deliver=True,
                before_delivery=None,
            ):
                return {
                    "reviewed": 0,
                    "delivered_to_lead": 0,
                    "review_attempted": 1 if review else 0,
                    "delivery_attempted": 0,
                    "review_failures": 1 if review else 0,
                    "delivery_failures": 0,
                    "last_error": (
                        "review case 'case-7': RuntimeError: native capture schema failed"
                    ),
                }

        with self.assertRaisesRegex(
            RuntimeError,
            "case-7.*native capture schema failed",
        ):
            await _drain_durable(Broker(), Runtime())

    async def test_serve_retries_transient_sqlite_failure_even_if_health_write_fails(
        self,
    ) -> None:
        class Broker:
            def __init__(self):
                self.retry_attempts = 0

            def mark_retrying(self, _error):
                self.retry_attempts += 1
                raise sqlite3.OperationalError("health state is locked")

        drain = AsyncMock(
            side_effect=[
                sqlite3.OperationalError("semantic state is locked"),
                asyncio.CancelledError(),
            ]
        )
        broker = Broker()
        with (
            patch("supervisor_broker._drain_durable", new=drain),
            patch("supervisor_broker.asyncio.sleep", new=AsyncMock()),
            patch("builtins.print"),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await serve(
                    broker,
                    object(),
                    object(),
                    reconnect_seconds=0.01,
                )

        self.assertEqual(drain.await_count, 2)
        self.assertEqual(broker.retry_attempts, 1)


class SuperviseOnceTests(unittest.TestCase):
    def test_supervise_once_uses_full_durable_drain(self) -> None:
        expected = {
            "broker": {
                "processed": 1001,
                "opened": 2,
                "closed": 1,
                "from_seq": 1000,
                "last_processed_seq": 2001,
            },
            "supervisor": {
                "reviewed": 21,
                "delivered_to_lead": 20,
                "review_attempted": 21,
                "delivery_attempted": 20,
                "review_failures": 0,
                "delivery_failures": 0,
            },
            "health": {
                "health_status": "healthy",
                "last_error": None,
                "last_error_at_ns": None,
                "updated_at_ns": 1,
            },
        }

        async def fake_drain(_broker, _runtime):
            return expected

        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "qiqi_delegate.sqlite3"
            with patch(
                "supervisor_broker._drain_durable",
                side_effect=fake_drain,
            ) as drain:
                with patch("builtins.print") as printed:
                    rc = main(["--supervise-once", "--db", str(db_path)])

        self.assertEqual(rc, 0)
        self.assertEqual(drain.call_count, 1)
        printed.assert_called_once_with(json.dumps(expected, sort_keys=True))


@unittest.skipIf(os.name == "nt", "Unix-domain Herdr socket test")
class HerdrLifecycleSubscriberTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    async def _close_writer(writer: asyncio.StreamWriter) -> None:
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass

    async def test_idle_subscription_emits_periodic_sqlite_wakeup(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        socket_path = Path(temp.name) / "herdr.sock"
        completed = asyncio.Event()
        seen_methods: list[str] = []

        async def handler(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            request = json.loads((await reader.readline()).decode("utf-8"))
            method = request["method"]
            seen_methods.append(method)
            try:
                if method == "session.snapshot":
                    writer.write(
                        (
                            json.dumps(
                                {"id": request["id"], "result": {"workspaces": []}}
                            )
                            + "\n"
                        ).encode("utf-8")
                    )
                    await writer.drain()
                    return
                if method == "events.subscribe":
                    writer.write(
                        (
                            json.dumps(
                                {
                                    "id": request["id"],
                                    "result": {"type": "subscription_started"},
                                }
                            )
                            + "\n"
                        ).encode("utf-8")
                    )
                    await writer.drain()
                    await reader.read()
                    return
                self.fail(f"unexpected Herdr method: {method}")
            finally:
                await self._close_writer(writer)
                if method == "events.subscribe":
                    completed.set()

        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        async with server:
            subscriber = HerdrLifecycleSubscriber(
                socket_path,
                event_idle_seconds=0.05,
            )
            stream = subscriber.stream_once(yield_ready=True)
            ready = await anext(stream)
            idle = await asyncio.wait_for(anext(stream), timeout=1)
            self.assertEqual(ready["event"], "subscription_started")
            self.assertEqual(idle["event"], "subscription_idle")
            await stream.aclose()
            await asyncio.wait_for(completed.wait(), timeout=2)

        self.assertEqual(
            seen_methods,
            ["session.snapshot", "events.subscribe"],
        )

    async def test_subscriber_uses_separate_snapshot_and_event_connections(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        socket_path = Path(temp.name) / "herdr.sock"
        seen: list[dict] = []
        completed = asyncio.Event()
        connection_count = 0

        async def handler(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            nonlocal connection_count
            connection_count += 1
            request = json.loads((await reader.readline()).decode("utf-8"))
            seen.append(request)
            method = request["method"]
            try:
                if method == "session.snapshot":
                    writer.write(
                        (
                            json.dumps(
                                {
                                    "id": request["id"],
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
                    return
                if method == "events.subscribe":
                    writer.write(
                        (
                            json.dumps(
                                {
                                    "id": request["id"],
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
                    return
                self.fail(f"unexpected Herdr method: {method}")
            finally:
                await self._close_writer(writer)
                if method == "events.subscribe":
                    completed.set()

        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        async with server:
            subscriber = HerdrLifecycleSubscriber(socket_path)
            stream = subscriber.stream_once(yield_ready=True)
            ready = await anext(stream)
            self.assertEqual(ready["event"], "subscription_started")
            event = await anext(stream)
            self.assertEqual(event["event"], "workspace_created")
            await stream.aclose()
            await asyncio.wait_for(completed.wait(), timeout=2)

        self.assertEqual(connection_count, 2)
        self.assertEqual(
            [item["method"] for item in seen],
            ["session.snapshot", "events.subscribe"],
        )
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

    async def test_subscription_readiness_is_emitted_only_after_ack(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        socket_path = Path(temp.name) / "herdr.sock"
        acknowledged = asyncio.Event()
        release_event = asyncio.Event()

        async def handler(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            request = json.loads((await reader.readline()).decode("utf-8"))
            method = request["method"]
            try:
                if method == "session.snapshot":
                    writer.write(
                        (
                            json.dumps(
                                {"id": request["id"], "result": {"workspaces": []}}
                            )
                            + "\n"
                        ).encode("utf-8")
                    )
                    await writer.drain()
                    return
                if method == "events.subscribe":
                    writer.write(
                        (
                            json.dumps(
                                {
                                    "id": request["id"],
                                    "result": {"type": "subscription_started"},
                                }
                            )
                            + "\n"
                        ).encode("utf-8")
                    )
                    await writer.drain()
                    acknowledged.set()
                    await release_event.wait()
                    writer.write(
                        (
                            json.dumps(
                                {
                                    "event": "workspace_created",
                                    "data": {"workspace_id": "w-after-ready"},
                                }
                            )
                            + "\n"
                        ).encode("utf-8")
                    )
                    await writer.drain()
                    await reader.read()
                    return
                self.fail(f"unexpected Herdr method: {method}")
            finally:
                await self._close_writer(writer)

        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        async with server:
            subscriber = HerdrLifecycleSubscriber(socket_path)
            stream = subscriber.stream_once(yield_ready=True)
            ready = await anext(stream)
            self.assertTrue(acknowledged.is_set())
            self.assertEqual(ready["event"], "subscription_started")
            release_event.set()
            event = await anext(stream)
            self.assertEqual(event["data"]["workspace_id"], "w-after-ready")
            await stream.aclose()

    async def test_snapshot_handshake_times_out_instead_of_stalling(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        socket_path = Path(temp.name) / "herdr.sock"
        completed = asyncio.Event()

        async def handler(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            try:
                request = json.loads((await reader.readline()).decode("utf-8"))
                self.assertEqual(request["method"], "session.snapshot")
                await reader.read()
            finally:
                await self._close_writer(writer)
                completed.set()

        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        async with server:
            subscriber = HerdrLifecycleSubscriber(
                socket_path,
                handshake_timeout_seconds=0.05,
            )
            stream = subscriber.stream_once(yield_ready=True)
            with self.assertRaisesRegex(
                HerdrSubscriptionError,
                "session.snapshot timed out",
            ):
                await anext(stream)
            await asyncio.wait_for(completed.wait(), timeout=2)

    async def test_subscribe_handshake_times_out_instead_of_stalling(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        socket_path = Path(temp.name) / "herdr.sock"
        completed = asyncio.Event()

        async def handler(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            request = json.loads((await reader.readline()).decode("utf-8"))
            method = request["method"]
            try:
                if method == "session.snapshot":
                    writer.write(
                        (
                            json.dumps(
                                {"id": request["id"], "result": {"workspaces": []}}
                            )
                            + "\n"
                        ).encode("utf-8")
                    )
                    await writer.drain()
                    return
                if method == "events.subscribe":
                    await reader.read()
                    return
                self.fail(f"unexpected Herdr method: {method}")
            finally:
                await self._close_writer(writer)
                if method == "events.subscribe":
                    completed.set()

        server = await asyncio.start_unix_server(handler, path=str(socket_path))
        async with server:
            subscriber = HerdrLifecycleSubscriber(
                socket_path,
                handshake_timeout_seconds=0.05,
            )
            stream = subscriber.stream_once(yield_ready=True)
            with self.assertRaisesRegex(
                HerdrSubscriptionError,
                "events.subscribe timed out",
            ):
                await anext(stream)
            await asyncio.wait_for(completed.wait(), timeout=2)

    async def test_events_lost_fails_to_reconnect_path_instead_of_guessing(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        socket_path = Path(temp.name) / "herdr.sock"

        async def handler(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            request = json.loads((await reader.readline()).decode("utf-8"))
            method = request["method"]
            try:
                if method == "session.snapshot":
                    writer.write(
                        (
                            json.dumps(
                                {"id": request["id"], "result": {"workspaces": []}}
                            )
                            + "\n"
                        ).encode("utf-8")
                    )
                    await writer.drain()
                    return
                if method == "events.subscribe":
                    writer.write(
                        (
                            json.dumps(
                                {
                                    "id": request["id"],
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
                                    "id": request["id"],
                                    "error": {
                                        "code": "events_lost",
                                        "message": (
                                            "retained lifecycle history was exceeded"
                                        ),
                                    },
                                }
                            )
                            + "\n"
                        ).encode("utf-8")
                    )
                    await writer.drain()
                    return
                self.fail(f"unexpected Herdr method: {method}")
            finally:
                await self._close_writer(writer)

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
