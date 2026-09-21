#!/usr/bin/env python3
from __future__ import annotations

import ast
import functools
import re
from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field

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


class TaskPacketInput(BaseModel):
    """Public transport shape for the existing canonical TaskPacket contract."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1)
    scope: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
    acceptance_criteria: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
    out_of_scope: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    context: TaskContextInput | None = None
    constraints: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    known_unknowns: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)


class GraphNodeInput(BaseModel):
    """Public GraphNode transport schema; TaskPacket remains the semantic contract."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    repository: str = Field(
        min_length=1,
        description="Exact repository name from workspace repos.yaml, not a filesystem path.",
    )
    task_packet: TaskPacketInput
    depends_on: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    route: str | None = Field(
        default=None,
        description="Exact execution route from instructions/agent-routing.yaml when executing this node.",
    )
    kind: Literal["repo_task"] = Field(
        default="repo_task",
        description=(
            "Execution node kind. Only repo_task is supported; omit this field to use "
            "the default. Do not invent values such as task or implementation."
        ),
    )


class TaskGraphInput(BaseModel):
    """Public TaskGraph transport schema with constrained orchestration metadata."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNodeInput] = Field(min_length=1)


class _DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)


class AcceptDecisionInput(_DecisionInput):
    action: Literal["accept"]


class RetryDecisionInput(_DecisionInput):
    action: Literal["retry"]
    resume_session: bool = False
    feedback: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)


class ReplanDecisionInput(_DecisionInput):
    action: Literal["replan"]


class BlockDecisionInput(_DecisionInput):
    action: Literal["block"]


GraphDecisionInput = Annotated[
    AcceptDecisionInput | RetryDecisionInput | ReplanDecisionInput | BlockDecisionInput,
    Field(discriminator="action"),
]
DecisionListInput = Annotated[list[GraphDecisionInput], Field(min_length=1)]
RevisionInput = Annotated[int, Field(ge=0)]


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
    elif (
        "not ready for delegation" in lowered
        or "only accepted while graph_state" in lowered
        or "reconciliation cannot run while" in lowered
    ):
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
async def start_graph(graph: TaskGraphInput) -> dict[str, Any]:
    """Create a validated TaskGraph run and return the initial outer-loop snapshot.

    `graph.nodes[*].task_packet` uses the existing canonical TaskPacket fields. Graph
    orchestration metadata (`node_id`, `repository`, `route`, `kind`, `depends_on`) stays
    outside TaskPacket. The repository names are validated against the current repos.yaml.
    """
    authored = task_graph_from_payload(graph.model_dump(exclude_none=True))
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
async def reconcile_graph(
    graph_run_id: str,
    graph: TaskGraphInput,
    expected_revision: RevisionInput,
) -> dict[str, Any]:
    """Replace the authored TaskGraph and reconcile existing runtime state.

    QiQi must author the complete next graph explicitly; runtime never infers nodes or
    dependencies from child prose. Unchanged independent nodes preserve accepted/reviewable
    state and evidence. New or materially changed nodes reset to pending, and invalidation
    propagates to descendants that depended on changed work. Removed nodes are retired
    without deleting attempt/session/result history. A Work Item revision is reconciled by
    updating only the TaskPackets/topology QiQi judges materially affected.
    """
    authored = task_graph_from_payload(graph.model_dump(exclude_none=True))
    registry = _load_repo_registry()
    try:
        return _graph_runtime.reconcile_graph(
            graph_run_id,
            authored,
            repository_names=registry.keys(),
            expected_revision=expected_revision,
        )
    except RuntimeError as exc:
        if "stale graph snapshot revision" not in str(exc).lower():
            raise
        raise ToolError(
            "code=graph_revision_conflict; "
            f"{exc}; "
            "action=call get_graph, review the current revision, then resubmit "
            "reconcile_graph with the authored replacement graph and refreshed "
            "expected_revision"
        ) from exc


@mcp.tool()
@_graph_public_errors
async def delegate_next(graph_run_id: str) -> dict[str, Any]:
    """Execute one deterministic conflict-free runnable wave and return control to QiQi.

    Phase 9 may execute multiple independent repositories concurrently in the same wave.
    Pending selective retries are prioritized before unrelated fresh work; each retry still
    uses a fresh TaskPacket snapshot and either STARTs fresh or RESUMEs the exact prior
    native session selected by QiQi. Until repo-local worktree isolation exists, at most one
    node per repository enters a wave. Existing delegate_repo_task repository/session
    ownership remains the authoritative runtime conflict guard.
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
    decisions: DecisionListInput,
    expected_revision: RevisionInput,
) -> dict[str, Any]:
    """Apply QiQi per-node semantic review decisions and recompute graph state.

    Supported actions are `accept`, `retry`, `replan`, and `block`. For `retry`, QiQi may
    set `resume_session=true` to continue the exact prior native session and may provide
    `feedback=[...]`; feedback is carried into a fresh TaskPacket snapshot through the
    existing context.claims_to_investigate contract. Omit/false `resume_session` for a
    fresh START. Decisions remain per-node even when several nodes settled in one Phase-9
    wave. `replan` fails closed until QiQi calls `reconcile_graph` with an explicitly
    authored replacement graph and the current revision.
    """
    return _graph_runtime.submit_decisions(
        graph_run_id,
        decisions_from_payload(
            [decision.model_dump(exclude_none=True, exclude_defaults=True) for decision in decisions]
        ),
        expected_revision=expected_revision,
    )


if __name__ == "__main__":
    mcp.run()
