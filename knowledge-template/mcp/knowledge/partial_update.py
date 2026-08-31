from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from core import ConflictError, ValidationError, read_knowledge, write_knowledge
from partial_contracts import KnowledgePatch
from sections import SectionError, replace_section


REVISION_RE = re.compile(r"^[0-9a-f]{64}$")


def _normalize_partial_changes(value: Any) -> dict[str, Any]:
    """Validate the partial-patch grammar exactly once through ``KnowledgePatch``."""
    try:
        patch = value if isinstance(value, KnowledgePatch) else KnowledgePatch.model_validate(value)
    except PydanticValidationError as exc:
        raise ValidationError(f"knowledge update changes are invalid: {exc}") from exc
    return patch.to_patch()


def update_knowledge(
    root: Path,
    item_id: str,
    expected_revision: str,
    changes: Any,
) -> dict[str, Any]:
    """Apply a typed partial mutation through the existing whole-document write path.

    ``KnowledgePatch`` owns patch grammar. This adapter only hydrates the current canonical
    document, reconciles the validated changed state, and delegates persistence to
    ``write_knowledge`` so locking, atomic replacement, index refresh, rollback, revision
    checks, and canonical section validation remain single-sourced.
    """
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValidationError("knowledge update id must be a non-empty string")
    item_id = item_id.strip()
    if not isinstance(expected_revision, str) or not REVISION_RE.fullmatch(expected_revision):
        raise ValidationError("expected_revision must be a lowercase SHA-256 hex digest")
    normalized = _normalize_partial_changes(changes)

    current = read_knowledge(root, [item_id])["results"][0]
    if current["revision"] != expected_revision:
        raise ConflictError(
            f"knowledge revision conflict for {item_id}: expected {expected_revision}, "
            f"current {current['revision']}"
        )

    entry: dict[str, Any] = {
        "id": current["id"],
        "expected_revision": expected_revision,
        "canonical_name": current["canonical_name"],
        "title": current["title"],
        "scope": copy.deepcopy(current["scope"]),
        "routing": copy.deepcopy(current["routing"]),
        "content": current["content"],
        "sources": copy.deepcopy(current["sources"]),
    }

    metadata = normalized.get("metadata")
    if metadata is not None:
        if "title" in metadata:
            entry["title"] = metadata["title"]
        if "routing" in metadata:
            entry["routing"].update(copy.deepcopy(metadata["routing"]))
        if "sources" in metadata:
            entry["sources"] = copy.deepcopy(metadata["sources"])

    if "content" in normalized:
        entry["content"] = normalized["content"]
    elif normalized.get("section") is not None:
        section = normalized["section"]
        try:
            entry["content"] = replace_section(
                entry["content"], section["id"], section["content"]
            )
        except SectionError as exc:
            raise ValidationError(str(exc)) from exc

    return write_knowledge(root, [entry])
