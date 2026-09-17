#!/usr/bin/env python3
from __future__ import annotations

import functools
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from server import STATE_DB, _load_repo_registry, mcp
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
        action = "restart the graph from the authored TaskGraph in this Phase-5 runtime"
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
    """Return the next deterministic repo-task dispatch while graph_state is ready.

    Phase 5 intentionally performs no child-agent or Herdr execution. The returned
    dispatch has `execution_side_effect=false`; Phase 6 connects this boundary to the
    existing delegate_repo_task execution primitive.
    """
    return _graph_runtime.delegate_next(graph_run_id)


@mcp.tool()
@_graph_public_errors
async def submit_decisions(
    graph_run_id: str,
    decisions: list[dict[str, Any]],
    expected_revision: int,
) -> dict[str, Any]:
    """Apply QiQi semantic review decisions and return the recomputed graph snapshot.

    Phase 5 supports the Phase-3 structured actions `accept`, `retry`, and `block`.
    `replan` remains a later dynamic-graph mutation concern. `expected_revision` is an
    optimistic-CAS guard against reviewing stale execution state.
    """
    return _graph_runtime.submit_decisions(
        graph_run_id,
        decisions_from_payload(decisions),
        expected_revision=expected_revision,
    )


if __name__ == "__main__":
    mcp.run()
