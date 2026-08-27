from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

from artifacts import ARTIFACT_TYPES

ARTIFACT_TEMPLATES_ENV = "WORK_ITEM_ARTIFACT_TEMPLATES_PATH"
DEFAULT_ARTIFACT_TEMPLATES_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "artifact-templates.json"
)
ARTIFACT_TEMPLATE_FILE_MAX_BYTES = 64_000
ARTIFACT_TEMPLATE_SECTION_MAX = 100
ARTIFACT_TEMPLATE_DESCRIPTION_MAX_CHARS = 1_000
ARTIFACT_TEMPLATE_PURPOSE_MAX_CHARS = 2_000
ARTIFACT_TEMPLATE_SECTION_TITLE_MAX_CHARS = 300
SECTION_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class ArtifactTemplateConfigError(RuntimeError):
    pass


def _required_text(value: Any, label: str, *, max_chars: int) -> str:
    if not isinstance(value, str):
        raise ArtifactTemplateConfigError(f"{label} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ArtifactTemplateConfigError(f"{label} must not be empty")
    if len(cleaned) > max_chars:
        raise ArtifactTemplateConfigError(f"{label} exceeds {max_chars} characters")
    return cleaned


def resolve_artifact_templates_path() -> Path:
    raw = os.environ.get(ARTIFACT_TEMPLATES_ENV, "").strip()
    path = Path(raw).expanduser() if raw else DEFAULT_ARTIFACT_TEMPLATES_PATH
    resolved = path.resolve()
    if not resolved.exists():
        source = ARTIFACT_TEMPLATES_ENV if raw else "default artifact template config"
        raise ArtifactTemplateConfigError(f"{source} does not exist: {resolved}")
    if not resolved.is_file():
        raise ArtifactTemplateConfigError(f"artifact template config is not a file: {resolved}")
    return resolved


def _validate_section(value: Any, *, artifact_type: str, index: int) -> dict[str, str]:
    label = f"artifact template {artifact_type}.sections[{index}]"
    if not isinstance(value, dict):
        raise ArtifactTemplateConfigError(f"{label} must be an object")
    unknown = sorted(set(value) - {"id", "title", "purpose"})
    if unknown:
        raise ArtifactTemplateConfigError(
            f"{label} contains unknown fields: {', '.join(unknown)}"
        )

    section_id = _required_text(value.get("id"), f"{label}.id", max_chars=128)
    if not SECTION_ID_RE.fullmatch(section_id):
        raise ArtifactTemplateConfigError(
            f"{label}.id must start with a lowercase letter and contain only lowercase "
            "letters, digits, _ or -"
        )
    title = _required_text(
        value.get("title"),
        f"{label}.title",
        max_chars=ARTIFACT_TEMPLATE_SECTION_TITLE_MAX_CHARS,
    )
    purpose = _required_text(
        value.get("purpose"),
        f"{label}.purpose",
        max_chars=ARTIFACT_TEMPLATE_PURPOSE_MAX_CHARS,
    )
    return {"id": section_id, "title": title, "purpose": purpose}


def validate_artifact_templates(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ArtifactTemplateConfigError("artifact template config root must be an object")

    unknown_types = sorted(set(value) - ARTIFACT_TYPES)
    if unknown_types:
        allowed = ", ".join(sorted(ARTIFACT_TYPES))
        raise ArtifactTemplateConfigError(
            "artifact template config contains unsupported types: "
            f"{', '.join(unknown_types)}; allowed types: {allowed}"
        )

    result: dict[str, dict[str, Any]] = {}
    for artifact_type, template in value.items():
        label = f"artifact template {artifact_type}"
        if not isinstance(template, dict):
            raise ArtifactTemplateConfigError(f"{label} must be an object")
        unknown = sorted(set(template) - {"description", "sections"})
        if unknown:
            raise ArtifactTemplateConfigError(
                f"{label} contains unknown fields: {', '.join(unknown)}"
            )

        description = _required_text(
            template.get("description"),
            f"{label}.description",
            max_chars=ARTIFACT_TEMPLATE_DESCRIPTION_MAX_CHARS,
        )
        sections = template.get("sections")
        if not isinstance(sections, list):
            raise ArtifactTemplateConfigError(f"{label}.sections must be a list")
        if len(sections) > ARTIFACT_TEMPLATE_SECTION_MAX:
            raise ArtifactTemplateConfigError(
                f"{label}.sections exceeds {ARTIFACT_TEMPLATE_SECTION_MAX} entries"
            )

        normalized_sections: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for index, section in enumerate(sections):
            normalized = _validate_section(
                section, artifact_type=artifact_type, index=index
            )
            if normalized["id"] in seen_ids:
                raise ArtifactTemplateConfigError(
                    f"{label}.sections contains duplicate id {normalized['id']!r}"
                )
            seen_ids.add(normalized["id"])
            normalized_sections.append(normalized)

        result[artifact_type] = {
            "description": description,
            "sections": normalized_sections,
        }
    return result


def load_artifact_templates(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    resolved = Path(path).expanduser().resolve() if path is not None else resolve_artifact_templates_path()
    if path is not None:
        if not resolved.exists():
            raise ArtifactTemplateConfigError(f"artifact template config does not exist: {resolved}")
        if not resolved.is_file():
            raise ArtifactTemplateConfigError(f"artifact template config is not a file: {resolved}")

    size = resolved.stat().st_size
    if size > ARTIFACT_TEMPLATE_FILE_MAX_BYTES:
        raise ArtifactTemplateConfigError(
            f"artifact template config exceeds {ARTIFACT_TEMPLATE_FILE_MAX_BYTES} bytes: {resolved}"
        )

    try:
        raw = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactTemplateConfigError(
            f"cannot read artifact template config {resolved}: {exc}"
        ) from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArtifactTemplateConfigError(
            f"invalid JSON in artifact template config {resolved}: line {exc.lineno}, column {exc.colno}"
        ) from exc
    return validate_artifact_templates(parsed)


def template_guidance_for(
    templates: dict[str, dict[str, Any]], artifact_type: str
) -> dict[str, Any] | None:
    """Return detached advisory guidance so callers cannot mutate startup config in memory."""
    template = templates.get(artifact_type)
    return copy.deepcopy(template) if template is not None else None
