#!/usr/bin/env python3
from __future__ import annotations

import ast
import functools
import re
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
    RecoverableRepoTaskExecutionError,
    decisions_from_payload,
    task_graph_from_payload,
)
from task_graph_store import GraphRuntimeStore

_graph_runtime = GraphRuntime(GraphRuntimeStore(STATE_DB))
_PRESERVED_SESSION_PATTERN = re.compile(
    r"native session ownership was preserved and can be resumed with "
    r"session_id=(?P<literal>'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\")"
)


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
    elif "retry requested resume" in lowered:
        code = "graph_retry_invalid"
        action = "retry with resume_session=false unless the node has a previous native session"
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


def _preserved_session_id(exc: ToolError) -> str | None:
    """Recover the exact session from the direct delegation recovery contract.

    The direct tool intentionally exposes this sentence only after SessionStore ownership
    has already been persisted. Match that explicit recovery clause rather than arbitrary
    `session_id` text from unrelated errors.
    """

    match = _PRESERVED_SESSION_PATTERN.search(str(exc))
    if match is None:
        return None
    try:
        value = ast.literal_eval(match.group("literal"))
    except (SyntaxError, ValueError):
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value


async def _execute_repo_task(
    node: GraphNode,
    *,
    session_id: str | None,
) -> dict[str, Any]:
    """Adapt one GraphNode back into the existing direct delegation primitive."""

    if node.route is None:
        raise RuntimeError(
            f"runnable node {node.node_id!r} has no route for repository execution"
        )
    packet = node.task_packet
    try:
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
            session_id=session_id,
        )
    except ToolError as exc:
        preserved_session_id = _preserved_session_id(exc)
        if preserved_session_id is None:
            raise
        raise RecoverableRepoTaskExecutionError(
            str(exc),
            session_id=preserved_session_id,
        ) from exc


async def _start_repo_task(node: GraphNode) -> dict[str, Any]:
    return await _execute_repo_task(node, session_id=None)


async def _resume_repo_task(node: GraphNode, session_id: str) -> dict[str, Any]:
    return await _execute_repo_task(node, session_id=session_id)


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
    """Return the current execution snapshot and any per-node review envelopes."""
    return _graph_runtime.get_graph(graph_run_id)


@mcp.tool()
@_graph_public_errors
async def delegate_next(graph_run_id: str) -> dict[str, Any]:
    """Execute one deterministic runnable repo-task and return control to QiQi.

    Phase 8 prefers a pending selective retry over unrelated fresh work. A retry executes
    a new TaskPacket snapshot and either STARTs fresh or RESUMEs the exact prior native
    session selected by QiQi. Existing delegate_repo_task session ownership remains the
    authoritative repository/agent continuity guard.
    """
    return await _graph_runtime.delegate_next(
        graph_run_id,
        executor=_start_repo_task,
        resume_executor=_resume_repo_task,
    )


@mcp.tool()
@_graph_public_errors
async def submit_decisions(
    graph_run_id: str,
    decisions: list[dict[str, Any]],
    expected_revision: int,
) -> dict[str, Any]:
    """Apply QiQi per-node semantic review decisions and recompute graph state.

    Supported actions are `accept`, `retry`, `replan`, and `block`. For `retry`, QiQi may
    set `resume_session=true` to continue the exact prior native session and may provide
    `feedback=[...]`; feedback is carried into a fresh TaskPacket snapshot through the
    existing context.claims_to_investigate contract. Omit/false `resume_session` for a
    fresh START. `replan` still fails closed until Phase 10 graph mutation/reconciliation.
    """
    return _graph_runtime.submit_decisions(
        graph_run_id,
        decisions_from_payload(decisions),
        expected_revision=expected_revision,
    )


if __name__ == "__main__":
    mcp.run()
