#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from mcp.server import MCPServer

from contracts import (
    KnowledgeReadResult,
    KnowledgeSearchContext,
    KnowledgeSearchResult,
    KnowledgeWriteResult,
    ReadIds,
    SearchKeywords,
    SearchLimit,
    WriteEntries,
)
from core import (
    DEFAULT_SEARCH_RESULTS,
    ConflictError,
    KnowledgeError,
    ValidationError,
    read_knowledge,
    resolve_store_root,
    search_knowledge,
    write_knowledge,
)


def _store_root() -> Path:
    raw = os.environ.get("KNOWLEDGE_STORE_ROOT", "").strip()
    if not raw:
        raise RuntimeError("KNOWLEDGE_STORE_ROOT must point to the shared knowledge store")
    return resolve_store_root(raw)


def _raise_actionable_error(exc: KnowledgeError) -> None:
    message = str(exc)
    lowered = message.lower()
    if isinstance(exc, ConflictError):
        if "revision conflict" in lowered or "changed during update" in lowered:
            raise ValueError(
                "code=revision_conflict; "
                f"{message}; action=call knowledge_read again for the exact knowledge id, "
                "re-distill against the returned content/revision, then retry update with "
                "that exact expected_revision"
            ) from exc
        if "already exists or collides" in lowered:
            raise ValueError(
                "code=create_conflict; "
                f"{message}; action=call knowledge_search for the concept, hydrate the "
                "existing item with knowledge_read, then update with exact id + "
                "expected_revision instead of retrying create"
            ) from exc
        if "does not exist for update" in lowered:
            raise ValueError(
                "code=missing_update_target; "
                f"{message}; action=call knowledge_search again; create only if no "
                "existing knowledge covers the concept"
            ) from exc
        if "index is stale" in lowered or "index points to a different id" in lowered:
            raise ValueError(
                "code=stale_index; "
                f"{message}; action=do not retry unchanged; the store operator must run "
                "knowledge reindex/check before search/read can be trusted"
            ) from exc
        raise ValueError(f"code=knowledge_conflict; {message}") from exc
    if isinstance(exc, ValidationError):
        raise ValueError(
            "code=knowledge_validation; "
            f"{message}; action=inspect the typed tool schema and correct the payload "
            "instead of guessing filesystem fields or flattening nested routing metadata"
        ) from exc
    if "knowledge id does not exist" in lowered:
        raise ValueError(
            "code=missing_read_target; "
            f"{message}; action=call knowledge_search again and read only exact returned ids"
        ) from exc
    raise RuntimeError(f"code=knowledge_store_error; {message}") from exc


mcp = MCPServer(
    "Shared Knowledge",
    instructions=(
        "Repository-independent durable knowledge service with progressive disclosure. "
        "Use knowledge_search after understanding the current work; search returns bounded "
        "routing decision cards, not evidence sufficient for implementation or update. "
        "Hydrate only the one or two selected exact ids with knowledge_read before relying "
        "on durable content. knowledge_read returns the exact revision and full semantic "
        "payload required for safe updates; search intentionally does not return revision. "
        "Before knowledge_write, apply the installed knowledge-distill skill. Create omits "
        "id/revision; update uses exact id + expected_revision from knowledge_read. Callers "
        "never choose knowledge filesystem paths or add a language field."
    ),
)


@mcp.tool()
async def knowledge_search(
    keywords: SearchKeywords,
    context: KnowledgeSearchContext | None = None,
    limit: SearchLimit = DEFAULT_SEARCH_RESULTS,
) -> KnowledgeSearchResult:
    """Discover relevant knowledge as bounded routing cards; hydrate selected ids separately."""
    try:
        result = search_knowledge(
            _store_root(),
            keywords,
            context.model_dump(exclude_none=True) if context is not None else None,
            limit,
        )
    except KnowledgeError as exc:
        _raise_actionable_error(exc)
    return KnowledgeSearchResult.model_validate(result)


@mcp.tool()
async def knowledge_read(ids: ReadIds) -> KnowledgeReadResult:
    """Hydrate one or two exact knowledge ids with full semantic content and revision."""
    try:
        result = read_knowledge(_store_root(), ids)
    except KnowledgeError as exc:
        _raise_actionable_error(exc)
    return KnowledgeReadResult.model_validate(result)


@mcp.tool()
async def knowledge_write(entries: WriteEntries) -> KnowledgeWriteResult:
    """Persist verified durable knowledge after applying the installed knowledge-distill skill.

    Search the candidate concept before create/update. Create omits id/revision. Update
    requires the exact id + expected_revision from a full knowledge_read. Keep routing
    nested, provenance non-empty, and filesystem-owned/language fields out of the payload.
    Pass entries=[] only when policy required a final review and no durable candidate remains.
    """
    payload = [entry.model_dump(exclude_none=True) for entry in entries]
    try:
        result = write_knowledge(_store_root(), payload)
    except KnowledgeError as exc:
        _raise_actionable_error(exc)
    return KnowledgeWriteResult.model_validate(result)


if __name__ == "__main__":
    mcp.run()
