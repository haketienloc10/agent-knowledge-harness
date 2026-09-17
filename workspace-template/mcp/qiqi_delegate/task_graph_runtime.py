from __future__ import annotations

from collections.abc import Collection
from typing import Any

from core import build_task_packet
from task_graph import GraphNode, TaskGraph
from task_graph_scheduler import (
    GraphSnapshot,
    NodeDecision,
    apply_decisions,
    derive_graph_state,
    initial_graph_snapshot,
    runnable_nodes,
)
from task_graph_store import GraphRuntimeStore
from task_graph_validation import validate_task_graph

_GRAPH_FIELDS = frozenset({"nodes"})
_NODE_FIELDS = frozenset(
    {"node_id", "kind", "repository", "route", "depends_on", "task_packet"}
)
_NODE_REQUIRED_FIELDS = frozenset({"node_id", "repository", "task_packet"})
_DECISION_FIELDS = frozenset({"node_id", "action"})


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"graph {label} must be an object")
    return value


def _reject_extra_fields(value: dict[str, Any], allowed: Collection[str], label: str) -> None:
    extra = sorted(set(value) - set(allowed))
    if extra:
        raise ValueError(
            f"graph {label} has unsupported fields: {', '.join(extra)}"
        )


def task_graph_from_payload(payload: Any) -> TaskGraph:
    """Build a TaskGraph transport value without introducing another task schema.

    Graph transport shape is decoded here, while delegated-task semantics still flow
    through the existing build_task_packet() contract.
    """

    graph_value = _require_object(payload, "payload")
    _reject_extra_fields(graph_value, _GRAPH_FIELDS, "payload")
    if "nodes" not in graph_value:
        raise ValueError("graph payload is missing required field: nodes")

    raw_nodes = graph_value["nodes"]
    if not isinstance(raw_nodes, list):
        raise ValueError("graph nodes must be a list")

    nodes: list[GraphNode] = []
    for index, raw_node in enumerate(raw_nodes):
        label = f"nodes[{index}]"
        node_value = _require_object(raw_node, label)
        _reject_extra_fields(node_value, _NODE_FIELDS, label)
        missing = sorted(_NODE_REQUIRED_FIELDS - set(node_value))
        if missing:
            raise ValueError(
                f"graph {label} is missing required fields: {', '.join(missing)}"
            )

        raw_packet = node_value["task_packet"]
        if not isinstance(raw_packet, dict):
            raise ValueError(f"graph {label}.task_packet must be an object")
        try:
            packet = build_task_packet(**raw_packet)
        except TypeError as exc:
            raise ValueError(
                f"graph {label} has invalid TaskPacket fields: {exc}"
            ) from exc
        except ValueError as exc:
            raise ValueError(f"graph {label} has invalid TaskPacket: {exc}") from exc

        raw_dependencies = node_value.get("depends_on", [])
        depends_on: Any
        if isinstance(raw_dependencies, list):
            depends_on = tuple(raw_dependencies)
        else:
            # Preserve malformed containers so the canonical graph validator rejects
            # them instead of silently changing the authored topology.
            depends_on = raw_dependencies

        nodes.append(
            GraphNode(
                node_id=node_value["node_id"],
                repository=node_value["repository"],
                task_packet=packet,
                depends_on=depends_on,
                route=node_value.get("route"),
                kind=node_value.get("kind", "repo_task"),
            )
        )

    return TaskGraph(nodes=tuple(nodes))


def decisions_from_payload(payload: Any) -> tuple[NodeDecision, ...]:
    if not isinstance(payload, list):
        raise ValueError("graph decisions must be a list")
    decisions: list[NodeDecision] = []
    for index, raw_decision in enumerate(payload):
        label = f"decisions[{index}]"
        decision = _require_object(raw_decision, label)
        _reject_extra_fields(decision, _DECISION_FIELDS, label)
        missing = sorted(_DECISION_FIELDS - set(decision))
        if missing:
            raise ValueError(
                f"graph {label} is missing required fields: {', '.join(missing)}"
            )
        decisions.append(
            NodeDecision(
                node_id=decision["node_id"],
                action=decision["action"],
            )
        )
    if not decisions:
        raise ValueError("graph decisions must contain at least one decision")
    return tuple(decisions)


class GraphRuntime:
    """Phase-5 QiQi outer-loop API over scheduler + durable runtime state.

    Authored TaskGraph semantics remain process-owned in Phase 5 and are not copied
    into SQLite. Durable restart recovery of authored graph definitions is intentionally
    deferred to the later recovery/reconciliation phase.
    """

    def __init__(self, store: GraphRuntimeStore):
        self.store = store
        self._graphs: dict[str, TaskGraph] = {}

    def start_graph(
        self,
        graph: TaskGraph,
        *,
        repository_names: Collection[str],
    ) -> dict[str, Any]:
        validate_task_graph(graph, repository_names=repository_names)
        snapshot = initial_graph_snapshot(graph)
        graph_run_id = self.store.create_run(snapshot)
        self._graphs[graph_run_id] = graph
        return self.get_graph(graph_run_id)

    def _graph_for_run(self, graph_run_id: str) -> TaskGraph:
        if not isinstance(graph_run_id, str) or not graph_run_id.strip():
            raise ValueError("graph_run_id must be a non-empty string")
        graph_run_id = graph_run_id.strip()
        graph = self._graphs.get(graph_run_id)
        if graph is not None:
            return graph
        if self.store.get_run(graph_run_id) is None:
            raise RuntimeError(f"unknown graph_run_id: {graph_run_id!r}")
        raise RuntimeError(
            "graph definition is unavailable for this persisted graph_run_id; "
            "Phase 5 restart recovery is not implemented"
        )

    def _snapshot(self, graph_run_id: str) -> tuple[TaskGraph, GraphSnapshot, int]:
        graph = self._graph_for_run(graph_run_id)
        snapshot, revision = self.store.load_snapshot_with_revision(graph_run_id, graph)
        return graph, snapshot, revision

    def get_graph(self, graph_run_id: str) -> dict[str, Any]:
        graph, snapshot, revision = self._snapshot(graph_run_id)
        run = self.store.get_run(graph_run_id)
        if run is None:
            raise RuntimeError(f"unknown graph_run_id: {graph_run_id!r}")

        execution_nodes: list[dict[str, Any]] = []
        for state in snapshot.node_states:
            persisted = self.store.get_node(graph_run_id, state.node_id)
            if persisted is None:
                raise RuntimeError(
                    f"persisted graph run is missing node state for {state.node_id!r}"
                )
            current_attempt_id = persisted.get("current_attempt_id")
            attempt = (
                self.store.get_attempt(current_attempt_id)
                if isinstance(current_attempt_id, str) and current_attempt_id
                else None
            )
            execution_nodes.append(
                {
                    "node_id": state.node_id,
                    "semantic_state": state.semantic_state,
                    "runtime_state": state.runtime_state,
                    "current_attempt_id": current_attempt_id,
                    "session_id": persisted.get("session_id"),
                    "turn_id": persisted.get("turn_id"),
                    "result": attempt.get("result") if attempt is not None else None,
                }
            )

        return {
            "graph_run_id": graph_run_id,
            "graph_state": derive_graph_state(snapshot),
            "revision": revision,
            "current_wave_id": run.get("current_wave_id"),
            "runnable_nodes": [node.node_id for node in runnable_nodes(snapshot)],
            "nodes": execution_nodes,
            "authored_node_count": len(graph.nodes),
        }

    def delegate_next(self, graph_run_id: str) -> dict[str, Any]:
        """Return the deterministic next dispatch contract without executing it.

        Phase 6 connects this exact dispatch boundary to delegate_repo_task(). Phase 5
        deliberately has no child-agent/Herdr side effect.
        """

        graph, snapshot, revision = self._snapshot(graph_run_id)
        graph_state = derive_graph_state(snapshot)
        if graph_state != "ready":
            raise RuntimeError(
                f"graph is not ready for delegation: state={graph_state!r}"
            )
        candidates = runnable_nodes(snapshot)
        if not candidates:
            raise RuntimeError("graph is ready but has no runnable node")
        node = candidates[0]
        return {
            "graph_run_id": graph_run_id,
            "graph_state": graph_state,
            "revision": revision,
            "dispatch": {
                "node": node.as_dict(),
                "execution_state": "planned",
                "execution_side_effect": False,
            },
            "remaining_runnable_nodes": [item.node_id for item in candidates[1:]],
        }

    def submit_decisions(
        self,
        graph_run_id: str,
        decisions: tuple[NodeDecision, ...],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        graph, snapshot, revision = self._snapshot(graph_run_id)
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise ValueError("expected_revision must be a non-negative integer")
        if expected_revision < 0:
            raise ValueError("expected_revision must be a non-negative integer")
        if revision != expected_revision:
            raise RuntimeError(
                "stale graph snapshot revision: "
                f"expected {expected_revision}, current {revision}"
            )

        graph_state = derive_graph_state(snapshot)
        if graph_state != "awaiting_review":
            raise RuntimeError(
                "graph decisions are only accepted while graph_state='awaiting_review'; "
                f"current state={graph_state!r}"
            )

        updated = apply_decisions(snapshot, decisions)
        self.store.save_snapshot(
            graph_run_id,
            updated,
            expected_revision=expected_revision,
        )
        # `graph` is intentionally retained in the process registry; save_snapshot
        # persists only execution state.
        self._graphs[graph_run_id] = graph
        return self.get_graph(graph_run_id)
