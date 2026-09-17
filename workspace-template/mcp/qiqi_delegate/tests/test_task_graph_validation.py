from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import TaskPacket, build_task_packet  # noqa: E402
from task_graph import GraphNode, TaskGraph  # noqa: E402
from task_graph_validation import validate_task_graph  # noqa: E402


class TaskGraphValidationTests(unittest.TestCase):
    def packet(self, objective: str = "Implement repository-local work."):
        return build_task_packet(
            objective=objective,
            scope=["repository-local implementation"],
            acceptance_criteria=["focused verification passes"],
        )

    def test_valid_dag_reuses_existing_taskpacket_validation(self) -> None:
        graph = TaskGraph(
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
            )
        )

        validate_task_graph(
            graph,
            repository_names={"contracts", "backend", "frontend"},
        )

    def test_duplicate_node_ids_are_rejected(self) -> None:
        graph = TaskGraph(
            nodes=(
                GraphNode("backend", "backend", self.packet()),
                GraphNode("backend", "backend", self.packet()),
            )
        )
        with self.assertRaisesRegex(ValueError, "duplicate graph node_id"):
            validate_task_graph(graph, repository_names={"backend"})

    def test_unknown_dependency_is_rejected(self) -> None:
        graph = TaskGraph(
            nodes=(
                GraphNode(
                    "backend",
                    "backend",
                    self.packet(),
                    depends_on=("contracts",),
                ),
            )
        )
        with self.assertRaisesRegex(ValueError, "unknown dependency 'contracts'"):
            validate_task_graph(graph, repository_names={"backend"})

    def test_self_dependency_is_rejected(self) -> None:
        graph = TaskGraph(
            nodes=(
                GraphNode(
                    "backend",
                    "backend",
                    self.packet(),
                    depends_on=("backend",),
                ),
            )
        )
        with self.assertRaisesRegex(ValueError, "must not depend on itself"):
            validate_task_graph(graph, repository_names={"backend"})

    def test_dependency_cycle_is_rejected(self) -> None:
        graph = TaskGraph(
            nodes=(
                GraphNode("a", "backend", self.packet(), depends_on=("b",)),
                GraphNode("b", "frontend", self.packet(), depends_on=("a",)),
            )
        )
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            validate_task_graph(
                graph,
                repository_names={"backend", "frontend"},
            )

    def test_repository_must_exist_in_canonical_registry_names(self) -> None:
        graph = TaskGraph(
            nodes=(GraphNode("backend", "backend", self.packet()),)
        )
        with self.assertRaisesRegex(ValueError, "unknown repository 'backend'"):
            validate_task_graph(graph, repository_names={"frontend"})

    def test_empty_graph_has_no_executable_work_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one node"):
            validate_task_graph(TaskGraph(nodes=()), repository_names={"backend"})

    def test_repo_task_semantics_use_existing_taskpacket_validator(self) -> None:
        invalid_packet = TaskPacket(
            objective="Implementation",
            scope=(),
            acceptance_criteria=("verification passes",),
        )
        graph = TaskGraph(
            nodes=(GraphNode("backend", "backend", invalid_packet),)
        )
        with self.assertRaisesRegex(
            ValueError,
            "invalid TaskPacket: scope must contain at least one item",
        ):
            validate_task_graph(graph, repository_names={"backend"})

    def test_only_repo_task_kind_is_supported_in_phase_2(self) -> None:
        graph = TaskGraph(
            nodes=(
                GraphNode(
                    "approval",
                    "backend",
                    self.packet(),
                    kind="human_gate",
                ),
            )
        )
        with self.assertRaisesRegex(ValueError, "unsupported graph node kind"):
            validate_task_graph(graph, repository_names={"backend"})


if __name__ == "__main__":
    unittest.main()
