#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Annotated, Literal

from mcp.server import MCPServer
from pydantic import Field

from artifact_templates import load_artifact_templates, template_guidance_for
from artifacts import (
    ARTIFACT_CHUNK_MAX_BYTES,
    ARTIFACT_LIST_MAX,
    ARTIFACT_READ_MAX_BYTES,
    ARTIFACT_READ_MIN_BYTES,
    ArtifactConflictError,
    ArtifactNotFoundError,
    append_artifact,
    create_artifact,
    finalize_artifact,
    get_artifact,
    list_artifacts,
    read_artifact_section,
)
from core import (
    HISTORY_LIMIT_MAX,
    ConflictError,
    NotFoundError,
    ValidationError,
    WorkItemError,
    create_work_item,
    get_work_item_snapshot,
    list_work_items,
    new_document,
    read_work_item_history,
    resolve_db_path,
    update_work_item,
)
from models import (
    HistoryCollection,
    HistoryStatus,
    WorkItemHistoryPage,
    WorkItemPatch,
    WorkItemSnapshot,
    WorkItemStatus,
)

ArtifactType = Literal["intake", "investigation", "plan", "review", "report"]
WorkItemId = Annotated[
    str,
    Field(
        min_length=3,
        max_length=256,
        pattern=r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="Canonical Work Item id in <source>:<external-id> form, for example redmine:116655.",
    ),
]
ArtifactId = Annotated[
    str,
    Field(
        min_length=3,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="Artifact id in <type>:<id> form, for example report:1.",
    ),
]
SectionId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Lowercase artifact section id using letters, digits, _ or -.",
    ),
]
Revision = Annotated[int, Field(ge=1)]
ListLimit = Annotated[int, Field(ge=1, le=200)]
HistoryReadLimit = Annotated[int, Field(ge=1, le=HISTORY_LIMIT_MAX)]
ArtifactListLimit = Annotated[int, Field(ge=1, le=ARTIFACT_LIST_MAX)]
ArtifactReadLimit = Annotated[int, Field(ge=ARTIFACT_READ_MIN_BYTES, le=ARTIFACT_READ_MAX_BYTES)]
ArtifactContent = Annotated[
    str,
    Field(
        min_length=1,
        max_length=ARTIFACT_CHUNK_MAX_BYTES,
        description=(
            "One artifact content chunk. Server limit is 32000 UTF-8 bytes, not characters; "
            "split larger content into multiple append calls."
        ),
    ),
]

ARTIFACT_TEMPLATES = load_artifact_templates()


def _db_path() -> Path:
    raw = os.environ.get("WORK_ITEM_DB_PATH", "").strip()
    if not raw:
        raise RuntimeError("WORK_ITEM_DB_PATH must point to the global Work Item SQLite database")
    return resolve_db_path(raw)


def _not_found_result(item_id: str, exc: NotFoundError) -> dict[str, Any]:
    return {
        "found": False,
        "id": item_id,
        "error": {
            "code": "work_item_not_found",
            "message": str(exc),
            "action": "verify the canonical task id or create the Work Item",
        },
    }


def _work_item_update_error_result(
    item_id: str,
    exc: ValidationError | ConflictError | NotFoundError,
) -> dict[str, Any]:
    if isinstance(exc, ValidationError):
        return {
            "updated": False,
            "id": item_id,
            "error": {
                "code": "work_item_validation",
                "message": str(exc),
                "action": (
                    "fix the patch to match the WorkItemPatch schema; historical semantic arrays are "
                    "full replacements, so read the complete target collection with "
                    "work_item_history_read before replacing it"
                ),
            },
        }
    if isinstance(exc, ConflictError):
        return {
            "updated": False,
            "id": item_id,
            "error": {
                "code": "revision_conflict",
                "message": str(exc),
                "action": (
                    "call work_item_get again for the current revision; if retrying a full historical "
                    "array replacement, reread that complete collection with work_item_history_read, "
                    "then reconcile and retry with the exact current revision"
                ),
            },
        }
    return {
        "updated": False,
        "id": item_id,
        "error": {
            "code": "work_item_not_found",
            "message": str(exc),
            "action": "verify the canonical task id or let QiQi create it",
        },
    }


def _raise_actionable_error(exc: WorkItemError) -> None:
    if isinstance(exc, ArtifactConflictError):
        message = str(exc)
        if "artifact revision conflict" in message:
            if "cursor revision" in message:
                raise ValueError(
                    "code=artifact_revision_conflict; "
                    f"{message}; action=call work_item_artifact_get again and restart "
                    "that section read without the stale cursor"
                ) from exc
            raise ValueError(
                "code=artifact_revision_conflict; "
                f"{message}; action=call work_item_artifact_get again and retry with its exact revision"
            ) from exc
        raise ValueError(f"code=artifact_conflict; {message}") from exc
    if isinstance(exc, ArtifactNotFoundError):
        raise ValueError(
            f"code=artifact_not_found; {exc}; action=call work_item_artifact_list/get to verify artifact identity"
        ) from exc
    if isinstance(exc, ConflictError):
        message = str(exc)
        if "history revision conflict" in message:
            raise ValueError(
                "code=history_revision_conflict; "
                f"{message}; action=restart work_item_history_read from the current revision without the stale cursor"
            ) from exc
        if "revision conflict" in message:
            raise ValueError(
                "code=revision_conflict; "
                f"{message}; action=call work_item_get again; if reconciling a historical full-array "
                "replacement, reread that complete collection with work_item_history_read before retrying"
            ) from exc
        raise ValueError(f"code=work_item_conflict; {message}") from exc
    if isinstance(exc, NotFoundError):
        raise ValueError(
            f"code=work_item_not_found; {exc}; action=verify the canonical task id or let QiQi create it"
        ) from exc
    if isinstance(exc, ValidationError):
        raise ValueError(f"code=work_item_validation; {exc}") from exc
    raise RuntimeError(f"code=work_item_store_error; {exc}") from exc


def _with_artifacts(item: dict[str, Any]) -> dict[str, Any]:
    result = dict(item)
    result["artifacts"] = list_artifacts(_db_path(), item["id"], limit=ARTIFACT_LIST_MAX)
    return result


def _with_template_guidance(artifact: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    result = dict(artifact)
    result["template_guidance"] = template_guidance_for(ARTIFACT_TEMPLATES, artifact_type)
    return result


mcp = MCPServer(
    "Global Work Item",
    instructions=(
        "Canonical mutable product-task state shared by QiQi and repository execution agents. "
        "When a TaskPacket identifies a Work Item, call work_item_get before substantive task work. "
        "work_item_get is a bounded current-state projection: it returns current requirements, current "
        "repo state, open questions/blockers, active decisions, pending handoffs, next actions, compact "
        "history counts and thin artifact metadata; it intentionally does not hydrate resolved, "
        "superseded or checkpoint history. Use work_item_history_read only when provenance/history is "
        "material to the current decision or when a legacy full-array mutation requires the complete "
        "target historical collection. Each history call reads exactly one semantic collection and its "
        "opaque cursor is bound to the whole Work Item revision plus collection and filters; if the "
        "Work Item changes between pages, restart the history read rather than mixing revisions. QiQi "
        "owns global orchestration state such as overall status/phase, repo assignment, next actions and "
        "task completion. A repository agent must only execute work in its current Git root and only "
        "update evidence/state it actually established for that repository, plus blockers, open questions, "
        "checkpoints or handoffs it discovered. Cross-repo remaining work is recorded and returned to QiQi; "
        "child agents must not modify sibling repositories. Work Item state is task truth, not reusable "
        "system knowledge and not runtime session state. Updates use optimistic concurrency: always pass "
        "the exact revision returned by work_item_get/list and reread on conflict. work_item_update exposes "
        "a typed WorkItemPatch. Use canonical record objects for questions, decisions, requirement/scope "
        "changes, blockers, handoffs, next actions and checkpoints; do not encode those semantic collections "
        "as plain strings or generic activity logs. Historical semantic arrays still replace atomically "
        "until incremental mutations are available, so never construct those arrays from the bounded "
        "snapshot; use work_item_history_read to hydrate the complete target collection first. A missing "
        "work_item_get is normal startup control flow and returns found=false so QiQi can create the item. "
        "Optional task artifacts provide progressive-disclosure detail for explicit user-requested intake, "
        "investigation, plan, review or report material. Do not create artifacts merely as normal progress "
        "bookkeeping. work_item_get returns only thin artifact metadata. Full artifact content must be read "
        "by section through bounded work_item_artifact_read calls. Artifact writes are independently "
        "revisioned, append-only while draft, limited to 32000 UTF-8 bytes per call, and become immutable "
        "after finalize. Artifact read cursors are bound to one artifact revision; restart a section read "
        "if the artifact changes between pages. Artifact mutations never advance the Work Item revision. "
        "If artifact detail conflicts with newer canonical Work Item state, the Work Item wins."
    ),
)


@mcp.tool()
async def work_item_get(id: WorkItemId) -> dict[str, Any]:
    """Return a bounded current-state Work Item snapshot plus thin artifact metadata."""
    try:
        result = _with_artifacts(get_work_item_snapshot(_db_path(), id))
        return WorkItemSnapshot.model_validate(result).model_dump(mode="python", by_alias=True)
    except NotFoundError as exc:
        return _not_found_result(id, exc)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_history_read(
    id: WorkItemId,
    collection: HistoryCollection,
    status: HistoryStatus | None = None,
    repository: str | None = None,
    cursor: str | None = None,
    limit: HistoryReadLimit = 50,
) -> dict[str, Any]:
    """Read one bounded canonical history collection page bound to one Work Item revision.

    `status` is valid only for lifecycle collections. `repository` is valid only for checkpoints.
    A cursor is opaque and bound to revision, collection and filters. If the Work Item revision
    changes between pages, restart without the stale cursor.
    """
    try:
        result = read_work_item_history(
            _db_path(),
            id,
            collection=collection,
            status=status,
            repository=repository,
            cursor=cursor,
            limit=limit,
        )
        return WorkItemHistoryPage.model_validate(result).model_dump(mode="python", by_alias=True)
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
        return list_work_items(_db_path(), status=status, repository=repository, limit=limit)
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
    changes: WorkItemPatch,
) -> dict[str, Any]:
    """Atomically merge a typed WorkItemPatch using exact optimistic revision control.

    Nested objects merge. Historical semantic arrays are full replacements until incremental
    mutations are available. Never rebuild them from work_item_get because that surface is a
    current-state projection; read the complete target collection with work_item_history_read,
    reconcile the intended replacement, then update using that exact whole Work Item revision.
    `artifacts` is derived metadata reserved by core and cannot be persisted.
    """
    try:
        patch = changes.to_merge_patch()
        return update_work_item(_db_path(), id, expected_revision, patch)
    except (ValidationError, ConflictError, NotFoundError) as exc:
        return _work_item_update_error_result(id, exc)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_list(
    id: WorkItemId,
    type: ArtifactType | None = None,
    limit: ArtifactListLimit = 50,
) -> list[dict[str, Any]]:
    """List thin artifact metadata for a Work Item without returning artifact bodies."""
    try:
        return list_artifacts(_db_path(), id, artifact_type=type, limit=limit)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_get(id: WorkItemId, artifact_id: ArtifactId) -> dict[str, Any]:
    """Return artifact metadata and ordered section manifest; never returns section content."""
    try:
        return get_artifact(_db_path(), id, artifact_id)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_create(
    id: WorkItemId,
    type: ArtifactType,
    title: str,
    summary: str,
    based_on_work_item_revision: Revision,
    artifact_id: ArtifactId | None = None,
) -> dict[str, Any]:
    """Create a draft artifact and return optional advisory section template guidance.

    Template guidance is loaded once at MCP startup, is not persisted, and does not enforce
    section presence, order, titles, or exclusivity. Callers may omit, reorder, or add sections.
    """
    try:
        artifact = create_artifact(
            _db_path(),
            id,
            artifact_type=type,
            title=title,
            summary=summary,
            based_on_work_item_revision=based_on_work_item_revision,
            artifact_id=artifact_id,
        )
        return _with_template_guidance(artifact, type)
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_append(
    id: WorkItemId,
    artifact_id: ArtifactId,
    expected_artifact_revision: Revision,
    section_id: SectionId,
    content: ArtifactContent,
    section_title: str | None = None,
) -> dict[str, Any]:
    """Append one bounded UTF-8 chunk to a draft artifact section and return the new manifest."""
    try:
        return append_artifact(
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
    cursor: str | None = None,
    limit_bytes: ArtifactReadLimit = ARTIFACT_READ_MAX_BYTES,
) -> dict[str, Any]:
    """Read 4..32000 UTF-8 bytes from one artifact revision/section using a continuation cursor."""
    try:
        return read_artifact_section(
            _db_path(),
            id,
            artifact_id,
            section_id=section_id,
            cursor=cursor,
            limit_bytes=limit_bytes,
        )
    except WorkItemError as exc:
        _raise_actionable_error(exc)


@mcp.tool()
async def work_item_artifact_finalize(
    id: WorkItemId,
    artifact_id: ArtifactId,
    expected_artifact_revision: Revision,
) -> dict[str, Any]:
    """Finalize a non-empty draft artifact. Completed artifacts are immutable in the MVP."""
    try:
        return finalize_artifact(
            _db_path(),
            id,
            artifact_id,
            expected_artifact_revision=expected_artifact_revision,
        )
    except WorkItemError as exc:
        _raise_actionable_error(exc)


if __name__ == "__main__":
    mcp.run()
