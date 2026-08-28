#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from mcp.server import MCPServer

from contracts import (
    KnowledgeId,
    KnowledgeReadResult,
    KnowledgeSearchContext,
    KnowledgeSearchResult,
    KnowledgeWriteResult,
    ReadIds,
    Revision,
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
from partial_contracts import (
    KnowledgeMetadataReadResult,
    KnowledgePatch,
    KnowledgeSectionReadResult,
    SectionId,
)
from partial_update import update_knowledge
from sections import SectionError, parse_sections, read_section, section_summaries


def _store_root() -> Path:
    raw = os.environ.get("KNOWLEDGE_STORE_ROOT", "").strip()
    if not raw:
        raise RuntimeError("KNOWLEDGE_STORE_ROOT must point to the shared knowledge store")
    return resolve_store_root(raw)


def _raise_actionable_error(exc: KnowledgeError) -> None:
    message = str(exc)
    lowered = message.lower()
    if "knowledge section does not exist" in lowered:
        raise ValueError(
            "code=missing_section; "
            f"{message}; action=call knowledge_read_metadata for the exact id, choose an "
            "existing returned section id, then retry without inventing or implicitly "
            "creating a section"
        ) from exc
    if isinstance(exc, ConflictError):
        if "revision conflict" in lowered or "changed during update" in lowered:
            raise ValueError(
                "code=revision_conflict; "
                f"{message}; action=read the exact knowledge target again, reconcile "
                "against the returned revision, then retry with that exact "
                "expected_revision. Use knowledge_read_metadata for metadata-only work, "
                "knowledge_read_section for one marked section, or knowledge_read when "
                "the full semantic content is required"
            ) from exc
        if "already exists or collides" in lowered:
            raise ValueError(
                "code=create_conflict; "
                f"{message}; action=call knowledge_search for the concept, read the "
                "existing item, then update with exact id + expected_revision instead "
                "of retrying create"
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
            "instead of guessing filesystem fields, flattening routing metadata, or "
            "editing semantic section markers manually"
        ) from exc
    if "knowledge id does not exist" in lowered:
        raise ValueError(
            "code=missing_read_target; "
            f"{message}; action=call knowledge_search again and read only exact returned ids"
        ) from exc
    raise RuntimeError(f"code=knowledge_store_error; {message}") from exc


def _section_validation_error(exc: SectionError) -> ValidationError:
    return ValidationError(str(exc))


mcp = MCPServer(
    "Shared Knowledge",
    instructions=(
        "Repository-independent durable knowledge service with progressive disclosure. "
        "Use knowledge_search after understanding the current work; search returns bounded "
        "routing decision cards, not evidence sufficient for implementation or update, and "
        "intentionally does not return revision. Read only the exact selected target at the "
        "smallest semantic scope required: knowledge_read for the full document, "
        "knowledge_read_metadata for metadata/provenance/revision without content, or "
        "knowledge_read_section for one existing stable marked section. Before "
        "knowledge_write or knowledge_update, apply the installed knowledge-distill skill. "
        "Create uses knowledge_write and omits id/revision. Full-document update remains "
        "supported by knowledge_write; scoped mutations use knowledge_update with exact id "
        "+ expected_revision. Callers never choose filesystem paths, add a language field, "
        "or invent section ids."
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
        for item in result["results"]:
            parse_sections(item["content"])
    except SectionError as exc:
        _raise_actionable_error(_section_validation_error(exc))
    except KnowledgeError as exc:
        _raise_actionable_error(exc)
    return KnowledgeReadResult.model_validate(result)


@mcp.tool()
async def knowledge_read_metadata(ids: ReadIds) -> KnowledgeMetadataReadResult:
    """Read exact knowledge metadata, provenance, section index, and revision without content."""
    try:
        hydrated = read_knowledge(_store_root(), ids)
        results = []
        for item in hydrated["results"]:
            results.append(
                {
                    "id": item["id"],
                    "revision": item["revision"],
                    "canonical_name": item["canonical_name"],
                    "title": item["title"],
                    "scope": item["scope"],
                    "routing": item["routing"],
                    "sources": item["sources"],
                    "sections": section_summaries(item["content"]),
                }
            )
    except SectionError as exc:
        _raise_actionable_error(_section_validation_error(exc))
    except KnowledgeError as exc:
        _raise_actionable_error(exc)
    return KnowledgeMetadataReadResult.model_validate({"results": results})


@mcp.tool()
async def knowledge_read_section(
    id: KnowledgeId,
    section_id: SectionId,
) -> KnowledgeSectionReadResult:
    """Read one existing stable marked semantic section plus its whole-document revision."""
    try:
        item = read_knowledge(_store_root(), [id])["results"][0]
        section = read_section(item["content"], section_id)
        result = {
            "id": item["id"],
            "revision": item["revision"],
            **section,
        }
    except SectionError as exc:
        message = str(exc)
        error: KnowledgeError
        if "does not exist" in message:
            error = ValidationError(message)
        else:
            error = _section_validation_error(exc)
        _raise_actionable_error(error)
    except KnowledgeError as exc:
        _raise_actionable_error(exc)
    return KnowledgeSectionReadResult.model_validate(result)


@mcp.tool()
async def knowledge_write(entries: WriteEntries) -> KnowledgeWriteResult:
    """Create or fully replace verified durable knowledge after knowledge-distill review.

    Search the candidate concept before create/update. Create omits id/revision. A legacy
    full-document update requires exact id + expected_revision from knowledge_read. Keep
    routing nested, provenance non-empty, and filesystem-owned/language fields out of the
    payload. Stable semantic section markers are optional but, when present, must be unique
    standalone lowercase-kebab markers immediately followed by Markdown H2-H6 headings.
    Pass entries=[] only when policy required a final review and no durable candidate remains.
    """
    payload = [entry.model_dump(exclude_none=True) for entry in entries]
    try:
        for entry in payload:
            parse_sections(entry["content"])
        result = write_knowledge(_store_root(), payload)
    except SectionError as exc:
        _raise_actionable_error(_section_validation_error(exc))
    except KnowledgeError as exc:
        _raise_actionable_error(exc)
    return KnowledgeWriteResult.model_validate(result)


@mcp.tool()
async def knowledge_update(
    id: KnowledgeId,
    expected_revision: Revision,
    changes: KnowledgePatch,
) -> KnowledgeWriteResult:
    """Patch metadata, whole content, or one existing semantic section without resending the document.

    Read the exact target first at the smallest sufficient scope. Metadata patches preserve
    content. Whole-content replacement preserves metadata. Section replacement preserves
    the stable marker and stored heading and changes only that section body. Metadata may be
    combined atomically with either content mode. Full-content and section replacement are
    mutually exclusive. The whole knowledge document still has one SHA-256 revision.
    """
    try:
        result = update_knowledge(
            _store_root(), id, expected_revision, changes.to_patch()
        )
    except KnowledgeError as exc:
        _raise_actionable_error(exc)
    return KnowledgeWriteResult.model_validate(result)


if __name__ == "__main__":
    mcp.run()
