from __future__ import annotations

import asyncio
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


class TaskGraphRuntimeTests(unittest.IsolatedAsyncioTestCase):
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
                    route="codex-balanced",
                ),
                GraphNode(
                    node_id="backend",
                    repository="backend",
                    task_packet=self.packet("Update backend consumer."),
                    depends_on=("contracts",),
                    route="codex-balanced",
                ),
            )
        )

    def start(self) -> dict:
        return self.runtime.start_graph(
            self.graph(),
            repository_names={"contracts", "backend"},
        )

    async def settled_executor(self, node: GraphNode) -> dict:
        return {
            "session_id": f"session-{node.node_id}",
            "turn_id": f"turn-{node.node_id}",
            "state": "settled",
            "agent_response": f"completed {node.node_id}",
        }

    def test_start_graph_returns_ready_outer_loop_snapshot(self) -> None:
        started = self.start()

        self.assertTrue(started["graph_run_id"])
        self.assertEqual(started["graph_state"], "ready")
        self.assertEqual(started["revision"], 0)
        self.assertEqual(started["runnable_nodes"], ["contracts"])
        self.assertEqual(started["review_required"], [])
        self.assertEqual(started["authored_node_count"], 2)
        self.assertEqual(
            [item["semantic_state"] for item in started["nodes"]],
            ["pending", "pending"],
        )

    async def test_delegate_next_executes_one_node_and_exposes_review_envelope(self) -> None:
        started = self.start()
        run_id = started["graph_run_id"]
        calls: list[str] = []

        async def executor(node: GraphNode) -> dict:
            calls.append(node.node_id)
            return await self.settled_executor(node)

        result = await self.runtime.delegate_next(run_id, executor=executor)
        persisted = self.store.get_node(run_id, "contracts")
        attempts = self.store.list_attempts(run_id, "contracts")

        self.assertEqual(calls, ["contracts"])
        self.assertEqual(result["graph_state"], "awaiting_review")
        self.assertIsNone(result["current_wave_id"])
        self.assertTrue(result["wave_id"])
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["node_id"], "contracts")
        self.assertEqual(result["results"][0]["runtime_state"], "settled")
        self.assertEqual(result["results"][0]["session_id"], "session-contracts")
        self.assertEqual(result["results"][0]["turn_id"], "turn-contracts")
        self.assertEqual(
            result["review_required"],
            [
                {
                    "node_id": "contracts",
                    "repository": "contracts",
                    "runtime_state": "settled",
                    "acceptance_criteria": ["focused verification passes"],
                    "result": {
                        "session_id": "session-contracts",
                        "turn_id": "turn-contracts",
                        "state": "settled",
                        "agent_response": "completed contracts",
                    },
                }
            ],
        )
        self.assertEqual(persisted["runtime_state"], "settled")
        self.assertEqual(persisted["session_id"], "session-contracts")
        self.assertEqual(persisted["turn_id"], "turn-contracts")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["wave_id"], result["wave_id"])
        self.assertFalse(attempts[0]["resume_session"])
        self.assertEqual(attempts[0]["result"]["agent_response"], "completed contracts")

    async def test_delegate_next_executes_all_conflict_free_runnable_nodes_per_wave(self) -> None:
        graph = TaskGraph(
            nodes=(
                GraphNode(
                    "backend",
                    "backend",
                    self.packet("Backend work."),
                    route="codex-balanced",
                ),
                GraphNode(
                    "frontend",
                    "frontend",
                    self.packet("Frontend work."),
                    route="codex-balanced",
                ),
            )
        )
        started = self.runtime.start_graph(
            graph,
            repository_names={"backend", "frontend"},
        )
        run_id = started["graph_run_id"]
        calls: list[str] = []

        async def executor(node: GraphNode) -> dict:
            calls.append(node.node_id)
            return await self.settled_executor(node)

        result = await self.runtime.delegate_next(run_id, executor=executor)

        self.assertEqual(calls, ["backend", "frontend"])
        self.assertEqual(result["graph_state"], "awaiting_review")
        self.assertEqual(
            [item["node_id"] for item in result["review_required"]],
            ["backend", "frontend"],
        )
        self.assertEqual(
            [item["node_id"] for item in result["results"]],
            ["backend", "frontend"],
        )
        backend_attempts = self.store.list_attempts(run_id, "backend")
        frontend_attempts = self.store.list_attempts(run_id, "frontend")
        self.assertEqual(len(backend_attempts), 1)
        self.assertEqual(len(frontend_attempts), 1)
        self.assertEqual(backend_attempts[0]["wave_id"], result["wave_id"])
        self.assertEqual(frontend_attempts[0]["wave_id"], result["wave_id"])

    async def test_executor_exception_terminalizes_attempt_and_closes_wave(self) -> None:
        started = self.start()
        run_id = started["graph_run_id"]

        async def executor(_: GraphNode) -> dict:
            raise RuntimeError("executor exploded")

        with self.assertRaisesRegex(RuntimeError, "executor exploded"):
            await self.runtime.delegate_next(run_id, executor=executor)

        current = self.runtime.get_graph(run_id)
        attempts = self.store.list_attempts(run_id, "contracts")
        self.assertEqual(current["graph_state"], "awaiting_review")
        self.assertEqual([item["node_id"] for item in current["review_required"]], ["contracts"])
        self.assertIsNone(current["current_wave_id"])
        self.assertEqual(current["nodes"][0]["runtime_state"], "failed")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["runtime_state"], "failed")
        self.assertEqual(attempts[0]["result"]["failure_type"], "executor_exception")
        self.assertNotIn("executor exploded", str(attempts[0]["result"]))

    async def test_executor_cancellation_terminalizes_attempt_and_closes_wave(self) -> None:
        started = self.start()
        run_id = started["graph_run_id"]

        async def executor(_: GraphNode) -> dict:
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await self.runtime.delegate_next(run_id, executor=executor)

        current = self.runtime.get_graph(run_id)
        attempts = self.store.list_attempts(run_id, "contracts")
        self.assertEqual(current["graph_state"], "awaiting_review")
        self.assertIsNone(current["current_wave_id"])
        self.assertEqual(current["nodes"][0]["runtime_state"], "failed")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["runtime_state"], "failed")
        self.assertEqual(attempts[0]["result"]["failure_type"], "execution_cancelled")

    async def test_delegate_next_requires_route_before_starting_attempt(self) -> None:
        graph = TaskGraph(
            nodes=(GraphNode("backend", "backend", self.packet("Backend work.")),)
        )
        started = self.runtime.start_graph(graph, repository_names={"backend"})
        run_id = started["graph_run_id"]

        with self.assertRaisesRegex(RuntimeError, "has no route"):
            await self.runtime.delegate_next(run_id, executor=self.settled_executor)

        self.assertEqual(self.store.list_attempts(run_id, "backend"), [])
        self.assertEqual(self.runtime.get_graph(run_id)["graph_state"], "ready")

    async def test_accept_decision_returns_control_to_ready_state(self) -> None:
        started = self.start()
        run_id = started["graph_run_id"]
        reviewable = await self.runtime.delegate_next(
            run_id,
            executor=self.settled_executor,
        )

        updated = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [{"node_id": "contracts", "action": "accept"}]
            ),
            expected_revision=reviewable["revision"],
        )

        self.assertEqual(updated["graph_state"], "ready")
        self.assertEqual(updated["runnable_nodes"], ["backend"])
        self.assertEqual(updated["review_required"], [])
        self.assertEqual(updated["nodes"][0]["semantic_state"], "satisfied")
        self.assertEqual(
            updated["decision_outcomes"],
            [
                {
                    "node_id": "contracts",
                    "action": "accept",
                    "semantic_state": "satisfied",
                }
            ],
        )
        self.assertEqual(updated["replan_required_nodes"], [])
        self.assertGreater(updated["revision"], reviewable["revision"])

    async def test_retry_block_and_replan_have_distinct_outer_loop_outcomes(self) -> None:
        expected = {
            "retry": ("ready", "pending", []),
            "block": ("blocked", "blocked", []),
            "replan": ("blocked", "blocked", ["contracts"]),
        }
        for action, (graph_state, semantic_state, replan_nodes) in expected.items():
            with self.subTest(action=action):
                runtime = GraphRuntime(GraphRuntimeStore(Path(self.temp.name) / f"{action}.sqlite3"))
                started = runtime.start_graph(
                    self.graph(),
                    repository_names={"contracts", "backend"},
                )
                run_id = started["graph_run_id"]
                reviewable = await runtime.delegate_next(
                    run_id,
                    executor=self.settled_executor,
                )

                updated = runtime.submit_decisions(
                    run_id,
                    decisions_from_payload(
                        [{"node_id": "contracts", "action": action}]
                    ),
                    expected_revision=reviewable["revision"],
                )

                self.assertEqual(updated["graph_state"], graph_state)
                self.assertEqual(updated["nodes"][0]["semantic_state"], semantic_state)
                self.assertEqual(updated["replan_required_nodes"], replan_nodes)
                self.assertEqual(updated["decision_outcomes"][0]["action"], action)
                self.assertEqual(updated["review_required"], [])

    async def test_submit_decisions_rejects_stale_revision(self) -> None:
        started = self.start()
        run_id = started["graph_run_id"]

        async def failed_executor(node: GraphNode) -> dict:
            return {
                "session_id": f"session-{node.node_id}",
                "turn_id": f"turn-{node.node_id}",
                "state": "failed",
                "agent_response": "failed response",
            }

        current = await self.runtime.delegate_next(run_id, executor=failed_executor)

        with self.assertRaisesRegex(RuntimeError, "stale graph snapshot revision"):
            self.runtime.submit_decisions(
                run_id,
                decisions_from_payload(
                    [{"node_id": "contracts", "action": "retry"}]
                ),
                expected_revision=current["revision"] - 1,
            )

    async def test_delegate_next_requires_ready_state(self) -> None:
        started = self.start()
        run_id = started["graph_run_id"]
        await self.runtime.delegate_next(run_id, executor=self.settled_executor)

        with self.assertRaisesRegex(RuntimeError, "not ready for delegation"):
            await self.runtime.delegate_next(run_id, executor=self.settled_executor)

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

    async def test_decision_transport_is_strict_and_replan_is_supported(self) -> None:
        decisions = decisions_from_payload(
            [{"node_id": "backend", "action": "replan"}]
        )
        self.assertEqual(decisions[0].node_id, "backend")
        self.assertEqual(decisions[0].action, "replan")

        with self.assertRaisesRegex(ValueError, "unsupported fields: reason"):
            decisions_from_payload(
                [{"node_id": "backend", "action": "accept", "reason": "extra"}]
            )

        started = self.start()
        run_id = started["graph_run_id"]
        reviewable = await self.runtime.delegate_next(
            run_id,
            executor=self.settled_executor,
        )
        with self.assertRaisesRegex(ValueError, "unsupported decision action 'skip'"):
            self.runtime.submit_decisions(
                run_id,
                decisions_from_payload(
                    [{"node_id": "contracts", "action": "skip"}]
                ),
                expected_revision=reviewable["revision"],
            )


if __name__ == "__main__":
    unittest.main()
