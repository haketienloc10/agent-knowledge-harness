from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import build_task_packet  # noqa: E402
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


class TaskGraphSchedulerTests(unittest.TestCase):
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
                GraphNode(
                    node_id="frontend",
                    repository="frontend",
                    task_packet=self.packet("Update frontend consumer."),
                    depends_on=("contracts",),
                ),
                GraphNode(
                    node_id="integration",
                    repository="backend",
                    task_packet=self.packet("Verify integrated behavior."),
                    depends_on=("backend", "frontend"),
                ),
            )
        )

    def snapshot_with(self, **overrides: tuple[str, str]) -> GraphSnapshot:
        graph = self.graph()
        states = []
        for node in graph.nodes:
            semantic_state, runtime_state = overrides.get(
                node.node_id,
                ("pending", "idle"),
            )
            states.append(
                NodeState(
                    node_id=node.node_id,
                    semantic_state=semantic_state,
                    runtime_state=runtime_state,
                )
            )
        return GraphSnapshot(graph=graph, node_states=tuple(states))

    def test_initial_snapshot_is_pending_idle_without_mutating_graph(self) -> None:
        graph = self.graph()
        snapshot = initial_graph_snapshot(graph)

        self.assertIs(snapshot.graph, graph)
        self.assertEqual(
            snapshot.node_states,
            tuple(NodeState(node.node_id) for node in graph.nodes),
        )
        self.assertEqual(derive_graph_state(snapshot), "ready")

    def test_runnable_nodes_returns_roots_in_authored_order(self) -> None:
        graph = TaskGraph(
            nodes=(
                GraphNode("first", "backend", self.packet("First root.")),
                GraphNode("second", "frontend", self.packet("Second root.")),
            )
        )
        snapshot = initial_graph_snapshot(graph)

        self.assertEqual(
            tuple(node.node_id for node in runnable_nodes(snapshot)),
            ("first", "second"),
        )

    def test_dependencies_unlock_only_after_semantic_satisfaction(self) -> None:
        snapshot = self.snapshot_with(contracts=("satisfied", "idle"))

        self.assertEqual(
            tuple(node.node_id for node in runnable_nodes(snapshot)),
            ("backend", "frontend"),
        )

    def test_runtime_non_idle_node_is_not_automatically_runnable(self) -> None:
        snapshot = self.snapshot_with(contracts=("pending", "failed"))

        self.assertEqual(runnable_nodes(snapshot), ())
        self.assertEqual(derive_graph_state(snapshot), "awaiting_review")

    def test_running_state_takes_precedence_over_other_ready_nodes(self) -> None:
        snapshot = self.snapshot_with(
            contracts=("satisfied", "idle"),
            backend=("pending", "running"),
            frontend=("pending", "idle"),
        )

        self.assertEqual(derive_graph_state(snapshot), "running")

    def test_awaiting_review_takes_precedence_over_ready_nodes(self) -> None:
        snapshot = self.snapshot_with(
            contracts=("satisfied", "idle"),
            backend=("pending", "settled"),
            frontend=("pending", "idle"),
        )

        self.assertEqual(derive_graph_state(snapshot), "awaiting_review")

    def test_semantic_block_moves_graph_to_blocked(self) -> None:
        snapshot = self.snapshot_with(contracts=("blocked", "idle"))

        self.assertEqual(derive_graph_state(snapshot), "blocked")
        self.assertEqual(runnable_nodes(snapshot), ())

    def test_cancelled_prerequisite_does_not_satisfy_dependency(self) -> None:
        snapshot = self.snapshot_with(contracts=("cancelled", "idle"))

        self.assertEqual(runnable_nodes(snapshot), ())
        self.assertEqual(derive_graph_state(snapshot), "blocked")

    def test_complete_when_all_nodes_are_semantically_terminal(self) -> None:
        snapshot = self.snapshot_with(
            contracts=("satisfied", "idle"),
            backend=("satisfied", "idle"),
            frontend=("cancelled", "idle"),
            integration=("cancelled", "idle"),
        )

        self.assertEqual(derive_graph_state(snapshot), "complete")

    def test_accept_decision_satisfies_only_reviewed_node(self) -> None:
        snapshot = self.snapshot_with(contracts=("pending", "awaiting_review"))

        updated = apply_decisions(
            snapshot,
            (NodeDecision(node_id="contracts", action="accept"),),
        )

        self.assertEqual(snapshot.node_states[0].semantic_state, "pending")
        self.assertEqual(snapshot.node_states[0].runtime_state, "awaiting_review")
        self.assertEqual(updated.node_states[0].semantic_state, "satisfied")
        self.assertEqual(updated.node_states[0].runtime_state, "idle")
        self.assertEqual(
            tuple(node.node_id for node in runnable_nodes(updated)),
            ("backend", "frontend"),
        )

    def test_retry_decision_resets_only_target_node_to_runnable(self) -> None:
        snapshot = self.snapshot_with(
            contracts=("satisfied", "idle"),
            backend=("pending", "failed"),
            frontend=("pending", "awaiting_review"),
        )

        updated = apply_decisions(
            snapshot,
            (NodeDecision(node_id="backend", action="retry"),),
        )

        self.assertEqual(
            next(state for state in updated.node_states if state.node_id == "backend"),
            NodeState("backend", "pending", "idle"),
        )
        self.assertEqual(
            next(state for state in updated.node_states if state.node_id == "frontend"),
            NodeState("frontend", "pending", "awaiting_review"),
        )
        self.assertEqual(derive_graph_state(updated), "awaiting_review")

    def test_block_decision_sets_semantic_block_without_runtime_conflation(self) -> None:
        snapshot = self.snapshot_with(contracts=("pending", "blocked"))

        updated = apply_decisions(
            snapshot,
            (NodeDecision(node_id="contracts", action="block"),),
        )

        self.assertEqual(updated.node_states[0], NodeState("contracts", "blocked", "idle"))
        self.assertEqual(derive_graph_state(updated), "blocked")

    def test_replan_decision_blocks_stale_authored_graph_until_mutation(self) -> None:
        snapshot = self.snapshot_with(contracts=("pending", "settled"))

        updated = apply_decisions(
            snapshot,
            (NodeDecision(node_id="contracts", action="replan"),),
        )

        self.assertEqual(updated.node_states[0], NodeState("contracts", "blocked", "idle"))
        self.assertEqual(derive_graph_state(updated), "blocked")
        self.assertEqual(runnable_nodes(updated), ())

    def test_apply_decisions_requires_reviewable_runtime_state(self) -> None:
        snapshot = initial_graph_snapshot(self.graph())

        with self.assertRaisesRegex(ValueError, "not awaiting a semantic decision"):
            apply_decisions(
                snapshot,
                (NodeDecision(node_id="contracts", action="accept"),),
            )

    def test_apply_decisions_rejects_unknown_duplicate_and_invalid_actions(self) -> None:
        snapshot = self.snapshot_with(contracts=("pending", "awaiting_review"))

        with self.assertRaisesRegex(ValueError, "unknown node 'missing'"):
            apply_decisions(
                snapshot,
                (NodeDecision(node_id="missing", action="accept"),),
            )

        with self.assertRaisesRegex(ValueError, "duplicate decision"):
            apply_decisions(
                snapshot,
                (
                    NodeDecision(node_id="contracts", action="accept"),
                    NodeDecision(node_id="contracts", action="retry"),
                ),
            )

        with self.assertRaisesRegex(ValueError, "unsupported decision action 'skip'"):
            apply_decisions(
                snapshot,
                (NodeDecision(node_id="contracts", action="skip"),),
            )

    def test_snapshot_requires_exact_valid_node_state_set(self) -> None:
        graph = self.graph()

        missing = GraphSnapshot(
            graph=graph,
            node_states=(NodeState("contracts"),),
        )
        with self.assertRaisesRegex(ValueError, "missing states"):
            runnable_nodes(missing)

        extra = GraphSnapshot(
            graph=graph,
            node_states=tuple(NodeState(node.node_id) for node in graph.nodes)
            + (NodeState("unknown"),),
        )
        with self.assertRaisesRegex(ValueError, "unknown nodes"):
            runnable_nodes(extra)

        duplicate = GraphSnapshot(
            graph=graph,
            node_states=(
                NodeState("contracts"),
                NodeState("contracts"),
                NodeState("backend"),
                NodeState("frontend"),
                NodeState("integration"),
            ),
        )
        with self.assertRaisesRegex(ValueError, "duplicate node state"):
            runnable_nodes(duplicate)

    def test_invalid_state_values_are_rejected(self) -> None:
        snapshot = self.snapshot_with(contracts=("mystery", "idle"))
        with self.assertRaisesRegex(ValueError, "invalid semantic_state"):
            derive_graph_state(snapshot)

        snapshot = self.snapshot_with(contracts=("pending", "mystery"))
        with self.assertRaisesRegex(ValueError, "invalid runtime_state"):
            derive_graph_state(snapshot)

    def test_unknown_dependency_fails_closed_if_unvalidated_graph_reaches_scheduler(self) -> None:
        graph = TaskGraph(
            nodes=(
                GraphNode(
                    "backend",
                    "backend",
                    self.packet("Backend work."),
                    depends_on=("missing",),
                ),
            )
        )
        snapshot = initial_graph_snapshot(graph)

        with self.assertRaisesRegex(ValueError, "unknown dependency 'missing'"):
            runnable_nodes(snapshot)


if __name__ == "__main__":
    unittest.main()
