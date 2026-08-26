#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Annotated, Literal

from mcp.server import MCPServer
from pydantic import Field

from artifacts import (
    ARTIFACT_APPEND_MAX_BYTES,
    ARTIFACT_INDEX_LIMIT,
    ARTIFACT_LIST_LIMIT_MAX,
    ARTIFACT_READ_MAX_CHUNKS,
    ArtifactConflictError,
    ArtifactNotFoundError,
    append_artifact_chunk,
    create_artifact,
    finalize_artifact,
    get_artifact,
    get_artifact_index,
    list_artifacts,
    read_artifact_section,
)
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
ArtifactType = Literal["intake", "investigation", "plan", "review", "report"]
WorkItemId = Annotated[str, Field(min_length=3, max_length=256)]
ArtifactId = Annotated[str, Field(min_length=3, max_length=256)]
SectionId = Annotated[str, Field(min_length=1, max_length=128)]
Revision = Annotated[int, Field(ge=1)]
ListLimit = Annotated[int, Field(ge=1, le=200)]
ArtifactListLimit = Annotated[int, Field(ge=1, le=ARTIFACT_LIST_LIMIT_MAX)]
ArtifactReadCursor = Annotated[int, Field(ge=0)]
ArtifactReadLimit = Annotated[int, Field(ge=1, le=ARTIFACT_READ_MAX_CHUNKS)]
ArtifactTitle = Annotated[str, Field(min_length=1, max_length=1_000)]
ArtifactSummary = Annotated[str, Field(max_length=2_000)]
ArtifactSectionTitle = Annotated[str, Field(min_length=1, max_length=500)]
ArtifactChunk = Annotated[str, Field(min_length=1, max_length=ARTIFACT_APPEND_MAX_BYTES)]

RESERVED_WORK_ITEM_VIEW_FIELDS = {
    "artifacts",
    "artifact_count",
    "artifacts_truncated",
}


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
    if isinstance(exc, ArtifactConflictError):
        message = str(exc)
        if "artifact revision conflict" in message:
            raise ValueError(
                "code=artifact_revision_conflict; "
                f"{message}; action=call work_item_artifact_get again, reconcile the artifact "
                "manifest, then retry with its exact artifact revision"
            ) from exc
        raise ValueError(f"code=artifact_conflict; {message}") from exc
    if isinstance(exc, ConflictError):
        message = str(exc)
        if "revision conflict" in message:
            raise ValueError(
                "code=revision_conflict; "
                f"{message}; action=call work_item_get again, reconcile against the current "
                "document, then retry with its exact revision"
            ) from exc
        raise ValueError(f"code=work_item_conflict; {message}") from exc
    if isinstance(exc, ArtifactNotFoundError):
        raise ValueError(
            f"code=artifact_not_found; {exc}; "
            "action=call work_item_artifact_list/get and verify the artifact/section id"
        ) from exc
    if isinstance(exc, NotFoundError):
        raise ValueError(
            f"code=work_item_not_found; {exc}; "
            "action=verify the canonical task id or let QiQi create it"
        ) from exc
    if isinstance(exc, ValidationError):
        message = str(exc)
        if "artifact chunk exceeds" in message:
            raise ValueError(
                f"code=artifact_chunk_too_large; {message}; "
                f"action=split content into chunks no larger than {ARTIFACT_APPEND_MAX_BYTES} UTF-8 bytes"
            ) from exc
        raise ValueError(f"code=work_item_validation; {message}") from exc
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
        "normal startup control flow and returns found=false so QiQi can create the item. "
        "Task artifacts are optional detailed material, never canonical task state. Do not create "
        "an intake/investigation/plan/review/report artifact unless the user explicitly requests "
        "that detailed artifact or explicitly requests a task report/review that requires one. "
        "Use progressive disclosure: work_item_get contains only a bounded thin artifact index; "
        "artifact_get returns metadata plus section manifest only; artifact_read returns at most "
        f"{ARTIFACT_READ_MAX_CHUNKS} stored chunks and each append is limited to "
        f"{ARTIFACT_APPEND_MAX_BYTES} UTF-8 bytes. Artifact revisions are independent from Work "
        "Item revisions. If artifact content conflicts with newer canonical Work Item state, the "
        "Work Item wins; based_on_work_item_revision tells which task snapshot the artifact used."
    ),
)


@mcp.tool()
async def work_item_get(id: WorkItemId) -> dict[str, Any]:
    """Return canonical task state plus a bounded thin artifact index; never artifact bodies."""
    try:
        db = _db_path()
        result = get_work_item(db, id)
        artifact_index = get_artifact_index(db, id, limit=ARTIFACT_INDEX_LIMIT)
        result["artifacts"] = artifact_index["items"]
        result["artifact_count"] = artifact_index["count"]
        result["artifacts_truncated"] = artifact_index["truncated"]
        return result
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
    """Atomically merge semantic task changes using exact Work Item revision control.

    Nested objects merge. Arrays are replaced as a whole. Artifact index fields returned by
    work_item_get are read-only derived views and cannot be persisted through this tool.
    """
    try:
        reserved = sorted(RESERVED_WORK_ITEM_VIEW_FIELDS.intersection(changes))
        if reserved:
            raise ValidationError(
                "changes must not modify derived artifact view fields: " + ", ".join(reserved)
            )
        return update_work_item(_db_path(), id, expected_revision, changes)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_list(
    id: WorkItemId,
    type: ArtifactType | None = None,
    limit: ArtifactListLimit = 50,
) -> list[dict[str, Any]]:
    """List thin artifact metadata for one Work Item; never returns section body content."""
    try:
        return list_artifacts(_db_path(), id, artifact_type=type, limit=limit)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_get(
    id: WorkItemId,
    artifact_id: ArtifactId,
) -> dict[str, Any]:
    """Return artifact metadata and ordered section manifest only; never full section bodies."""
    try:
        return get_artifact(_db_path(), id, artifact_id)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_create(
    id: WorkItemId,
    type: ArtifactType,
    title: ArtifactTitle,
    based_on_work_item_revision: Revision,
    summary: ArtifactSummary = "",
    artifact_id: ArtifactId | None = None,
) -> dict[str, Any]:
    """Create optional artifact metadata in draft state, pinned to the exact current Work Item revision.

    This tool creates no body content. Use only when the user explicitly requested this detailed
    artifact/report. If artifact_id is omitted, the server allocates type:1, type:2, ... atomically.
    """
    try:
        return create_artifact(
            _db_path(),
            id,
            artifact_type=type,
            title=title,
            summary=summary,
            based_on_work_item_revision=based_on_work_item_revision,
            artifact_id=artifact_id,
        )
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_append(
    id: WorkItemId,
    artifact_id: ArtifactId,
    expected_artifact_revision: Revision,
    section_id: SectionId,
    content: ArtifactChunk,
    section_title: ArtifactSectionTitle | None = None,
) -> dict[str, Any]:
    """Append one bounded UTF-8 chunk to a draft artifact section using artifact revision control.

    The first chunk of a new section must provide section_title. Later chunks may omit it. A
    completed artifact is immutable. Large content must be split across multiple append calls.
    """
    try:
        return append_artifact_chunk(
            _db_path(),
            id,
            artifact_id,
            expected_artifact_revision=expected_artifact_revision,
            section_id=section_id,
            section_title=section_title,
            content=content,
        )
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_read(
    id: WorkItemId,
    artifact_id: ArtifactId,
    section_id: SectionId,
    cursor: ArtifactReadCursor = 0,
    limit_chunks: ArtifactReadLimit = 1,
) -> dict[str, Any]:
    """Read one bounded window of a section by chunk cursor; repeat with next_cursor when needed."""
    try:
        return read_artifact_section(
            _db_path(),
            id,
            artifact_id,
            section_id,
            cursor=cursor,
            limit_chunks=limit_chunks,
        )
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_finalize(
    id: WorkItemId,
    artifact_id: ArtifactId,
    expected_artifact_revision: Revision,
    summary: ArtifactSummary | None = None,
) -> dict[str, Any]:
    """Finalize a non-empty draft artifact as complete using its exact independent revision."""
    try:
        return finalize_artifact(
            _db_path(),
            id,
            artifact_id,
            expected_artifact_revision=expected_artifact_revision,
            summary=summary,
        )
    except WorkItemError as exc:
        _raise_actionable_error(exc)


if __name__ == "__main__":
    mcp.run()
