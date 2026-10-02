from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.server.mcpserver.exceptions import ToolError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import task_graph_mcp  # noqa: E402
from core import SessionStore, build_task_packet  # noqa: E402
from supervisor_broker import SupervisorBroker  # noqa: E402
from supervisor_control import AutonomousSupervisorRuntime  # noqa: E402
from task_graph import GraphNode  # noqa: E402


class Phase4SemanticStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "qiqi_delegate.sqlite3"
        self.store = SessionStore(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_work_item_revision_is_monotonic_and_idempotent(self) -> None:
        first = self.store.record_work_item_revision(
            work_item_id="e2e:008",
            work_item_revision=3,
            reason="initial runtime observation",
        )
        same = self.store.record_work_item_revision(
            work_item_id="e2e:008",
            work_item_revision=3,
            reason="same revision observed again",
        )
        newer = self.store.record_work_item_revision(
            work_item_id="e2e:008",
            work_item_revision=4,
            reason="material requirement changed",
        )

        self.assertFalse(first["idempotent"])
        self.assertTrue(same["idempotent"])
        self.assertEqual(first["event_seq"], same["event_seq"])
        self.assertFalse(newer["idempotent"])
        with self.assertRaisesRegex(RuntimeError, "must be monotonic"):
            self.store.record_work_item_revision(
                work_item_id="e2e:008",
                work_item_revision=2,
            )

    def test_accept_disposition_emits_candidate_accepted_transition(self) -> None:
        packet = build_task_packet(
            objective="Produce candidate.",
            scope=["repo work"],
            acceptance_criteria=["tests pass"],
        )
        self.store.record_turn(
            turn_id="turn-accept",
            session_id="session-accept",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=packet,
            agent_response="candidate evidence",
        )
        disposition = self.store.record_lead_disposition(
            turn_id="turn-accept",
            action="accept",
            reason="reviewed exact candidate",
            candidate_id="sha256:candidate",
        )
        events = self.store.list_slp_events()
        self.assertEqual(
            [event["event_type"] for event in events],
            ["peer.response", "lead.disposition", "candidate.accepted"],
        )
        self.assertEqual(events[-1]["candidate_id"], "sha256:candidate")
        self.assertEqual(
            events[-1]["payload"]["disposition_id"],
            disposition["disposition_id"],
        )

    def test_direct_defer_requires_and_persists_owner_checkpoint(self) -> None:
        packet = build_task_packet(
            objective="Produce actionable response.",
            scope=["repo work"],
            acceptance_criteria=["lead closes loop"],
        )
        self.store.record_turn(
            turn_id="turn-defer",
            session_id="session-defer",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=packet,
            agent_response="DEPENDENCY_REQUEST: need upstream contract",
        )

        with self.assertRaisesRegex(
            ValueError,
            "defer disposition requires owner and return_checkpoint",
        ):
            self.store.record_lead_disposition(
                turn_id="turn-defer",
                action="defer",
                reason="waiting for upstream contract",
            )

        disposition = self.store.record_lead_disposition(
            turn_id="turn-defer",
            action="defer",
            reason="waiting for upstream contract",
            owner="lead",
            return_checkpoint="after upstream contract is accepted",
        )
        self.assertEqual(disposition["owner"], "lead")
        self.assertEqual(
            disposition["return_checkpoint"],
            "after upstream contract is accepted",
        )
        event = [
            item
            for item in self.store.list_slp_events()
            if item["event_type"] == "lead.disposition"
        ][0]
        self.assertEqual(event["payload"]["owner"], "lead")
        self.assertEqual(
            event["payload"]["return_checkpoint"],
            "after upstream contract is accepted",
        )

    def test_disposition_rejects_work_item_override_mismatch(self) -> None:
        packet = build_task_packet(
            objective="Produce tracked candidate.",
            scope=["repo work"],
            acceptance_criteria=["tests pass"],
            context={
                "trusted_facts": [
                    {
                        "fact": (
                            "work_item_path=/tmp/work-items/e2e-a; "
                            "id=e2e:a; revision=2"
                        ),
                        "source": "canonical Work Item locator",
                    }
                ]
            },
        )
        self.store.record_turn(
            turn_id="turn-provenance",
            session_id="session-provenance",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=packet,
            agent_response="candidate evidence",
        )

        with self.assertRaisesRegex(RuntimeError, "does not match the captured Peer turn"):
            self.store.record_lead_disposition(
                turn_id="turn-provenance",
                action="accept",
                reason="incorrect override",
                work_item_id="e2e:b",
                work_item_revision=9,
            )

        self.assertIsNone(self.store.get_lead_disposition("turn-provenance"))
        self.assertEqual(
            [event["event_type"] for event in self.store.list_slp_events()],
            ["peer.response"],
        )

    def test_peer_signal_locators_must_match_captured_turn(self) -> None:
        packet = build_task_packet(
            objective="Report tracked governance signal.",
            scope=["repo work"],
            acceptance_criteria=["signal is reconciled"],
            context={
                "trusted_facts": [
                    {
                        "fact": (
                            "work_item_path=/tmp/work-items/e2e-signal; "
                            "id=e2e:signal; revision=2"
                        ),
                        "source": "canonical Work Item locator",
                    }
                ]
            },
        )
        self.store.record_turn(
            turn_id="turn-signal-provenance",
            session_id="session-signal-provenance",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=packet,
            agent_response="REOPEN_REQUEST: premise changed",
        )

        with self.assertRaisesRegex(RuntimeError, "does not match the captured Peer turn"):
            self.store.record_peer_signal(
                turn_id="turn-signal-provenance",
                signal="REOPEN_REQUEST",
                work_item_id="e2e:other",
                work_item_revision=9,
            )

        self.store.record_peer_signal(
            turn_id="turn-signal-provenance",
            signal="REOPEN_REQUEST",
        )
        with self.assertRaisesRegex(RuntimeError, "does not match the durable Peer signal"):
            self.store.record_peer_signal_resolution(
                turn_id="turn-signal-provenance",
                signal="REOPEN_REQUEST",
                reason="incorrect resolution provenance",
                work_item_id="e2e:other",
                work_item_revision=9,
            )

        self.assertEqual(
            [event["event_type"] for event in self.store.list_slp_events()],
            ["peer.response", "peer.signal"],
        )

    def test_candidate_reconciliation_requires_current_revision_and_tracked_replacement(
        self,
    ) -> None:
        stale_packet = build_task_packet(
            objective="Produce revision 1 candidate.",
            scope=["repo work"],
            acceptance_criteria=["tests pass"],
            context={
                "trusted_facts": [
                    {
                        "fact": (
                            "work_item_path=/tmp/work-items/e2e-reconcile; "
                            "id=e2e:reconcile; revision=1"
                        ),
                        "source": "canonical Work Item locator",
                    }
                ]
            },
        )
        replacement_packet = build_task_packet(
            objective="Untracked unrelated result.",
            scope=["repo work"],
            acceptance_criteria=["tests pass"],
        )
        self.store.record_turn(
            turn_id="turn-stale",
            session_id="session-stale",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=stale_packet,
            agent_response="revision 1 result",
        )
        self.store.record_turn(
            turn_id="turn-untracked",
            session_id="session-untracked",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=replacement_packet,
            agent_response="untracked result",
        )
        self.store.record_work_item_revision(
            work_item_id="e2e:reconcile",
            work_item_revision=2,
            reason="material requirement change",
        )

        with self.assertRaisesRegex(RuntimeError, "latest recorded Work Item revision"):
            self.store.record_candidate_reconciliation(
                stale_turn_id="turn-stale",
                resolution="revalidated",
                reason="invalid future revision",
                work_item_id="e2e:reconcile",
                work_item_revision=99,
            )

        with self.assertRaisesRegex(RuntimeError, "exact current revision"):
            self.store.record_candidate_reconciliation(
                stale_turn_id="turn-stale",
                resolution="superseded",
                reason="invalid replacement provenance",
                work_item_id="e2e:reconcile",
                work_item_revision=2,
                replacement_turn_id="turn-untracked",
            )

        event_seq = self.store.record_candidate_reconciliation(
            stale_turn_id="turn-stale",
            resolution="revalidated",
            reason="candidate remains valid under revision 2",
            work_item_id="e2e:reconcile",
            work_item_revision=2,
        )
        event = next(
            item for item in self.store.list_slp_events() if item["seq"] == event_seq
        )
        self.assertEqual(event["event_type"], "candidate.reconciled")
        self.assertEqual(event["work_item_revision"], 2)

    def test_schema_upgrade_backfills_legacy_turn_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "legacy.sqlite3"
            packet = build_task_packet(
                objective="Legacy captured result.",
                scope=["repo evidence"],
                acceptance_criteria=["report evidence"],
            )
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE sessions (
                        session_id TEXT PRIMARY KEY,
                        repository TEXT NOT NULL,
                        agent TEXT NOT NULL,
                        created_at_ns INTEGER NOT NULL,
                        updated_at_ns INTEGER NOT NULL
                    );
                    CREATE TABLE turns (
                        turn_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        repository TEXT NOT NULL,
                        route TEXT NOT NULL,
                        state TEXT NOT NULL,
                        native_turn_id TEXT,
                        task_packet_json TEXT NOT NULL,
                        agent_response TEXT NOT NULL,
                        created_at_ns INTEGER NOT NULL
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                    ("legacy-session", "repo-a", "claude", 10, 10),
                )
                conn.execute(
                    "INSERT INTO turns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "legacy-turn",
                        "legacy-session",
                        "repo-a",
                        "claude-balanced",
                        "settled",
                        None,
                        packet.to_json(),
                        "legacy result",
                        11,
                    ),
                )

            # The first broker connection performs the legacy backfill and then starts
            # its own explicit BEGIN IMMEDIATE transaction. This is the upgrade path that
            # previously failed with "cannot start a transaction within a transaction".
            broker_result = SupervisorBroker(db_path).process_pending()
            self.assertEqual(broker_result["processed"], 1)

            upgraded = SessionStore(db_path)
            first = upgraded.list_slp_events()
            second = upgraded.list_slp_events()

        peer_events = [event for event in first if event["event_type"] == "peer.response"]
        self.assertEqual(len(peer_events), 1)
        self.assertEqual(peer_events[0]["turn_id"], "legacy-turn")
        self.assertEqual(peer_events[0]["payload"]["backfilled_from"], "turns")
        self.assertEqual(len(second), len(first))

    def test_explicit_peer_signal_requires_captured_turn(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unknown turn_id"):
            self.store.record_peer_signal(
                turn_id="missing",
                signal="REOPEN_REQUEST",
            )

        packet = build_task_packet(
            objective="Investigate premise.",
            scope=["repo evidence"],
            acceptance_criteria=["report evidence"],
        )
        self.store.record_turn(
            turn_id="turn-signal",
            session_id="session-signal",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=packet,
            agent_response="REOPEN_REQUEST with evidence",
        )
        seq = self.store.record_peer_signal(
            turn_id="turn-signal",
            signal="REOPEN_REQUEST",
            details="premise contradicted",
        )
        event = next(item for item in self.store.list_slp_events() if item["seq"] == seq)
        self.assertEqual(event["event_type"], "peer.signal")
        self.assertEqual(event["payload"]["signal"], "REOPEN_REQUEST")

    def test_signal_resolution_requires_matching_explicit_signal(self) -> None:
        packet = build_task_packet(
            objective="Investigate dependency.",
            scope=["repo evidence"],
            acceptance_criteria=["report evidence"],
        )
        self.store.record_turn(
            turn_id="turn-resolve-signal",
            session_id="session-resolve-signal",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=packet,
            agent_response="DEPENDENCY_REQUEST with evidence",
        )
        with self.assertRaisesRegex(RuntimeError, "matching prior explicit Peer signal"):
            self.store.record_peer_signal_resolution(
                turn_id="turn-resolve-signal",
                signal="DEPENDENCY_REQUEST",
                reason="dependency resolved",
            )

        self.store.record_peer_signal(
            turn_id="turn-resolve-signal",
            signal="DEPENDENCY_REQUEST",
            details="need upstream contract",
        )
        seq = self.store.record_peer_signal_resolution(
            turn_id="turn-resolve-signal",
            signal="DEPENDENCY_REQUEST",
            reason="upstream contract accepted",
        )
        event = next(item for item in self.store.list_slp_events() if item["seq"] == seq)
        self.assertEqual(event["event_type"], "peer.signal_resolved")
        self.assertEqual(event["payload"]["signal"], "DEPENDENCY_REQUEST")




class DirectDelegationPhase4IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tracked_delegation_emits_revision_claim_response_and_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo_path = root / "repo-a"
            repo_path.mkdir()
            db_path = root / "qiqi_delegate.sqlite3"
            store = SessionStore(db_path)
            capture_path = root / "capture.json"

            context = server.TaskContextInput(
                trusted_facts=[
                    server.TrustedFactInput(
                        fact=(
                            "work_item_path=/tmp/work-items/e2e-008; "
                            "id=e2e:008; revision=4"
                        ),
                        source="canonical Work Item locator",
                    )
                ]
            )

            with (
                patch.object(server, "_store", store),
                patch.object(server, "_resolve_repo", return_value=repo_path),
                patch.object(
                    server,
                    "_resolve_route",
                    return_value=(
                        "claude",
                        {"adapter": "claude", "command": "claude"},
                        {"model": "sonnet", "args": []},
                    ),
                ),
                patch.object(server.shutil, "which", return_value="/bin/true"),
                patch.object(server, "_ensure_herdr_server", new=AsyncMock()),
                patch.object(server, "_require_current_integration", new=AsyncMock()),
                patch.object(server, "_claim_resources", new=AsyncMock()),
                patch.object(server, "_release_resources", new=AsyncMock()) as release,
                patch.object(
                    server,
                    "_register_active_capture",
                    return_value=capture_path,
                ),
                patch.object(server, "_remove_active_capture"),
                patch.object(server, "_build_handoff_args", return_value=[]),
                patch.object(server, "_build_interactive_args", return_value=[]),
                patch.object(
                    server,
                    "_create_herdr_workspace",
                    new=AsyncMock(return_value=("workspace-1", "pane-1")),
                ),
                patch.object(
                    server,
                    "_start_interactive_agent",
                    new=AsyncMock(return_value=("agent-1", {})),
                ),
                patch.object(server, "_validate_reported_session_if_present"),
                patch.object(
                    server,
                    "_prompt_and_wait",
                    new=AsyncMock(return_value=("settled", {})),
                ),
                patch.object(
                    server,
                    "_wait_for_native_session",
                    new=AsyncMock(return_value="native-session-1"),
                ),
                patch.object(
                    server,
                    "_wait_for_result_capture",
                    new=AsyncMock(
                        return_value={
                            "state": "settled",
                            "native_turn_id": "native-turn-1",
                            "agent_response": "peer final response",
                        }
                    ),
                ),
                patch.object(server, "_close_herdr_workspace", new=AsyncMock()),
            ):
                result = await server.delegate_repo_task(
                    repository="repo-a",
                    route="claude-balanced",
                    objective="Implement one tracked change.",
                    scope=["pricing behavior"],
                    acceptance_criteria=["focused tests pass"],
                    context=context,
                )

            self.assertEqual(result["state"], "settled")
            release.assert_awaited_once()
            events = store.list_slp_events()
            self.assertEqual(
                [event["event_type"] for event in events],
                [
                    "work_item.revision_changed",
                    "write_scope.claimed",
                    "peer.dispatched",
                    "peer.response",
                    "write_scope.released",
                ],
            )
            claim = events[1]
            release_event = events[-1]
            self.assertEqual(claim["payload"]["scope"], ["*"])
            self.assertEqual(claim["payload"]["claim_id"], release_event["payload"]["claim_id"])
            self.assertEqual(claim["work_item_revision"], 4)
            self.assertEqual(release_event["work_item_revision"], 4)


    async def test_durable_write_claim_blocks_restart_overlap_before_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo_path = root / "repo-a"
            repo_path.mkdir()
            hook_path = root / "result-hook.py"
            hook_path.write_text("# hook\n", encoding="utf-8")
            store = SessionStore(root / "qiqi_delegate.sqlite3")
            store.record_write_scope_claim(
                claim_id="repo:repo-a:turn:orphaned",
                repository="repo-a",
                owner="orphaned-turn",
                scope=["*"],
                turn_id="orphaned-turn",
            )
            release = AsyncMock()

            with (
                patch.object(server, "_store", store),
                patch.object(server, "_resolve_repo", return_value=repo_path),
                patch.object(
                    server,
                    "_resolve_route",
                    return_value=(
                        "claude",
                        {"adapter": "claude", "command": "claude"},
                        {"model": "sonnet", "args": []},
                    ),
                ),
                patch.object(server.shutil, "which", return_value="/bin/true"),
                patch.object(server, "RESULT_HOOK_PATH", hook_path),
                patch.object(server, "_ensure_herdr_server", new=AsyncMock()),
                patch.object(server, "_require_current_integration", new=AsyncMock()),
                patch.object(server, "_claim_resources", new=AsyncMock()),
                patch.object(server, "_release_resources", new=release),
                patch.object(server, "_record_peer_dispatch") as dispatch,
            ):
                with self.assertRaisesRegex(
                    ToolError,
                    "active durable write-scope claim",
                ):
                    await server.delegate_repo_task(
                        repository="repo-a",
                        route="claude-balanced",
                        objective="Start a replacement writer.",
                        scope=["pricing"],
                        acceptance_criteria=["tests pass"],
                    )

            dispatch.assert_not_called()
            release.assert_awaited_once()
            active = store.list_active_write_scope_claims(repository="repo-a")
            self.assertEqual([item["claim_id"] for item in active], [
                "repo:repo-a:turn:orphaned"
            ])
            self.assertEqual(
                [
                    event["event_type"]
                    for event in store.list_slp_events()
                    if event["turn_id"] != "orphaned-turn"
                ],
                [],
            )

    async def test_write_scope_release_survives_peer_dispatch_recording_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo_path = root / "repo-a"
            repo_path.mkdir()
            hook_path = root / "result-hook.py"
            hook_path.write_text("# hook\n", encoding="utf-8")
            store = SessionStore(root / "qiqi_delegate.sqlite3")
            original_record_slp_event = store.record_slp_event
            release = AsyncMock()

            def fail_dispatch(**kwargs):
                if kwargs.get("event_type") == "peer.dispatched":
                    raise RuntimeError("dispatch event insert failed")
                return original_record_slp_event(**kwargs)

            with ExitStack() as stack:
                stack.enter_context(patch.object(server, "_store", store))
                stack.enter_context(
                    patch.object(server, "_resolve_repo", return_value=repo_path)
                )
                stack.enter_context(
                    patch.object(
                        server,
                        "_resolve_route",
                        return_value=(
                            "claude",
                            {"adapter": "claude", "command": "claude"},
                            {"model": "sonnet", "args": []},
                        ),
                    )
                )
                stack.enter_context(
                    patch.object(server.shutil, "which", return_value="/bin/true")
                )
                stack.enter_context(patch.object(server, "RESULT_HOOK_PATH", hook_path))
                stack.enter_context(
                    patch.object(server, "_ensure_herdr_server", new=AsyncMock())
                )
                stack.enter_context(
                    patch.object(server, "_require_current_integration", new=AsyncMock())
                )
                stack.enter_context(
                    patch.object(server, "_claim_resources", new=AsyncMock())
                )
                stack.enter_context(
                    patch.object(server, "_release_resources", new=release)
                )
                stack.enter_context(
                    patch.object(
                        server,
                        "_record_peer_dispatch",
                        side_effect=RuntimeError("dispatch event insert failed"),
                    )
                )

                with self.assertRaisesRegex(ToolError, "dispatch event insert failed"):
                    await server.delegate_repo_task(
                        repository="repo-a",
                        route="claude-balanced",
                        objective="Implement one change.",
                        scope=["pricing"],
                        acceptance_criteria=["tests pass"],
                    )

            release.assert_awaited_once()
            self.assertEqual(
                [event["event_type"] for event in store.list_slp_events()],
                ["write_scope.claimed", "write_scope.released"],
            )


    async def test_write_scope_release_survives_herdr_workspace_close_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo_path = root / "repo-a"
            repo_path.mkdir()
            store = SessionStore(root / "qiqi_delegate.sqlite3")
            capture_path = root / "capture.json"
            release = AsyncMock()

            with ExitStack() as stack:
                stack.enter_context(patch.object(server, "_store", store))
                stack.enter_context(
                    patch.object(server, "_resolve_repo", return_value=repo_path)
                )
                stack.enter_context(
                    patch.object(
                        server,
                        "_resolve_route",
                        return_value=(
                            "claude",
                            {"adapter": "claude", "command": "claude"},
                            {"model": "sonnet", "args": []},
                        ),
                    )
                )
                stack.enter_context(
                    patch.object(server.shutil, "which", return_value="/bin/true")
                )
                stack.enter_context(
                    patch.object(server, "_ensure_herdr_server", new=AsyncMock())
                )
                stack.enter_context(
                    patch.object(server, "_require_current_integration", new=AsyncMock())
                )
                stack.enter_context(
                    patch.object(server, "_claim_resources", new=AsyncMock())
                )
                stack.enter_context(
                    patch.object(server, "_release_resources", new=release)
                )
                stack.enter_context(
                    patch.object(
                        server, "_register_active_capture", return_value=capture_path
                    )
                )
                stack.enter_context(patch.object(server, "_remove_active_capture"))
                stack.enter_context(
                    patch.object(server, "_build_handoff_args", return_value=[])
                )
                stack.enter_context(
                    patch.object(server, "_build_interactive_args", return_value=[])
                )
                stack.enter_context(
                    patch.object(
                        server,
                        "_create_herdr_workspace",
                        new=AsyncMock(return_value=("workspace-1", "pane-1")),
                    )
                )
                stack.enter_context(
                    patch.object(
                        server,
                        "_start_interactive_agent",
                        new=AsyncMock(return_value=("agent-1", {})),
                    )
                )
                stack.enter_context(
                    patch.object(server, "_validate_reported_session_if_present")
                )
                stack.enter_context(
                    patch.object(
                        server,
                        "_prompt_and_wait",
                        new=AsyncMock(return_value=("settled", {})),
                    )
                )
                stack.enter_context(
                    patch.object(
                        server,
                        "_wait_for_native_session",
                        new=AsyncMock(return_value="native-session-1"),
                    )
                )
                stack.enter_context(
                    patch.object(
                        server,
                        "_wait_for_result_capture",
                        new=AsyncMock(
                            return_value={
                                "state": "settled",
                                "native_turn_id": "native-turn-1",
                                "agent_response": "peer final response",
                            }
                        ),
                    )
                )
                stack.enter_context(
                    patch.object(
                        server,
                        "_close_herdr_workspace",
                        new=AsyncMock(
                            side_effect=RuntimeError("transient close failure")
                        ),
                    )
                )
                with self.assertRaisesRegex(ToolError, "transient close failure"):
                    await server.delegate_repo_task(
                        repository="repo-a",
                        route="claude-balanced",
                        objective="Implement one change.",
                        scope=["pricing"],
                        acceptance_criteria=["tests pass"],
                    )

            release.assert_awaited_once()
            self.assertIn(
                "write_scope.released",
                [event["event_type"] for event in store.list_slp_events()],
            )


class TaskGraphPhase4IntegrationTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def dispatching_delegate(
        *,
        turn_id: str,
        result: dict | None = None,
        error: Exception | None = None,
    ) -> AsyncMock:
        async def execute(**kwargs):
            server._record_peer_dispatch(
                turn_id=turn_id,
                repository=kwargs["repository"],
                route=kwargs["route"],
                work_item_id=None,
                work_item_revision=None,
            )
            if error is not None:
                raise error
            assert result is not None
            return result

        return AsyncMock(side_effect=execute)

    async def test_downstream_execution_emits_dependency_consumed_from_upstream_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "qiqi_delegate.sqlite3"
            store = SessionStore(db_path)
            source_packet = build_task_packet(
                objective="Produce upstream contract.",
                scope=["contract"],
                acceptance_criteria=["contract evidence"],
            )
            store.record_turn(
                turn_id="turn-upstream",
                session_id="session-upstream",
                repository="upstream",
                agent="claude",
                route="claude-balanced",
                state="settled",
                native_turn_id=None,
                packet=source_packet,
                agent_response="accepted upstream evidence",
            )
            store.record_lead_disposition(
                turn_id="turn-upstream",
                action="accept",
                reason="upstream accepted",
            )

            consumer_packet = build_task_packet(
                objective="Consume accepted upstream semantics.",
                scope=["downstream"],
                acceptance_criteria=["downstream verification"],
                context={
                    "trusted_facts": [
                        {
                            "fact": (
                                "work_item_path=/tmp/work-items/e2e-008; "
                                "id=e2e:008; revision=5"
                            ),
                            "source": "canonical Work Item locator",
                        }
                    ]
                },
            )
            node = GraphNode(
                node_id="downstream",
                repository="downstream",
                task_packet=consumer_packet,
                depends_on=("upstream",),
                route="claude-balanced",
            )
            graph_store = MagicMock()
            graph_store.get_node.return_value = {"turn_id": "turn-upstream"}
            graph_runtime = SimpleNamespace(store=graph_store)
            delegate = self.dispatching_delegate(
                turn_id="turn-downstream",
                result={
                    "session_id": "session-downstream",
                    "turn_id": "turn-downstream",
                    "state": "settled",
                    "agent_response": "downstream evidence",
                },
            )

            with (
                patch.object(task_graph_mcp, "_store", store),
                patch.object(task_graph_mcp, "_graph_runtime", graph_runtime),
                patch.object(server, "_store", store),
                patch.object(task_graph_mcp, "delegate_repo_task", delegate),
            ):
                await task_graph_mcp._execute_repo_task(
                    node,
                    session_id=None,
                    graph_run_id="graph-1",
                )

            dependency_events = [
                event
                for event in store.list_slp_events()
                if event["event_type"] == "dependency.consumed"
            ]
            self.assertEqual(len(dependency_events), 1)
            event = dependency_events[0]
            self.assertEqual(event["payload"]["source_turn_id"], "turn-upstream")
            self.assertIsNone(event["turn_id"])
            self.assertEqual(event["graph_run_id"], "graph-1")
            self.assertEqual(event["node_id"], "downstream")
            self.assertEqual(event["work_item_id"], "e2e:008")
            self.assertEqual(event["work_item_revision"], 5)


    async def test_dependency_consumed_is_persisted_before_downstream_transport_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(Path(temp) / "qiqi_delegate.sqlite3")
            source_packet = build_task_packet(
                objective="Produce upstream contract.",
                scope=["contract"],
                acceptance_criteria=["contract evidence"],
            )
            store.record_turn(
                turn_id="turn-upstream-failure",
                session_id="session-upstream-failure",
                repository="upstream",
                agent="claude",
                route="claude-balanced",
                state="settled",
                native_turn_id=None,
                packet=source_packet,
                agent_response="upstream evidence",
            )
            store.record_lead_disposition(
                turn_id="turn-upstream-failure",
                action="accept",
                reason="upstream accepted before downstream dispatch",
            )
            consumer_packet = build_task_packet(
                objective="Consume upstream contract.",
                scope=["downstream"],
                acceptance_criteria=["downstream evidence"],
            )
            node = GraphNode(
                node_id="downstream",
                repository="downstream",
                task_packet=consumer_packet,
                depends_on=("upstream",),
                route="claude-balanced",
            )
            graph_store = MagicMock()
            graph_store.get_node.return_value = {"turn_id": "turn-upstream-failure"}
            graph_runtime = SimpleNamespace(store=graph_store)

            delegate = self.dispatching_delegate(
                turn_id="turn-downstream-failure",
                error=ToolError("final response transport failed"),
            )
            with (
                patch.object(task_graph_mcp, "_store", store),
                patch.object(task_graph_mcp, "_graph_runtime", graph_runtime),
                patch.object(server, "_store", store),
                patch.object(task_graph_mcp, "delegate_repo_task", delegate),
            ):
                with self.assertRaises(ToolError):
                    await task_graph_mcp._execute_repo_task(
                        node,
                        session_id=None,
                        graph_run_id="graph-failure",
                    )

            events = [
                event
                for event in store.list_slp_events()
                if event["event_type"] == "dependency.consumed"
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(
                events[0]["payload"]["source_turn_id"],
                "turn-upstream-failure",
            )
            self.assertIsNone(events[0]["turn_id"])

    async def test_legacy_satisfied_dependency_without_accept_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(Path(temp) / "qiqi_delegate.sqlite3")
            source_packet = build_task_packet(
                objective="Legacy upstream result.",
                scope=["contract"],
                acceptance_criteria=["contract evidence"],
            )
            store.record_turn(
                turn_id="turn-legacy-upstream",
                session_id="session-legacy-upstream",
                repository="upstream",
                agent="claude",
                route="claude-balanced",
                state="settled",
                native_turn_id=None,
                packet=source_packet,
                agent_response="legacy upstream evidence",
            )
            node = GraphNode(
                node_id="downstream",
                repository="downstream",
                task_packet=build_task_packet(
                    objective="Consume upstream contract.",
                    scope=["downstream"],
                    acceptance_criteria=["downstream evidence"],
                ),
                depends_on=("upstream",),
                route="claude-balanced",
            )
            graph_store = MagicMock()
            graph_store.get_node.return_value = {"turn_id": "turn-legacy-upstream"}
            graph_runtime = SimpleNamespace(store=graph_store)
            delegate = self.dispatching_delegate(
                turn_id="turn-downstream",
                result={
                    "session_id": "session-downstream",
                    "turn_id": "turn-downstream",
                    "state": "settled",
                    "agent_response": "must not run",
                },
            )

            with (
                patch.object(task_graph_mcp, "_store", store),
                patch.object(task_graph_mcp, "_graph_runtime", graph_runtime),
                patch.object(server, "_store", store),
                patch.object(task_graph_mcp, "delegate_repo_task", delegate),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "lacks an explicit ACCEPT disposition",
                ):
                    await task_graph_mcp._execute_repo_task(
                        node,
                        session_id=None,
                        graph_run_id="legacy-graph",
                    )

            delegate.assert_awaited_once()
            event_types = [event["event_type"] for event in store.list_slp_events()]
            self.assertNotIn("dependency.consumed", event_types)
            self.assertNotIn("peer.dispatched", event_types)

    async def test_predispatch_failure_does_not_record_dependency_consumption(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(Path(temp) / "qiqi_delegate.sqlite3")
            packet = build_task_packet(
                objective="Accepted upstream.",
                scope=["contract"],
                acceptance_criteria=["accepted"],
            )
            store.record_turn(
                turn_id="turn-upstream-preflight",
                session_id="session-upstream-preflight",
                repository="upstream",
                agent="claude",
                route="claude-balanced",
                state="settled",
                native_turn_id=None,
                packet=packet,
                agent_response="accepted evidence",
            )
            store.record_lead_disposition(
                turn_id="turn-upstream-preflight",
                action="accept",
                reason="accepted",
            )
            node = GraphNode(
                node_id="downstream",
                repository="downstream",
                task_packet=build_task_packet(
                    objective="Consume dependency.",
                    scope=["downstream"],
                    acceptance_criteria=["done"],
                ),
                depends_on=("upstream",),
                route="claude-balanced",
            )
            graph_store = MagicMock()
            graph_store.get_node.return_value = {"turn_id": "turn-upstream-preflight"}
            graph_runtime = SimpleNamespace(store=graph_store)
            delegate = AsyncMock(side_effect=ToolError("integration preflight failed"))

            with (
                patch.object(task_graph_mcp, "_store", store),
                patch.object(task_graph_mcp, "_graph_runtime", graph_runtime),
                patch.object(task_graph_mcp, "delegate_repo_task", delegate),
            ):
                with self.assertRaises(ToolError):
                    await task_graph_mcp._execute_repo_task(
                        node,
                        session_id=None,
                        graph_run_id="graph-preflight",
                    )

            self.assertNotIn(
                "dependency.consumed",
                [event["event_type"] for event in store.list_slp_events()],
            )

    async def test_invalid_later_dependency_rolls_back_all_dispatch_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SessionStore(Path(temp) / "qiqi_delegate.sqlite3")
            packet = build_task_packet(
                objective="Upstream result.",
                scope=["contract"],
                acceptance_criteria=["evidence"],
            )
            for turn_id in ("turn-good", "turn-bad"):
                store.record_turn(
                    turn_id=turn_id,
                    session_id=f"session-{turn_id}",
                    repository="upstream",
                    agent="claude",
                    route="claude-balanced",
                    state="settled",
                    native_turn_id=None,
                    packet=packet,
                    agent_response="upstream evidence",
                )
            store.record_lead_disposition(
                turn_id="turn-good",
                action="accept",
                reason="first dependency accepted",
            )
            node = GraphNode(
                node_id="downstream",
                repository="downstream",
                task_packet=build_task_packet(
                    objective="Consume both dependencies.",
                    scope=["downstream"],
                    acceptance_criteria=["done"],
                ),
                depends_on=("good", "bad"),
                route="claude-balanced",
            )
            graph_store = MagicMock()
            graph_store.get_node.side_effect = lambda _run, node_id: {
                "turn_id": "turn-good" if node_id == "good" else "turn-bad"
            }
            graph_runtime = SimpleNamespace(store=graph_store)
            delegate = self.dispatching_delegate(
                turn_id="turn-downstream-multi",
                result={
                    "session_id": "session-downstream",
                    "turn_id": "turn-downstream-multi",
                    "state": "settled",
                    "agent_response": "must not run",
                },
            )

            with (
                patch.object(task_graph_mcp, "_store", store),
                patch.object(task_graph_mcp, "_graph_runtime", graph_runtime),
                patch.object(server, "_store", store),
                patch.object(task_graph_mcp, "delegate_repo_task", delegate),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "lacks an explicit ACCEPT disposition",
                ):
                    await task_graph_mcp._execute_repo_task(
                        node,
                        session_id=None,
                        graph_run_id="graph-multi",
                    )

            event_types = [event["event_type"] for event in store.list_slp_events()]
            self.assertNotIn("dependency.consumed", event_types)
            self.assertNotIn("peer.dispatched", event_types)


class _AutonomousE2EControlPlane:
    def __init__(self, store: SessionStore, turn_id: str):
        self.store = store
        self.turn_id = turn_id
        self.supervisor_wake_count = 0
        self.lead_wake_count = 0

    async def ensure_started(self):
        return {
            "workspace_id": "slp-control",
            "lead_agent_name": "lead",
            "supervisor_agent_name": "supervisor",
        }

    async def prompt_supervisor(self, packet):
        self.supervisor_wake_count += 1
        return {
            "case_id": packet["case_id"],
            "status": "issue",
            "observation": "Peer response exists without explicit Lead disposition.",
            "evidence": [
                f"peer_response_locator.turn_id={self.turn_id}",
                "disposition_state.recorded=false",
            ],
            "open_question_for_lead": (
                "What explicit technical disposition closes this Peer response?"
            ),
        }

    async def wake_lead(self, finding):
        self.lead_wake_count += 1
        self.store.record_lead_disposition(
            turn_id=self.turn_id,
            action="accept",
            reason="autonomous E2E Lead reviewed the existing Peer response",
        )


class AutonomousSupervisorE2E08Tests(unittest.IsolatedAsyncioTestCase):
    async def test_e2e08_no_human_supervisor_prompt_and_semantic_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "qiqi_delegate.sqlite3"
            store = SessionStore(db_path)
            broker = SupervisorBroker(db_path)
            packet = build_task_packet(
                objective="Produce E2E-08 candidate.",
                scope=["fixture"],
                acceptance_criteria=["fixture evidence"],
            )
            store.record_turn(
                turn_id="turn-e2e08",
                session_id="session-e2e08",
                repository="repo-a",
                agent="claude",
                route="claude-balanced",
                state="settled",
                native_turn_id=None,
                packet=packet,
                agent_response="E2E-08 Peer response",
            )

            first = broker.process_pending()
            self.assertEqual(first["opened"], 1)
            case = broker.list_cases()[0]
            self.assertEqual(case["status"], "OPEN")

            control = _AutonomousE2EControlPlane(store, "turn-e2e08")
            runtime = AutonomousSupervisorRuntime(
                state_db=db_path,
                control_plane=control,
            )
            autonomous = await runtime.handle_pending_cases()

            self.assertEqual(
                autonomous,
                {
                    "reviewed": 1,
                    "delivered_to_lead": 1,
                    "review_attempted": 1,
                    "delivery_attempted": 1,
                    "review_failures": 0,
                    "delivery_failures": 0,
                },
            )
            self.assertEqual(control.supervisor_wake_count, 1)
            self.assertEqual(control.lead_wake_count, 1)
            self.assertEqual(broker.list_cases()[0]["status"], "WAITING_FOR_EVIDENCE")

            final = broker.process_pending()
            self.assertGreaterEqual(final["closed"], 1)
            self.assertEqual(broker.list_cases()[0]["status"], "CLOSED")
            self.assertEqual(
                store.get_lead_disposition("turn-e2e08")["action"],
                "accept",
            )


if __name__ == "__main__":
    unittest.main()
