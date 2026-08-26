#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Annotated, Literal

from mcp.server import MCPServer
from pydantic import Field

from core import (
    ConflictError,
    NotFoundError,
    ValidationError,
    WorkItemError,
    create_work_item,
    get_work_item,
    list_work_items,
    new_document,
    resolve_db_path,
    update_work_item,
)

WorkItemStatus = Literal["active", "waiting", "blocked", "done", "cancelled"]
WorkItemId = Annotated[str, Field(min_length=3, max_length=256)]
Revision = Annotated[int, Field(ge=1)]
ListLimit = Annotated[int, Field(ge=1, le=200)]


def _db_path() -> Path:
    raw = os.environ.get("WORK_ITEM_DB_PATH", "").strip()
    if not raw:
        raise RuntimeError(
            "WORK_ITEM_DB_PATH must point to the global Work Item SQLite database"
        )
    return resolve_db_path(raw)


def _not_found_result(item_id: str, exc: NotFoundError) -> dict[str, Any]:
    """Return a normal control-flow result for an absent canonical Work Item."""
    return {
        "found": False,
        "id": item_id,
        "error": {
            "code": "work_item_not_found",
            "message": str(exc),
            "action": "verify the canonical task id or create the Work Item",
        },
    }


def _raise_actionable_error(exc: WorkItemError) -> None:
    if isinstance(exc, ConflictError):
        message = str(exc)
        if "revision conflict" in message:
            raise ValueError(
                "code=revision_conflict; "
                f"{message}; action=call work_item_get again, reconcile against the current "
                "document, then retry with its exact revision"
            ) from exc
        raise ValueError(f"code=work_item_conflict; {message}") from exc
    if isinstance(exc, NotFoundError):
        raise ValueError(
            f"code=work_item_not_found; {exc}; "
            "action=verify the canonical task id or let QiQi create it"
        ) from exc
    if isinstance(exc, ValidationError):
        raise ValueError(f"code=work_item_validation; {exc}") from exc
    raise RuntimeError(f"code=work_item_store_error; {exc}") from exc


mcp = MCPServer(
    "Global Work Item",
    instructions=(
        "Canonical mutable product-task state shared by QiQi and repository execution agents. "
        "When a TaskPacket identifies a Work Item, read it before substantive task work so "
        "continuity does not depend on QiQi repeating prior history. QiQi owns global "
        "orchestration state such as overall status/phase, repo assignment, next actions and "
        "task completion. A repository agent may read the whole Work Item for context but must "
        "only execute work in its current Git root and only update evidence/state it actually "
        "established for that repository, plus blockers, open questions, checkpoints or handoffs "
        "it discovered. Cross-repo remaining work is recorded and returned to QiQi; child agents "
        "must not modify sibling repositories. Work Item state is task truth, not reusable system "
        "knowledge and not runtime session state. Updates use optimistic concurrency: always pass "
        "the exact revision returned by work_item_get/list and reread on conflict. The changes "
        "object uses JSON merge-patch semantics: nested objects merge, arrays replace atomically, "
        "and null removes a field; required fields cannot be removed. A missing work_item_get is "
        "normal startup control flow and returns found=false so QiQi can create the item."
    ),
)


@mcp.tool()
async def work_item_get(id: WorkItemId) -> dict[str, Any]:
    """Return the complete canonical Work Item; if absent, return found=false without tool failure."""
    try:
        return get_work_item(_db_path(), id)
    except NotFoundError as exc:
        return _not_found_result(id, exc)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_list(
    status: WorkItemStatus | None = None,
    repository: str | None = None,
    limit: ListLimit = 50,
) -> list[dict[str, Any]]:
    """List compact Work Item summaries, optionally filtered by status or involved repository."""
    try:
        return list_work_items(
            _db_path(), status=status, repository=repository, limit=limit
        )
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_create(
    id: WorkItemId,
    title: str,
    summary: str = "",
    status: WorkItemStatus = "active",
    phase: str = "investigation",
    current_requirements: list[str] | None = None,
    repositories: list[str] | None = None,
) -> dict[str, Any]:
    """Create one canonical Work Item. QiQi normally owns creation and initial repo assignment."""
    try:
        document = new_document(
            item_id=id,
            title=title,
            summary=summary,
            status=status,
            phase=phase,
            current_requirements=current_requirements,
            repositories=repositories,
        )
        return create_work_item(_db_path(), document)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_update(
    id: WorkItemId,
    expected_revision: Revision,
    changes: dict[str, Any],
) -> dict[str, Any]:
    """Atomically merge changes into a Work Item using exact optimistic revision control.

    Nested objects merge. Arrays are replaced as a whole, which keeps MVP semantics explicit:
    read the current document, reconcile the full intended array value, then update using that
    exact revision. Do not use this tool as an activity transcript; persist current requirements,
    material questions/decisions/requirement changes, repo evidence, blockers, handoffs, next
    actions and meaningful checkpoints only.
    """
    try:
        return update_work_item(_db_path(), id, expected_revision, changes)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


if __name__ == "__main__":
    mcp.run()
