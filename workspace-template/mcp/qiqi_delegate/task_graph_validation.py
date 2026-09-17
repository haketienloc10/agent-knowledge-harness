from __future__ import annotations

from collections.abc import Collection

from core import TaskPacket, build_task_packet
from task_graph import TaskGraph


def validate_task_graph(
    graph: TaskGraph,
    *,
    repository_names: Collection[str],
) -> None:
    """Validate authored graph structure without introducing a second task schema.

    `repository_names` must come from the canonical workspace repository registry.
    Task semantics are revalidated through the existing `build_task_packet()` path;
    this module owns only graph-specific invariants.
    """

    if not graph.nodes:
        raise ValueError("task graph must contain at least one node")

    repositories = set(repository_names)
    node_ids: set[str] = set()

    for node in graph.nodes:
        if not isinstance(node.node_id, str) or not node.node_id.strip():
            raise ValueError("graph node_id must not be empty")
        if node.node_id in node_ids:
            raise ValueError(f"duplicate graph node_id: {node.node_id!r}")
        node_ids.add(node.node_id)

        if node.kind != "repo_task":
            raise ValueError(
                f"unsupported graph node kind {node.kind!r} for node {node.node_id!r}"
            )
        if not isinstance(node.repository, str) or not node.repository.strip():
            raise ValueError(f"node {node.node_id!r} repository must not be empty")
        if node.repository not in repositories:
            raise ValueError(
                f"node {node.node_id!r} references unknown repository {node.repository!r}"
            )
        if not isinstance(node.task_packet, TaskPacket):
            raise ValueError(f"repo_task node {node.node_id!r} must contain a TaskPacket")

        try:
            build_task_packet(**node.task_packet.as_dict())
        except ValueError as exc:
            raise ValueError(
                f"node {node.node_id!r} has invalid TaskPacket: {exc}"
            ) from exc

    dependents: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree: dict[str, int] = {}

    for node in graph.nodes:
        indegree[node.node_id] = len(node.depends_on)
        for dependency in node.depends_on:
            if dependency == node.node_id:
                raise ValueError(f"node {node.node_id!r} must not depend on itself")
            if dependency not in node_ids:
                raise ValueError(
                    f"node {node.node_id!r} references unknown dependency {dependency!r}"
                )
            dependents[dependency].append(node.node_id)

    roots = [node_id for node_id, degree in indegree.items() if degree == 0]
    ready = list(roots)
    visited = 0

    while ready:
        current = ready.pop()
        visited += 1
        for dependent in dependents[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)

    if visited != len(node_ids):
        cyclic = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
        raise ValueError(f"graph contains a dependency cycle involving: {', '.join(cyclic)}")

    terminal_nodes = [node_id for node_id, items in dependents.items() if not items]
    if not roots or not terminal_nodes:
        raise ValueError("task graph has no executable root-to-terminal work path")
