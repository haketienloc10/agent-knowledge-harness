from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import build_task_packet  # noqa: E402
from task_graph import GraphNode, TaskGraph  # noqa: E402


class TaskGraphDomainTests(unittest.TestCase):
    def packet(self):
        return build_task_packet(
            objective="Expose payment_status in the Order API.",
            scope=["Order API", "payment status mapping"],
            acceptance_criteria=[
                "API response contains payment_status",
                "null status maps to unknown",
            ],
            out_of_scope=["frontend rendering"],
            constraints=["preserve backward compatibility"],
        )

    def test_graph_node_wraps_existing_task_packet_without_flattening(self) -> None:
        packet = self.packet()
        node = GraphNode(
            node_id="backend-payment-status",
            repository="backend",
            task_packet=packet,
        )

        self.assertIs(node.task_packet, packet)
        payload = node.as_dict()
        self.assertEqual(payload["task_packet"], packet.as_dict())
        self.assertNotIn("objective", payload)
        self.assertNotIn("scope", payload)
        self.assertNotIn("acceptance_criteria", payload)

    def test_graph_metadata_stays_outside_task_packet(self) -> None:
        packet = self.packet()
        node = GraphNode(
            node_id="backend-payment-status",
            kind="repo_task",
            repository="backend",
            route="claude-balanced",
            depends_on=("contracts-payment-status",),
            task_packet=packet,
        )

        self.assertEqual(
            node.as_dict(),
            {
                "node_id": "backend-payment-status",
                "kind": "repo_task",
                "repository": "backend",
                "depends_on": ["contracts-payment-status"],
                "task_packet": packet.as_dict(),
                "route": "claude-balanced",
            },
        )

    def test_task_graph_preserves_authored_node_order(self) -> None:
        packet = self.packet()
        contracts = GraphNode(
            node_id="contracts-payment-status",
            repository="contracts",
            task_packet=packet,
        )
        backend = GraphNode(
            node_id="backend-payment-status",
            repository="backend",
            depends_on=("contracts-payment-status",),
            task_packet=packet,
        )

        graph = TaskGraph(nodes=(contracts, backend))

        self.assertEqual(
            [node["node_id"] for node in graph.as_dict()["nodes"]],
            ["contracts-payment-status", "backend-payment-status"],
        )

    def test_graph_domain_objects_are_immutable(self) -> None:
        packet = self.packet()
        node = GraphNode(
            node_id="backend-payment-status",
            repository="backend",
            task_packet=packet,
        )
        graph = TaskGraph(nodes=(node,))

        with self.assertRaises(FrozenInstanceError):
            node.repository = "frontend"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            graph.nodes = ()  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
