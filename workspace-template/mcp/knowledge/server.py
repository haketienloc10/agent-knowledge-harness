from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from core import KnowledgeError, KnowledgeStore

mcp = MCPServer(
    "QiQi Knowledge",
    instructions=(
        "Shared durable knowledge service independent of the current workspace or repository. "
        "At the start of a work turn, generate multiple task-relevant search terms and call "
        "knowledge_read before investigation. Before finalizing work, review reusable verified "
        "knowledge and call knowledge_write; use entries=[] when nothing should be persisted. "
        "Use canonical English routing concepts plus optional multilingual aliases; document "
        "content may use any language. Live owner-repository source/test overrides stale knowledge."
    ),
)


def _store() -> KnowledgeStore:
    return KnowledgeStore.from_environment()


@mcp.tool()
async def knowledge_read(
    keywords: list[str],
    context: dict[str, str] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Retrieve relevant shared Markdown knowledge using agent-generated keywords.

    `keywords` should contain multiple task-relevant concepts. Prefer canonical
    English concepts and include original-language/domain aliases when useful.
    `context.repo` and `context.domain` are optional ranking hints only; they do
    not restrict which shared knowledge may be returned.
    """
    try:
        return _store().read(keywords, context=context, limit=limit)
    except KnowledgeError as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool()
async def knowledge_write(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist reviewed durable knowledge as canonical Markdown documents.

    Submit semantic fields, never filesystem paths. For creates, omit `id` and
    `expected_revision`; provide canonical_name, title, scope, routing, content,
    and sources. For updates, pass the existing `id` plus `expected_revision`
    returned by knowledge_read and keep its scope/canonical_name unchanged.
    Pass `entries=[]` when the knowledge review found nothing durable to store.
    """
    try:
        return _store().write(entries)
    except KnowledgeError as exc:
        raise RuntimeError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run()
