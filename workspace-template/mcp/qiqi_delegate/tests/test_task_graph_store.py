from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import SessionStore, build_task_packet  # noqa: E402
from task_graph import GraphNode, TaskGraph  # noqa: E402
from task_graph_scheduler import (  # noqa: E402
    GraphSnapshot,
    NodeDecision,
    NodeState,
    apply_decisions,
    derive_graph_state,
    initial_graph_snapshot,
    runnable_nodes,
)
from task_graph_store import GraphRuntimeStore  # noqa: E402


class TaskGraphRuntimeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
        self.store = GraphRuntimeStore(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def packet(self, objective: str):
        return build_task_packet(
            objective=objective,
            scope=["repository-local implementation"],
            acceptance_criteria=["focused verification passes"],
        )

    def graph(self) -> TaskGraph:
        return TaskGraph(
            nodes=(
                GraphNode(
                    node_id="contracts",
                    repository="contracts",
                    task_packet=self.packet("Update shared contract."),
                ),
                GraphNode(
                    node_id="backend",
                    repository="backend",
                    task_packet=self.packet("Update backend consumer."),
                    depends_on=("contracts",),
                ),
            )
        )

    def create_run(self) -> tuple[str, TaskGraph]:
        graph = self.graph()
        run_id = self.store.create_run(
            initial_graph_snapshot(graph),
            graph_run_id="graph-run-1",
        )
        return run_id, graph

    def finish_contracts_attempt(
        self,
        run_id: str,
        *,
        runtime_state: str = "settled",
        wave_id: str = "wave-1",
        session_id: str = "session-1",
        turn_id: str = "turn-1",
    ) -> str:
        attempt_id = self.store.start_attempt(run_id, "contracts", wave_id)
        self.store.bind_attempt_session(attempt_id, session_id)
        self.store.finish_attempt(
            attempt_id,
            runtime_state=runtime_state,
            session_id=session_id,
            turn_id=turn_id,
            result={
                "state": runtime_state,
                "session_id": session_id,
                "turn_id": turn_id,
                "agent_response": "native final response",
            },
        )
        return attempt_id

    def test_create_run_persists_only_execution_state_and_rehydrates_with_supplied_graph(self) -> None:
        run_id, graph = self.create_run()

        run = self.store.get_run(run_id)
        self.assertIsNotNone(run)
        self.assertEqual(run["graph_run_id"], run_id)
        self.assertIsNone(run["current_wave_id"])
        self.assertNotIn("graph_json", run)
        self.assertNotIn("task_packet_json", run)

        loaded = self.store.load_snapshot(run_id, graph)
        self.assertIs(loaded.graph, graph)
        self.assertEqual(loaded, initial_graph_snapshot(graph))
        self.assertEqual(derive_graph_state(loaded), "ready")

    def test_runtime_store_can_share_the_existing_qiqi_delegate_sqlite_database(self) -> None:
        session_store = SessionStore(self.db_path)
        self.assertTrue(session_store.register_session("session-1", "contracts", "claude"))

        run_id, graph = self.create_run()

        self.assertIsNotNone(session_store.get_session("session-1"))
        self.assertEqual(self.store.load_snapshot(run_id, graph).graph, graph)

    def test_attempt_lifecycle_persists_wave_session_turn_and_normalized_result(self) -> None:
        run_id, graph = self.create_run()

        attempt_id = self.store.start_attempt(run_id, "contracts", "wave-1")
        self.assertEqual(self.store.get_run(run_id)["current_wave_id"], "wave-1")
        self.assertEqual(self.store.get_node(run_id, "contracts")["runtime_state"], "running")
        self.assertEqual(derive_graph_state(self.store.load_snapshot(run_id, graph)), "running")

        attempt = self.store.get_attempt(attempt_id)
        self.assertEqual(attempt["attempt_number"], 1)
        self.assertFalse(attempt["resume_session"])
        self.assertIsNone(attempt["session_id"])
        self.assertIsNone(attempt["result"])

        with self.assertRaisesRegex(RuntimeError, "while node attempts are running"):
            self.store.close_wave(run_id, "wave-1")

        self.store.bind_attempt_session(attempt_id, "session-1")
        self.assertEqual(self.store.get_attempt(attempt_id)["session_id"], "session-1")
        self.assertEqual(self.store.get_node(run_id, "contracts")["session_id"], "session-1")

        result = {
            "state": "settled",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "agent_response": "native final response",
        }
        self.store.finish_attempt(
            attempt_id,
            runtime_state="settled",
            session_id="session-1",
            turn_id="turn-1",
            result=result,
        )

        attempt = self.store.get_attempt(attempt_id)
        self.assertEqual(attempt["runtime_state"], "settled")
        self.assertEqual(attempt["session_id"], "session-1")
        self.assertEqual(attempt["turn_id"], "turn-1")
        self.assertEqual(attempt["result"], result)

        node = self.store.get_node(run_id, "contracts")
        self.assertEqual(node["current_attempt_id"], attempt_id)
        self.assertEqual(node["runtime_state"], "settled")
        self.assertEqual(node["session_id"], "session-1")
        self.assertEqual(node["turn_id"], "turn-1")
        self.assertEqual(
            derive_graph_state(self.store.load_snapshot(run_id, graph)),
            "awaiting_review",
        )

        self.store.close_wave(run_id, "wave-1")
        self.assertIsNone(self.store.get_run(run_id)["current_wave_id"])

    def test_semantic_acceptance_is_persisted_without_erasing_execution_linkage(self) -> None:
        run_id, graph = self.create_run()
        attempt_id = self.finish_contracts_attempt(run_id)
        self.store.close_wave(run_id, "wave-1")

        reviewable = self.store.load_snapshot(run_id, graph)
        accepted = apply_decisions(
            reviewable,
            (NodeDecision(node_id="contracts", action="accept"),),
        )
        self.store.save_snapshot(run_id, accepted)

        loaded = self.store.load_snapshot(run_id, graph)
        contracts = next(state for state in loaded.node_states if state.node_id == "contracts")
        self.assertEqual(contracts, NodeState("contracts", "satisfied", "idle"))
        self.assertEqual(
            tuple(node.node_id for node in runnable_nodes(loaded)),
            ("backend",),
        )

        node = self.store.get_node(run_id, "contracts")
        self.assertEqual(node["current_attempt_id"], attempt_id)
        self.assertEqual(node["session_id"], "session-1")
        self.assertEqual(node["turn_id"], "turn-1")

    def test_retry_creates_a_new_attempt_snapshot_with_resume_metadata(self) -> None:
        run_id, graph = self.create_run()
        first_attempt = self.finish_contracts_attempt(
            run_id,
            runtime_state="failed",
        )
        self.store.close_wave(run_id, "wave-1")

        reviewable = self.store.load_snapshot(run_id, graph)
        retried = apply_decisions(
            reviewable,
            (NodeDecision(node_id="contracts", action="retry"),),
        )
        self.store.save_snapshot(run_id, retried)

        second_attempt = self.store.start_attempt(
            run_id,
            "contracts",
            "wave-2",
            resume_session=True,
            session_id="session-1",
        )

        self.assertNotEqual(first_attempt, second_attempt)
        attempts = self.store.list_attempts(run_id, "contracts")
        self.assertEqual([item["attempt_number"] for item in attempts], [1, 2])
        self.assertFalse(attempts[0]["resume_session"])
        self.assertTrue(attempts[1]["resume_session"])
        self.assertEqual(attempts[1]["session_id"], "session-1")
        self.assertEqual(attempts[0]["result"]["state"], "failed")
        self.assertIsNone(attempts[1]["result"])

    def test_resume_requires_explicit_session_and_session_identity_cannot_change(self) -> None:
        run_id, _ = self.create_run()

        with self.assertRaisesRegex(ValueError, "resume_session requires"):
            self.store.start_attempt(
                run_id,
                "contracts",
                "wave-1",
                resume_session=True,
            )

        attempt_id = self.store.start_attempt(run_id, "contracts", "wave-1")
        self.store.bind_attempt_session(attempt_id, "session-1")
        with self.assertRaisesRegex(RuntimeError, "session identity cannot change"):
            self.store.bind_attempt_session(attempt_id, "session-2")
        with self.assertRaisesRegex(RuntimeError, "session identity cannot change"):
            self.store.finish_attempt(
                attempt_id,
                runtime_state="settled",
                session_id="session-2",
                result={"state": "settled"},
            )

    def test_store_rejects_state_that_would_desynchronize_an_active_attempt(self) -> None:
        run_id, graph = self.create_run()
        self.store.start_attempt(run_id, "contracts", "wave-1")

        inconsistent = GraphSnapshot(
            graph=graph,
            node_states=(
                NodeState("contracts", "pending", "idle"),
                NodeState("backend", "pending", "idle"),
            ),
        )
        with self.assertRaisesRegex(RuntimeError, "has a running attempt"):
            self.store.save_snapshot(run_id, inconsistent)

    def test_load_snapshot_requires_the_same_authored_node_set(self) -> None:
        run_id, _ = self.create_run()
        other_graph = TaskGraph(
            nodes=(
                GraphNode(
                    node_id="contracts",
                    repository="contracts",
                    task_packet=self.packet("Update contract."),
                ),
                GraphNode(
                    node_id="frontend",
                    repository="frontend",
                    task_packet=self.packet("Update frontend."),
                    depends_on=("contracts",),
                ),
            )
        )

        with self.assertRaisesRegex(RuntimeError, "does not match TaskGraph"):
            self.store.load_snapshot(run_id, other_graph)

    def test_attempt_result_must_be_a_json_object_and_finish_is_single_use(self) -> None:
        run_id, _ = self.create_run()
        attempt_id = self.store.start_attempt(run_id, "contracts", "wave-1")

        with self.assertRaisesRegex(ValueError, "must be an object"):
            self.store.finish_attempt(
                attempt_id,
                runtime_state="settled",
                result=["not", "an", "object"],  # type: ignore[arg-type]
            )

        self.store.finish_attempt(
            attempt_id,
            runtime_state="blocked",
            result={"state": "blocked", "session_id": "session-1"},
            session_id="session-1",
        )
        with self.assertRaisesRegex(RuntimeError, "already terminal"):
            self.store.finish_attempt(
                attempt_id,
                runtime_state="blocked",
                result={"state": "blocked"},
            )


if __name__ == "__main__":
    unittest.main()
