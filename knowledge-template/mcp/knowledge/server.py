#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from core import DEFAULT_RESULTS, read_knowledge, resolve_store_root, write_knowledge


def _store_root() -> Path:
    raw = os.environ.get("KNOWLEDGE_STORE_ROOT", "").strip()
    if not raw:
        raise RuntimeError("KNOWLEDGE_STORE_ROOT must point to the shared knowledge store")
    return resolve_store_root(raw)


mcp = MCPServer(
    "Shared Knowledge",
    instructions=(
        "Repository-independent durable knowledge service. Use knowledge_read after "
        "understanding the current work and generating several task-relevant search "
        "terms. The caller may provide repo/domain context only as ranking hints; "
        "knowledge is not permission-scoped to the current repository. Use "
        "knowledge_write during finalization only after semantic distillation: "
        "persist reusable, non-trivial, evidence-backed knowledge, or pass an empty "
        "entries list to record that the knowledge review found nothing durable. "
        "Callers never choose a file path or directory."
    ),
)


@mcp.tool()
async def knowledge_read(
    keywords: list[str],
    context: dict[str, str] | None = None,
    limit: int = DEFAULT_RESULTS,
) -> dict[str, Any]:
    """Read relevant shared durable knowledge using caller-generated search terms.

    `keywords` should contain several task-relevant concepts. Canonical English
    concepts are preferred for routing, with original-language or project aliases
    included when useful. `context.repo` and `context.domain` are optional ranking
    hints only; they do not restrict the namespaces that may be returned.
    """
    return read_knowledge(_store_root(), keywords, context, limit)


@mcp.tool()
async def knowledge_write(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist distilled shared knowledge without exposing filesystem decisions.

    Create entries omit `id`/`expected_revision`. Update entries include the exact
    `id` and `expected_revision` returned by knowledge_read. Every entry supplies a
    canonical_name, semantic scope, routing metadata, free-form Markdown content,
    and provenance sources. Paths, filenames, directories, front matter, and
    INDEX.md are owned by this MCP. An empty list records a completed knowledge
    review with no durable update.
    """
    return write_knowledge(_store_root(), entries)


if __name__ == "__main__":
    mcp.run()
