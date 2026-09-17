from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection
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
from task_graph_store import GraphRuntimeStore, new_wave_id
from task_graph_validation import validate_task_graph

_GRAPH_FIELDS = frozenset({"nodes"})
_NODE_FIELDS = frozenset(
    {"node_id", "kind", "repository", "route", "depends_on", "task_packet"}
)
_NODE_REQUIRED_FIELDS = frozenset({"node_id", "repository", "task_packet"})
_DECISION_FIELDS = frozenset({"node_id", "action"})
_EXECUTION_TERMINAL_STATES = frozenset({"settled", "failed", "blocked"})

RepoTaskExecutor = Callable[[GraphNode], Awaitable[dict[str, Any]]]


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


def _required_execution_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"repo-task execution result {label} must be a non-empty string")
    return value


def _validated_execution_result(value: Any) -> dict[str, Any]:
    """Validate the normalized result returned by the existing repo-task primitive."""

    if not isinstance(value, dict):
        raise RuntimeError("repo-task executor returned a non-object result")
    state = value.get("state")
    if state not in _EXECUTION_TERMINAL_STATES:
        raise RuntimeError(
            f"repo-task executor returned unsupported terminal state: {state!r}"
        )
    _required_execution_id(value.get("session_id"), "session_id")
    _required_execution_id(value.get("turn_id"), "turn_id")
    if "agent_response" not in value:
        raise RuntimeError("repo-task execution result is missing agent_response")
    response = value["agent_response"]
    if response is not None and not isinstance(response, str):
        raise RuntimeError("repo-task execution result agent_response must be a string or null")
    return dict(value)


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
    """QiQi outer-loop runtime over scheduler, persistence, and repo-task execution.

    Authored TaskGraph semantics remain process-owned and are not copied into SQLite.
    Phase 6 executes exactly one runnable repo-task per wave through an injected adapter
    for the existing delegate_repo_task primitive. Parallel waves, selective RESUME,
    and durable authored-graph recovery remain later phases.
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
            "durable authored-graph restart recovery is not implemented"
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

    async def delegate_next(
        self,
        graph_run_id: str,
        *,
        executor: RepoTaskExecutor,
    ) -> dict[str, Any]:
        """Execute exactly one runnable repo-task and return control to QiQi.

        Runtime settlement remains distinct from semantic acceptance: after a settled,
        failed, or blocked child turn the node remains semantically pending and the graph
        becomes `awaiting_review` until QiQi submits a decision.
        """

        _, snapshot, _ = self._snapshot(graph_run_id)
        graph_state = derive_graph_state(snapshot)
        if graph_state != "ready":
            raise RuntimeError(
                f"graph is not ready for delegation: state={graph_state!r}"
            )
        candidates = runnable_nodes(snapshot)
        if not candidates:
            raise RuntimeError("graph is ready but has no runnable node")
        node = candidates[0]
        if node.route is None:
            raise RuntimeError(
                f"runnable node {node.node_id!r} has no route for repository execution"
            )
        if not callable(executor):
            raise ValueError("repo-task executor must be callable")

        wave_id = new_wave_id()
        attempt_id = self.store.start_attempt(
            graph_run_id,
            node.node_id,
            wave_id,
        )

        try:
            result = _validated_execution_result(await executor(node))
        except asyncio.CancelledError:
            # Cancellation bypasses `except Exception` on supported Python versions.
            # Persist a terminal runtime fact and close the wave before propagating the
            # cancellation so the graph cannot be stranded permanently in `running`.
            self.store.finish_attempt(
                attempt_id,
                runtime_state="failed",
                result={
                    "state": "failed",
                    "agent_response": None,
                    "failure_type": "execution_cancelled",
                },
            )
            self.store.close_wave(graph_run_id, wave_id)
            raise
        except Exception:
            # Do not strand deterministic runtime state when the synchronous execution
            # primitive fails before producing its normalized terminal result. Preserve
            # only a generic execution fact here; the original exception still propagates
            # through the public tool boundary without being copied into runtime history.
            self.store.finish_attempt(
                attempt_id,
                runtime_state="failed",
                result={
                    "state": "failed",
                    "agent_response": None,
                    "failure_type": "executor_exception",
                },
            )
            self.store.close_wave(graph_run_id, wave_id)
            raise

        self.store.finish_attempt(
            attempt_id,
            runtime_state=result["state"],
            result=result,
            session_id=result["session_id"],
            turn_id=result["turn_id"],
        )
        self.store.close_wave(graph_run_id, wave_id)

        current = self.get_graph(graph_run_id)
        return {
            **current,
            "wave_id": wave_id,
            "results": [
                {
                    "node_id": node.node_id,
                    "attempt_id": attempt_id,
                    "runtime_state": result["state"],
                    "session_id": result["session_id"],
                    "turn_id": result["turn_id"],
                    "agent_response": result["agent_response"],
                    **(
                        {"blocker_type": result["blocker_type"]}
                        if "blocker_type" in result
                        else {}
                    ),
                }
            ],
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
