#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from mcp.server import MCPServer

from contracts import (
    KnowledgeReadContext,
    KnowledgeReadResult,
    KnowledgeWriteResult,
    ReadKeywords,
    ReadLimit,
    WriteEntries,
)
from core import (
    DEFAULT_RESULTS,
    ConflictError,
    KnowledgeError,
    ValidationError,
    read_knowledge,
    resolve_store_root,
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
                f"{message}; action=search/read the existing knowledge first and update it "
                "with exact id + expected_revision instead of retrying create"
            ) from exc
        if "does not exist for update" in lowered:
            raise ValueError(
                "code=missing_update_target; "
                f"{message}; action=call knowledge_read/search again; create only if no "
                "existing knowledge covers the concept"
            ) from exc
        if "index is stale" in lowered or "index points to a different id" in lowered:
            raise ValueError(
                "code=stale_index; "
                f"{message}; action=do not retry unchanged; the store operator must run "
                "knowledge reindex/check before this knowledge can be read safely"
            ) from exc
        raise ValueError(f"code=knowledge_conflict; {message}") from exc
    if isinstance(exc, ValidationError):
        raise ValueError(
            "code=knowledge_validation; "
            f"{message}; action=inspect the typed tool schema and correct the payload "
            "instead of guessing filesystem fields or flattening nested routing metadata"
        ) from exc
    raise RuntimeError(f"code=knowledge_store_error; {message}") from exc


mcp = MCPServer(
    "Shared Knowledge",
    instructions=(
        "Repository-independent durable knowledge service. Use knowledge_read after "
        "understanding the current work and generating several task-relevant search "
        "terms. The caller may provide repo/domain context only as ranking hints; "
        "knowledge is not permission-scoped to the current repository. Before every "
        "knowledge_write required by agent policy, apply the installed knowledge-distill "
        "skill to the evidence from the current work. Persist the durable conclusion the "
        "evidence actually established, not an unverified task, ticket, incident, or bug "
        "premise; preserve material inference and remaining uncertainty. Use "
        "knowledge_write during finalization only after that semantic distillation: "
        "persist reusable, non-trivial, evidence-backed knowledge, or pass an empty "
        "entries list when a required review found nothing durable. The knowledge_write "
        "schema is strict and nested: summary, when_to_read, keywords, and aliases belong "
        "under routing. Create omits id/revision; update uses exact id + expected_revision "
        "from knowledge_read. Callers never choose a file path, filename, directory, INDEX "
        "path, or language field."
    ),
)


@mcp.tool()
async def knowledge_read(
    keywords: ReadKeywords,
    context: KnowledgeReadContext | None = None,
    limit: ReadLimit = DEFAULT_RESULTS,
) -> KnowledgeReadResult:
    """Read relevant shared durable knowledge using explicit typed search inputs.

    Generate several task-relevant concepts before calling. Canonical English
    concepts are preferred for routing, with original-language/project aliases when
    useful. `context.repo` and `context.domain` are optional ranking hints only.
    The result schema exposes stable id/path/revision so updates never guess identity
    or filesystem location.
    """
    try:
        result = read_knowledge(
            _store_root(),
            keywords,
            context.model_dump(exclude_none=True) if context is not None else None,
            limit,
        )
    except KnowledgeError as exc:
        _raise_actionable_error(exc)
    return KnowledgeReadResult.model_validate(result)


@mcp.tool()
async def knowledge_write(entries: WriteEntries) -> KnowledgeWriteResult:
    """Persist knowledge only after applying the installed knowledge-distill skill.

    Distill from evidence, not from the task premise: do not create a bug/ticket-named
    durable claim unless the work actually verified that claim. Preserve important
    fact-vs-inference boundaries and unresolved uncertainty. Compression must not
    increase certainty. Search the candidate conclusion before create/update.

    CREATE: omit `id` and `expected_revision`.
    UPDATE: provide exact `id` + `expected_revision` returned by knowledge_read.
    ROUTING: put `summary`, `when_to_read`, `keywords`, and optional `aliases`
    inside the nested `routing` object.
    NEVER provide path/filename/directory/INDEX fields; Knowledge MCP owns them.
    `content` may be Vietnamese, English, or mixed; there is no `language` field.
    Pass `entries=[]` only when policy required a finalization review and the
    knowledge-distill procedure found nothing durable to persist.
    """
    payload = [entry.model_dump(exclude_none=True) for entry in entries]
    try:
        result = write_knowledge(_store_root(), payload)
    except KnowledgeError as exc:
        _raise_actionable_error(exc)
    return KnowledgeWriteResult.model_validate(result)


if __name__ == "__main__":
    mcp.run()
