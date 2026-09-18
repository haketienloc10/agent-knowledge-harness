from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import build_task_packet
from task_graph import GraphNode, TaskGraph
from task_graph_runtime import GraphRuntime, decisions_from_payload
from task_graph_store import GraphRuntimeStore


class TaskGraphReconciliationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
        self.store = GraphRuntimeStore(self.db_path)
        self.runtime = GraphRuntime(self.store)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def packet(self, objective: str, *, revision: int | None = None):
        context = None
        if revision is not None:
            context = {
                "trusted_facts": [
                    {
                        "fact": f"work_item_revision={revision}",
                        "source": "Work Item",
                    }
                ]
            }
        return build_task_packet(
            objective=objective,
            scope=["repository-local implementation"],
            acceptance_criteria=["focused verification passes"],
            context=context,
        )

    def initial_graph(self) -> TaskGraph:
        return TaskGraph(
            nodes=(
                GraphNode(
                    "contracts",
                    "contracts",
                    self.packet("Update shared contract.", revision=1),
                    route="codex-balanced",
                ),
                GraphNode(
                    "backend",
                    "backend",
                    self.packet("Update backend consumer."),
                    depends_on=("contracts",),
                    route="codex-balanced",
                ),
                GraphNode(
                    "docs",
                    "docs",
                    self.packet("Update documentation."),
                    route="codex-balanced",
                ),
                GraphNode(
                    "obsolete",
                    "obsolete",
                    self.packet("Update obsolete integration."),
                    route="codex-balanced",
                ),
            )
        )

    async def executor(self, node: GraphNode) -> dict:
        return {
            "session_id": f"session-{node.node_id}",
            "turn_id": f"turn-{node.node_id}",
            "state": "settled",
            "agent_response": f"completed {node.node_id}",
        }

    async def complete_initial_graph(self) -> tuple[str, dict]:
        started = self.runtime.start_graph(
            self.initial_graph(),
            repository_names={"contracts", "backend", "docs", "obsolete"},
        )
        run_id = started["graph_run_id"]

        first_wave = await self.runtime.delegate_next(run_id, executor=self.executor)
        self.assertEqual(
            [item["node_id"] for item in first_wave["results"]],
            ["contracts", "docs", "obsolete"],
        )
        reviewed = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [
                    {"node_id": "contracts", "action": "accept"},
                    {"node_id": "docs", "action": "accept"},
                    {"node_id": "obsolete", "action": "accept"},
                ]
            ),
            expected_revision=first_wave["revision"],
        )
        self.assertEqual(reviewed["runnable_nodes"], ["backend"])

        second_wave = await self.runtime.delegate_next(run_id, executor=self.executor)
        completed = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload([{"node_id": "backend", "action": "accept"}]),
            expected_revision=second_wave["revision"],
        )
        self.assertEqual(completed["graph_state"], "complete")
        return run_id, completed

    async def test_reconcile_preserves_unaffected_evidence_and_resets_material_dependents(self) -> None:
        run_id, completed = await self.complete_initial_graph()
        docs_before = self.store.get_node(run_id, "docs")
        contracts_attempts_before = self.store.list_attempts(run_id, "contracts")
        backend_attempts_before = self.store.list_attempts(run_id, "backend")
        obsolete_attempts_before = self.store.list_attempts(run_id, "obsolete")

        next_graph = TaskGraph(
            nodes=(
                GraphNode(
                    "contracts",
                    "contracts",
                    self.packet("Update shared contract.", revision=2),
                    route="codex-balanced",
                ),
                # Authored node is byte-for-byte equivalent to the prior backend node.
                # It must still reset because its accepted result depended on contracts.
                GraphNode(
                    "backend",
                    "backend",
                    self.packet("Update backend consumer."),
                    depends_on=("contracts",),
                    route="codex-balanced",
                ),
                GraphNode(
                    "docs",
                    "docs",
                    self.packet("Update documentation."),
                    route="codex-balanced",
                ),
                GraphNode(
                    "verification",
                    "verification",
                    self.packet("Verify the revised contract end to end."),
                    depends_on=("contracts",),
                    route="codex-balanced",
                ),
            )
        )

        reconciled = self.runtime.reconcile_graph(
            run_id,
            next_graph,
            repository_names={"contracts", "backend", "docs", "verification"},
            expected_revision=completed["revision"],
        )

        self.assertEqual(reconciled["graph_state"], "ready")
        self.assertEqual(reconciled["runnable_nodes"], ["contracts"])
        self.assertEqual(
            reconciled["reconciliation"],
            {
                "preserved_nodes": ["docs"],
                "added_nodes": ["verification"],
                "removed_nodes": ["obsolete"],
                "changed_nodes": ["contracts"],
                "dependency_invalidated_nodes": ["backend"],
                "reset_nodes": ["contracts", "backend"],
            },
        )

        states = {item["node_id"]: item for item in reconciled["nodes"]}
        self.assertEqual(states["contracts"]["semantic_state"], "pending")
        self.assertEqual(states["contracts"]["runtime_state"], "idle")
        self.assertIsNone(states["contracts"]["current_attempt_id"])
        self.assertIsNone(states["contracts"]["session_id"])
        self.assertIsNone(states["contracts"]["turn_id"])
        self.assertEqual(states["backend"]["semantic_state"], "pending")
        self.assertIsNone(states["backend"]["current_attempt_id"])
        self.assertEqual(states["docs"]["semantic_state"], "satisfied")
        self.assertEqual(
            states["docs"]["current_attempt_id"],
            docs_before["current_attempt_id"],
        )
        self.assertEqual(states["docs"]["session_id"], docs_before["session_id"])

        self.assertEqual(
            self.store.list_attempts(run_id, "contracts"),
            contracts_attempts_before,
        )
        self.assertEqual(
            self.store.list_attempts(run_id, "backend"),
            backend_attempts_before,
        )
        retired = self.store.get_node(run_id, "obsolete")
        self.assertEqual(retired["active"], 0)
        self.assertEqual(retired["semantic_state"], "cancelled")
        self.assertEqual(self.store.list_attempts(run_id, "obsolete"), obsolete_attempts_before)
        with self.assertRaisesRegex(RuntimeError, "unknown active graph node"):
            self.store.start_attempt(run_id, "obsolete", "retired-wave")

    async def test_replan_can_be_released_by_explicit_reconciled_graph(self) -> None:
        graph = TaskGraph(
            nodes=(
                GraphNode(
                    "contracts",
                    "contracts",
                    self.packet("Update contract.", revision=1),
                    route="codex-balanced",
                ),
            )
        )
        started = self.runtime.start_graph(graph, repository_names={"contracts"})
        run_id = started["graph_run_id"]
        delegated = await self.runtime.delegate_next(run_id, executor=self.executor)
        blocked = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload([{"node_id": "contracts", "action": "replan"}]),
            expected_revision=delegated["revision"],
        )
        self.assertEqual(blocked["graph_state"], "blocked")
        self.assertEqual(blocked["replan_required_nodes"], ["contracts"])

        replacement = TaskGraph(
            nodes=(
                GraphNode(
                    "contracts",
                    "contracts",
                    self.packet("Update revised contract.", revision=2),
                    route="codex-balanced",
                ),
            )
        )
        reconciled = self.runtime.reconcile_graph(
            run_id,
            replacement,
            repository_names={"contracts"},
            expected_revision=blocked["revision"],
        )

        self.assertEqual(reconciled["graph_state"], "ready")
        self.assertEqual(reconciled["runnable_nodes"], ["contracts"])
        self.assertEqual(reconciled["reconciliation"]["changed_nodes"], ["contracts"])
        self.assertEqual(reconciled["nodes"][0]["semantic_state"], "pending")
        self.assertIsNone(reconciled["nodes"][0]["current_attempt_id"])
        self.assertEqual(len(self.store.list_attempts(run_id, "contracts")), 1)

    def test_reconcile_rejects_active_wave_even_with_current_revision(self) -> None:
        graph = TaskGraph(
            nodes=(
                GraphNode(
                    "contracts",
                    "contracts",
                    self.packet("Update contract.", revision=1),
                    route="codex-balanced",
                ),
            )
        )
        started = self.runtime.start_graph(graph, repository_names={"contracts"})
        run_id = started["graph_run_id"]
        self.store.start_attempt(run_id, "contracts", "manual-active-wave")
        running = self.runtime.get_graph(run_id)

        replacement = TaskGraph(
            nodes=(
                GraphNode(
                    "contracts",
                    "contracts",
                    self.packet("Update revised contract.", revision=2),
                    route="codex-balanced",
                ),
            )
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "graph reconciliation cannot run while a wave is active",
        ):
            self.runtime.reconcile_graph(
                run_id,
                replacement,
                repository_names={"contracts"},
                expected_revision=running["revision"],
            )


if __name__ == "__main__":
    unittest.main()
