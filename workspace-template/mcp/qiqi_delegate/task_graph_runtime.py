from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass, replace
from typing import Any

from core import TaskPacket, build_task_packet
from task_graph import GraphNode, TaskGraph
from task_graph_scheduler import (
    REVIEWABLE_RUNTIME_STATES,
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
_DECISION_FIELDS = frozenset({"node_id", "action", "resume_session", "feedback"})
_DECISION_REQUIRED_FIELDS = frozenset({"node_id", "action"})
_EXECUTION_TERMINAL_STATES = frozenset({"settled", "failed", "blocked"})
_RETRY_FEEDBACK_SOURCE = "QiQi semantic review"

RepoTaskExecutor = Callable[[GraphNode], Awaitable[dict[str, Any]]]
ResumeRepoTaskExecutor = Callable[[GraphNode, str], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ReviewDecision:
    """QiQi semantic decision plus retry-only execution guidance."""

    node_id: str
    action: str
    resume_session: bool = False
    feedback: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetryPlan:
    """Process-owned execution plan for the next attempt of one reviewed node."""

    task_packet: TaskPacket
    resume_session: bool
    session_id: str | None
    feedback: tuple[str, ...]


class RecoverableRepoTaskExecutionError(RuntimeError):
    """Execution failed after native session ownership was already captured."""

    def __init__(self, message: str, *, session_id: str):
        super().__init__(message)
        self.session_id = session_id


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


def _feedback_from_payload(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"graph {label} must be a list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"graph {label}[{index}] must be a string")
        cleaned = item.strip()
        if not cleaned:
            raise ValueError(f"graph {label}[{index}] must not be empty")
        result.append(cleaned)
    return tuple(result)


def _retry_task_packet(packet: TaskPacket, feedback: tuple[str, ...]) -> TaskPacket:
    """Create a fresh delegated-turn TaskPacket without mutating authored semantics.

    Retry feedback is execution context, not a new Graph schema. It is represented through
    the existing TaskPacket context contract as claims to investigate, while objective,
    scope, acceptance criteria, exclusions, constraints, and known unknowns stay authored.
    Feedback that repeats an existing trusted fact or claim keeps the existing classification
    instead of creating a contradictory/duplicate context entry.
    """

    payload = packet.as_dict()
    if feedback:
        context = dict(payload.get("context", {}))
        trusted = list(context.get("trusted_facts", []))
        claims = list(context.get("claims_to_investigate", []))
        known_propositions = {
            item["fact"].casefold()
            for item in trusted
            if isinstance(item, dict) and isinstance(item.get("fact"), str)
        }
        known_propositions.update(
            item["claim"].casefold()
            for item in claims
            if isinstance(item, dict) and isinstance(item.get("claim"), str)
        )
        for item in feedback:
            key = item.casefold()
            if key in known_propositions:
                continue
            claims.append({"claim": item, "source": _RETRY_FEEDBACK_SOURCE})
            known_propositions.add(key)
        if claims:
            context["claims_to_investigate"] = claims
        payload["context"] = context
    return build_task_packet(**payload)


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


def decisions_from_payload(payload: Any) -> tuple[ReviewDecision, ...]:
    if not isinstance(payload, list):
        raise ValueError("graph decisions must be a list")
    decisions: list[ReviewDecision] = []
    for index, raw_decision in enumerate(payload):
        label = f"decisions[{index}]"
        decision = _require_object(raw_decision, label)
        _reject_extra_fields(decision, _DECISION_FIELDS, label)
        missing = sorted(_DECISION_REQUIRED_FIELDS - set(decision))
        if missing:
            raise ValueError(
                f"graph {label} is missing required fields: {', '.join(missing)}"
            )

        action = decision["action"]
        has_retry_metadata = "resume_session" in decision or "feedback" in decision
        if action != "retry" and has_retry_metadata:
            raise ValueError(
                f"graph {label} retry metadata is only valid for action='retry'"
            )

        resume_session = decision.get("resume_session", False)
        if not isinstance(resume_session, bool):
            raise ValueError(f"graph {label}.resume_session must be a boolean")
        feedback = _feedback_from_payload(decision.get("feedback"), f"{label}.feedback")

        decisions.append(
            ReviewDecision(
                node_id=decision["node_id"],
                action=action,
                resume_session=resume_session,
                feedback=feedback,
            )
        )
    if not decisions:
        raise ValueError("graph decisions must contain at least one decision")
    return tuple(decisions)


class GraphRuntime:
    """QiQi outer-loop runtime over scheduler, persistence, and repo-task execution.

    Authored TaskGraph semantics remain process-owned and are not copied into SQLite.
    Phase 6 executes exactly one runnable repo-task per wave through the existing
    delegate_repo_task primitive. Phase 7 exposes per-node semantic review. Phase 8 adds
    selective retry with a fresh TaskPacket snapshot plus START/RESUME choice. Parallel
    waves, graph mutation/reconciliation, and durable authored-graph recovery remain later.
    """

    def __init__(self, store: GraphRuntimeStore):
        self.store = store
        self._graphs: dict[str, TaskGraph] = {}
        self._retry_plans: dict[tuple[str, str], RetryPlan] = {}

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

        graph_nodes = {node.node_id: node for node in graph.nodes}
        execution_nodes: list[dict[str, Any]] = []
        review_required: list[dict[str, Any]] = []
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
            result = attempt.get("result") if attempt is not None else None
            retry_plan = self._retry_plans.get((graph_run_id, state.node_id))
            execution_nodes.append(
                {
                    "node_id": state.node_id,
                    "semantic_state": state.semantic_state,
                    "runtime_state": state.runtime_state,
                    "current_attempt_id": current_attempt_id,
                    "session_id": persisted.get("session_id"),
                    "turn_id": persisted.get("turn_id"),
                    "result": result,
                    "retry_pending": (
                        {
                            "resume_session": retry_plan.resume_session,
                            "session_id": retry_plan.session_id,
                            "feedback": list(retry_plan.feedback),
                        }
                        if retry_plan is not None
                        else None
                    ),
                }
            )

            if (
                state.semantic_state == "pending"
                and state.runtime_state in REVIEWABLE_RUNTIME_STATES
            ):
                authored = graph_nodes[state.node_id]
                review_required.append(
                    {
                        "node_id": state.node_id,
                        "repository": authored.repository,
                        "runtime_state": state.runtime_state,
                        "acceptance_criteria": list(
                            authored.task_packet.acceptance_criteria
                        ),
                        "result": result,
                    }
                )

        return {
            "graph_run_id": graph_run_id,
            "graph_state": derive_graph_state(snapshot),
            "revision": revision,
            "current_wave_id": run.get("current_wave_id"),
            "runnable_nodes": [node.node_id for node in runnable_nodes(snapshot)],
            "review_required": review_required,
            "nodes": execution_nodes,
            "authored_node_count": len(graph.nodes),
        }

    async def delegate_next(
        self,
        graph_run_id: str,
        *,
        executor: RepoTaskExecutor,
        resume_executor: ResumeRepoTaskExecutor | None = None,
    ) -> dict[str, Any]:
        """Execute exactly one runnable repo-task and return control to QiQi.

        A pending retry is preferred over unrelated fresh runnable work. Retry execution
        uses a freshly built TaskPacket snapshot. When QiQi requested continuity, the exact
        persisted native session is passed through both the Graph store guard and the
        existing direct delegation RESUME ownership checks.
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

        retry_candidates = [
            item
            for item in candidates
            if (graph_run_id, item.node_id) in self._retry_plans
        ]
        node = retry_candidates[0] if retry_candidates else candidates[0]
        retry_key = (graph_run_id, node.node_id)
        retry_plan = self._retry_plans.get(retry_key)
        execution_node = (
            replace(node, task_packet=retry_plan.task_packet)
            if retry_plan is not None
            else node
        )
        if execution_node.route is None:
            raise RuntimeError(
                f"runnable node {execution_node.node_id!r} has no route for repository execution"
            )
        if not callable(executor):
            raise ValueError("repo-task executor must be callable")
        if (
            retry_plan is not None
            and retry_plan.resume_session
            and not callable(resume_executor)
        ):
            raise RuntimeError("retry requested RESUME but no resume executor is available")

        wave_id = new_wave_id()
        attempt_id = self.store.start_attempt(
            graph_run_id,
            execution_node.node_id,
            wave_id,
            resume_session=(retry_plan.resume_session if retry_plan is not None else False),
            session_id=(retry_plan.session_id if retry_plan is not None else None),
        )
        if retry_plan is not None:
            self._retry_plans.pop(retry_key, None)

        try:
            if retry_plan is not None and retry_plan.resume_session:
                assert retry_plan.session_id is not None
                assert resume_executor is not None
                raw_result = await resume_executor(execution_node, retry_plan.session_id)
            else:
                raw_result = await executor(execution_node)
            result = _validated_execution_result(raw_result)
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
        except RecoverableRepoTaskExecutionError as exc:
            # Direct delegation can discover/persist the native session before final-result
            # capture fails. Keep that exact recovery key on the failed graph attempt so a
            # later semantic RETRY may RESUME the same native conversation.
            self.store.finish_attempt(
                attempt_id,
                runtime_state="failed",
                result={
                    "state": "failed",
                    "agent_response": None,
                    "failure_type": "executor_exception",
                },
                session_id=exc.session_id,
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
                    "node_id": execution_node.node_id,
                    "attempt_id": attempt_id,
                    "runtime_state": result["state"],
                    "session_id": result["session_id"],
                    "turn_id": result["turn_id"],
                    "agent_response": result["agent_response"],
                    "resume_session": bool(
                        retry_plan is not None and retry_plan.resume_session
                    ),
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
        decisions: tuple[ReviewDecision, ...],
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

        scheduler_decisions = tuple(
            NodeDecision(node_id=decision.node_id, action=decision.action)
            for decision in decisions
        )
        updated = apply_decisions(snapshot, scheduler_decisions)

        graph_nodes = {node.node_id: node for node in graph.nodes}
        retry_plans: dict[tuple[str, str], RetryPlan] = {}
        for decision in decisions:
            if decision.action != "retry":
                continue
            persisted = self.store.get_node(graph_run_id, decision.node_id)
            if persisted is None:
                raise RuntimeError(
                    f"persisted graph run is missing node state for {decision.node_id!r}"
                )
            session_id = persisted.get("session_id") if decision.resume_session else None
            if decision.resume_session and (
                not isinstance(session_id, str) or not session_id.strip()
            ):
                raise RuntimeError(
                    f"retry requested RESUME for node {decision.node_id!r} "
                    "but no previous native session is available"
                )
            authored = graph_nodes[decision.node_id]
            retry_plans[(graph_run_id, decision.node_id)] = RetryPlan(
                task_packet=_retry_task_packet(authored.task_packet, decision.feedback),
                resume_session=decision.resume_session,
                session_id=session_id,
                feedback=decision.feedback,
            )

        self.store.save_snapshot(
            graph_run_id,
            updated,
            expected_revision=expected_revision,
        )
        # The current authored graph remains unchanged. Retry plans are process-owned
        # execution metadata, matching the current process-owned graph-definition boundary.
        self._graphs[graph_run_id] = graph
        for decision in decisions:
            self._retry_plans.pop((graph_run_id, decision.node_id), None)
        self._retry_plans.update(retry_plans)

        updated_states = {state.node_id: state for state in updated.node_states}
        current = self.get_graph(graph_run_id)
        outcomes: list[dict[str, Any]] = []
        for decision in decisions:
            outcome: dict[str, Any] = {
                "node_id": decision.node_id,
                "action": decision.action,
                "semantic_state": updated_states[decision.node_id].semantic_state,
            }
            if decision.action == "retry":
                plan = retry_plans[(graph_run_id, decision.node_id)]
                outcome["retry_execution"] = {
                    "resume_session": plan.resume_session,
                    "session_id": plan.session_id,
                    "feedback": list(plan.feedback),
                }
            outcomes.append(outcome)

        return {
            **current,
            "decision_outcomes": outcomes,
            "replan_required_nodes": [
                decision.node_id
                for decision in decisions
                if decision.action == "replan"
            ],
        }
