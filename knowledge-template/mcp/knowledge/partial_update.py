from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from core import ConflictError, ValidationError, read_knowledge, write_knowledge
from sections import SectionError, parse_sections, replace_section


REVISION_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_partial_changes(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("knowledge update changes must be an object")
    extra = set(value) - {"metadata", "content", "section"}
    if extra:
        raise ValidationError(
            "knowledge update changes has unsupported field(s): "
            + ", ".join(sorted(extra))
        )
    if not value:
        raise ValidationError("knowledge update changes must contain at least one mutation")
    if value.get("content") is not None and value.get("section") is not None:
        raise ValidationError("knowledge update cannot replace full content and one section together")

    metadata = value.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict) or not metadata:
            raise ValidationError("knowledge metadata patch must be a non-empty object")
        extra_metadata = set(metadata) - {"title", "routing", "sources"}
        if extra_metadata:
            raise ValidationError(
                "knowledge metadata patch has unsupported field(s): "
                + ", ".join(sorted(extra_metadata))
            )
        routing = metadata.get("routing")
        if routing is not None:
            if not isinstance(routing, dict) or not routing:
                raise ValidationError("knowledge routing patch must be a non-empty object")
            extra_routing = set(routing) - {
                "summary",
                "when_to_read",
                "keywords",
                "aliases",
            }
            if extra_routing:
                raise ValidationError(
                    "knowledge routing patch has unsupported field(s): "
                    + ", ".join(sorted(extra_routing))
                )

    section = value.get("section")
    if section is not None:
        if not isinstance(section, dict):
            raise ValidationError("knowledge section patch must be an object")
        if set(section) != {"id", "content"}:
            raise ValidationError(
                "knowledge section patch must contain exactly id and content"
            )
        if not isinstance(section["id"], str) or not section["id"]:
            raise ValidationError("knowledge section id must be a non-empty string")
        if not isinstance(section["content"], str):
            raise ValidationError("knowledge section content must be a string")

    if "content" in value and value["content"] is None:
        raise ValidationError("knowledge content replacement cannot be null")
    if "content" in value and not isinstance(value["content"], str):
        raise ValidationError("knowledge content replacement must be a string")
    return value


def update_knowledge(
    root: Path,
    item_id: str,
    expected_revision: str,
    changes: Any,
) -> dict[str, Any]:
    """Apply a typed partial mutation through the existing whole-document write path.

    The caller sends only changed metadata/content/section state. This adapter hydrates
    the current canonical document server-side, reconstructs the full semantic payload,
    and delegates persistence to write_knowledge so locking, atomic replacement, index
    refresh, rollback, and revision checks remain single-sourced.
    """
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValidationError("knowledge update id must be a non-empty string")
    item_id = item_id.strip()
    if not isinstance(expected_revision, str) or not REVISION_RE.fullmatch(expected_revision):
        raise ValidationError("expected_revision must be a lowercase SHA-256 hex digest")
    normalized = _validate_partial_changes(changes)

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

    try:
        parse_sections(entry["content"])
    except SectionError as exc:
        raise ValidationError(str(exc)) from exc

    return write_knowledge(root, [entry])
