from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import build_task_packet
from task_graph import GraphNode, TaskGraph
from task_graph_runtime import (
    GraphRuntime,
    decisions_from_payload,
    task_graph_from_payload,
)
from task_graph_store import GraphRuntimeStore


class TaskGraphRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
        self.store = GraphRuntimeStore(self.db_path)
        self.runtime = GraphRuntime(self.store)

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

    def start(self) -> dict:
        return self.runtime.start_graph(
            self.graph(),
            repository_names={"contracts", "backend"},
        )

    def test_start_graph_returns_ready_outer_loop_snapshot(self) -> None:
        started = self.start()

        self.assertTrue(started["graph_run_id"])
        self.assertEqual(started["graph_state"], "ready")
        self.assertEqual(started["revision"], 0)
        self.assertEqual(started["runnable_nodes"], ["contracts"])
        self.assertEqual(started["authored_node_count"], 2)
        self.assertEqual(
            [item["semantic_state"] for item in started["nodes"]],
            ["pending", "pending"],
        )

    def test_delegate_next_is_deterministic_dispatch_only_in_phase_5(self) -> None:
        started = self.start()
        run_id = started["graph_run_id"]

        dispatch = self.runtime.delegate_next(run_id)
        after = self.runtime.get_graph(run_id)

        self.assertEqual(dispatch["graph_state"], "ready")
        self.assertEqual(dispatch["revision"], started["revision"])
        self.assertEqual(dispatch["dispatch"]["node"]["node_id"], "contracts")
        self.assertEqual(dispatch["dispatch"]["execution_state"], "planned")
        self.assertFalse(dispatch["dispatch"]["execution_side_effect"])
        self.assertEqual(after["revision"], started["revision"])
        self.assertEqual(after["graph_state"], "ready")
        self.assertIsNone(after["nodes"][0]["current_attempt_id"])

    def test_submit_decisions_returns_control_to_ready_state(self) -> None:
        started = self.start()
        run_id = started["graph_run_id"]

        attempt_id = self.store.start_attempt(run_id, "contracts", "wave-1")
        self.store.finish_attempt(
            attempt_id,
            runtime_state="settled",
            result={
                "state": "settled",
                "agent_response": "native final response",
            },
        )
        self.store.close_wave(run_id, "wave-1")

        reviewable = self.runtime.get_graph(run_id)
        self.assertEqual(reviewable["graph_state"], "awaiting_review")
        self.assertEqual(reviewable["nodes"][0]["result"]["state"], "settled")

        updated = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [{"node_id": "contracts", "action": "accept"}]
            ),
            expected_revision=reviewable["revision"],
        )

        self.assertEqual(updated["graph_state"], "ready")
        self.assertEqual(updated["runnable_nodes"], ["backend"])
        self.assertEqual(updated["nodes"][0]["semantic_state"], "satisfied")
        self.assertGreater(updated["revision"], reviewable["revision"])

    def test_submit_decisions_rejects_stale_revision(self) -> None:
        started = self.start()
        run_id = started["graph_run_id"]
        attempt_id = self.store.start_attempt(run_id, "contracts", "wave-1")
        self.store.finish_attempt(
            attempt_id,
            runtime_state="failed",
            result={"state": "failed", "agent_response": "failed response"},
        )
        current = self.runtime.get_graph(run_id)

        with self.assertRaisesRegex(RuntimeError, "stale graph snapshot revision"):
            self.runtime.submit_decisions(
                run_id,
                decisions_from_payload(
                    [{"node_id": "contracts", "action": "retry"}]
                ),
                expected_revision=current["revision"] - 1,
            )

    def test_delegate_next_requires_ready_state(self) -> None:
        started = self.start()
        run_id = started["graph_run_id"]
        attempt_id = self.store.start_attempt(run_id, "contracts", "wave-1")

        with self.assertRaisesRegex(RuntimeError, "not ready for delegation"):
            self.runtime.delegate_next(run_id)

        self.store.finish_attempt(
            attempt_id,
            runtime_state="settled",
            result={"state": "settled", "agent_response": "done"},
        )
        with self.assertRaisesRegex(RuntimeError, "not ready for delegation"):
            self.runtime.delegate_next(run_id)

    def test_persisted_run_without_process_graph_fails_closed(self) -> None:
        started = self.start()
        restarted_runtime = GraphRuntime(GraphRuntimeStore(self.db_path))

        with self.assertRaisesRegex(RuntimeError, "restart recovery is not implemented"):
            restarted_runtime.get_graph(started["graph_run_id"])

    def test_graph_transport_reuses_existing_taskpacket_builder(self) -> None:
        graph = task_graph_from_payload(
            {
                "nodes": [
                    {
                        "node_id": "backend",
                        "repository": "backend",
                        "depends_on": [],
                        "task_packet": {
                            "objective": "Update backend.",
                            "scope": ["backend"],
                            "acceptance_criteria": ["tests pass"],
                        },
                    }
                ]
            }
        )
        self.assertEqual(graph.nodes[0].task_packet.scope, ("backend",))

        with self.assertRaisesRegex(ValueError, "scope must contain at least one item"):
            task_graph_from_payload(
                {
                    "nodes": [
                        {
                            "node_id": "backend",
                            "repository": "backend",
                            "task_packet": {
                                "objective": "Update backend.",
                                "scope": [],
                                "acceptance_criteria": ["tests pass"],
                            },
                        }
                    ]
                }
            )

    def test_graph_transport_rejects_unsupported_fields_without_new_semantic_schema(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported fields: objective"):
            task_graph_from_payload(
                {
                    "nodes": [],
                    "objective": "duplicate graph-level task semantics",
                }
            )

        with self.assertRaisesRegex(ValueError, "invalid TaskPacket fields"):
            task_graph_from_payload(
                {
                    "nodes": [
                        {
                            "node_id": "backend",
                            "repository": "backend",
                            "task_packet": {
                                "objective": "Update backend.",
                                "scope": ["backend"],
                                "acceptance_criteria": ["tests pass"],
                                "duplicate_semantics": "forbidden",
                            },
                        }
                    ]
                }
            )

    def test_decision_transport_is_strict_and_replan_remains_unsupported(self) -> None:
        decisions = decisions_from_payload(
            [{"node_id": "backend", "action": "accept"}]
        )
        self.assertEqual(decisions[0].node_id, "backend")

        with self.assertRaisesRegex(ValueError, "unsupported fields: reason"):
            decisions_from_payload(
                [{"node_id": "backend", "action": "accept", "reason": "extra"}]
            )

        started = self.start()
        run_id = started["graph_run_id"]
        attempt_id = self.store.start_attempt(run_id, "contracts", "wave-1")
        self.store.finish_attempt(
            attempt_id,
            runtime_state="settled",
            result={"state": "settled", "agent_response": "done"},
        )
        reviewable = self.runtime.get_graph(run_id)
        with self.assertRaisesRegex(ValueError, "unsupported decision action 'replan'"):
            self.runtime.submit_decisions(
                run_id,
                decisions_from_payload(
                    [{"node_id": "contracts", "action": "replan"}]
                ),
                expected_revision=reviewable["revision"],
            )


if __name__ == "__main__":
    unittest.main()
