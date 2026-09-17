#!/usr/bin/env python3
from __future__ import annotations

import functools
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from server import (
    STATE_DB,
    TaskContextInput,
    _load_repo_registry,
    delegate_repo_task,
    mcp,
)
from task_graph import GraphNode
from task_graph_runtime import (
    GraphRuntime,
    decisions_from_payload,
    task_graph_from_payload,
)
from task_graph_store import GraphRuntimeStore

_graph_runtime = GraphRuntime(GraphRuntimeStore(STATE_DB))


def _graph_tool_error(exc: ValueError | RuntimeError) -> ToolError:
    message = str(exc)
    lowered = message.lower()
    code = "graph_runtime_error"
    action = "inspect the current graph snapshot and retry the outer-loop operation"

    if isinstance(exc, ValueError):
        code = "graph_invalid"
        action = "correct the TaskGraph or structured decision payload and retry"
    elif "stale graph snapshot revision" in lowered:
        code = "graph_revision_conflict"
        action = "call get_graph, review the current revision, then resubmit decisions"
    elif "unknown graph_run_id" in lowered:
        code = "unknown_graph_run"
        action = "use a graph_run_id returned by start_graph"
    elif "restart recovery is not implemented" in lowered or "definition is unavailable" in lowered:
        code = "graph_definition_unavailable"
        action = "restart the graph from the authored TaskGraph in the current runtime"
    elif "no route for repository execution" in lowered:
        code = "graph_execution_invalid"
        action = "author a non-empty route on the repo-task node before executing the graph"
    elif "not ready for delegation" in lowered or "only accepted while graph_state" in lowered:
        code = "graph_state_conflict"
        action = "follow the returned graph_state outer-loop transition before retrying"

    return ToolError(f"code={code}; {message}; action={action}")


def _graph_public_errors(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ToolError:
            raise
        except (ValueError, RuntimeError) as exc:
            raise _graph_tool_error(exc) from exc

    return wrapper


def _delegate_context(node: GraphNode) -> TaskContextInput | None:
    context = node.task_packet.context
    if context is None:
        return None
    return TaskContextInput(**context.as_dict())


async def _execute_repo_task(node: GraphNode) -> dict[str, Any]:
    """Adapt one GraphNode back into the existing direct delegation primitive."""

    if node.route is None:
        raise RuntimeError(
            f"runnable node {node.node_id!r} has no route for repository execution"
        )
    packet = node.task_packet
    return await delegate_repo_task(
        repository=node.repository,
        route=node.route,
        objective=packet.objective,
        scope=list(packet.scope),
        acceptance_criteria=list(packet.acceptance_criteria),
        out_of_scope=list(packet.out_of_scope),
        context=_delegate_context(node),
        constraints=list(packet.constraints),
        known_unknowns=list(packet.known_unknowns),
        session_id=None,
    )


@mcp.tool()
@_graph_public_errors
async def start_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Create a validated TaskGraph run and return the initial outer-loop snapshot.

    `graph.nodes[*].task_packet` uses the existing canonical TaskPacket fields. Graph
    orchestration metadata (`node_id`, `repository`, `route`, `kind`, `depends_on`) stays
    outside TaskPacket. The repository names are validated against the current repos.yaml.
    """
    authored = task_graph_from_payload(graph)
    registry = _load_repo_registry()
    return _graph_runtime.start_graph(
        authored,
        repository_names=registry.keys(),
    )


@mcp.tool()
@_graph_public_errors
async def get_graph(graph_run_id: str) -> dict[str, Any]:
    """Return the current execution snapshot for one graph run."""
    return _graph_runtime.get_graph(graph_run_id)


@mcp.tool()
@_graph_public_errors
async def delegate_next(graph_run_id: str) -> dict[str, Any]:
    """Execute one deterministic runnable repo-task and return control to QiQi.

    Phase 6 runs exactly one node per wave through the existing `delegate_repo_task`
    primitive. The child result is persisted as runtime evidence, but runtime settlement
    does not satisfy the node: the graph returns `awaiting_review` for QiQi review.
    """
    return await _graph_runtime.delegate_next(
        graph_run_id,
        executor=_execute_repo_task,
    )


@mcp.tool()
@_graph_public_errors
async def submit_decisions(
    graph_run_id: str,
    decisions: list[dict[str, Any]],
    expected_revision: int,
) -> dict[str, Any]:
    """Apply QiQi semantic review decisions and return the recomputed graph snapshot.

    The current structured actions remain `accept`, `retry`, and `block`. `replan`
    remains a later dynamic-graph mutation concern. `expected_revision` is an
    optimistic-CAS guard against reviewing stale execution state. Phase 8 will add the
    selective START/RESUME retry policy; Phase 6 always executes a fresh START.
    """
    return _graph_runtime.submit_decisions(
        graph_run_id,
        decisions_from_payload(decisions),
        expected_revision=expected_revision,
    )


if __name__ == "__main__":
    mcp.run()
