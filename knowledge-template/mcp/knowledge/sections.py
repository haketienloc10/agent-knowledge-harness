from __future__ import annotations

import re
from dataclasses import dataclass


MAX_KNOWLEDGE_SECTIONS = 100
SECTION_MARKER_PREFIX = "<!-- knowledge-section:"
SECTION_MARKER_RE = re.compile(
    r"^<!-- knowledge-section:([a-z0-9]+(?:-[a-z0-9]+)*) -->$"
)
SECTION_HEADING_RE = re.compile(r"^#{2,6} +\S.*$")


class SectionError(ValueError):
    pass


@dataclass(frozen=True)
class SectionSpan:
    section_id: str
    heading: str
    marker_index: int
    heading_index: int
    end_index: int


def parse_sections(content: str) -> list[SectionSpan]:
    """Parse optional stable semantic sections from one knowledge content body.

    Section identity comes from an exact standalone marker immediately followed by a
    Markdown H2-H6 heading. Section boundaries are marker-to-marker, not heading-level
    based, so nested Markdown headings remain ordinary section content.
    """
    if not isinstance(content, str):
        raise SectionError("knowledge content must be a string")

    lines = content.splitlines()
    raw_markers: list[tuple[int, str]] = []
    seen: set[str] = set()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(SECTION_MARKER_PREFIX):
            continue
        if line != stripped:
            raise SectionError(
                f"knowledge section marker at line {index + 1} must not be indented"
            )
        match = SECTION_MARKER_RE.fullmatch(line)
        if match is None:
            raise SectionError(
                f"malformed knowledge section marker at line {index + 1}; expected "
                "<!-- knowledge-section:lowercase-kebab-id -->"
            )
        section_id = match.group(1)
        if section_id in seen:
            raise SectionError(f"duplicate knowledge section id: {section_id}")
        seen.add(section_id)
        raw_markers.append((index, section_id))

    if len(raw_markers) > MAX_KNOWLEDGE_SECTIONS:
        raise SectionError(
            f"knowledge content exceeds {MAX_KNOWLEDGE_SECTIONS} semantic sections"
        )

    spans: list[SectionSpan] = []
    for position, (marker_index, section_id) in enumerate(raw_markers):
        heading_index = marker_index + 1
        if heading_index >= len(lines) or not SECTION_HEADING_RE.fullmatch(lines[heading_index]):
            raise SectionError(
                f"knowledge section {section_id!r} marker must be immediately followed "
                "by a Markdown H2-H6 heading"
            )
        end_index = (
            raw_markers[position + 1][0]
            if position + 1 < len(raw_markers)
            else len(lines)
        )
        spans.append(
            SectionSpan(
                section_id=section_id,
                heading=lines[heading_index],
                marker_index=marker_index,
                heading_index=heading_index,
                end_index=end_index,
            )
        )
    return spans


def section_summaries(content: str) -> list[dict[str, str]]:
    return [
        {"id": span.section_id, "heading": span.heading}
        for span in parse_sections(content)
    ]


def read_section(content: str, section_id: str) -> dict[str, str]:
    for span in parse_sections(content):
        if span.section_id != section_id:
            continue
        lines = content.splitlines()
        body = "\n".join(lines[span.heading_index + 1 : span.end_index]).strip()
        return {
            "section_id": span.section_id,
            "heading": span.heading,
            "content": body,
        }
    raise SectionError(f"knowledge section does not exist: {section_id}")


def replace_section(content: str, section_id: str, replacement: str) -> str:
    if not isinstance(replacement, str):
        raise SectionError("section replacement content must be a string")
    if any(
        line.strip().startswith(SECTION_MARKER_PREFIX)
        for line in replacement.splitlines()
    ):
        raise SectionError(
            "section replacement content must not contain knowledge-section markers; "
            "section structure is owned by the canonical document"
        )

    spans = parse_sections(content)
    target = next((span for span in spans if span.section_id == section_id), None)
    if target is None:
        raise SectionError(f"knowledge section does not exist: {section_id}")

    lines = content.splitlines()
    before = lines[: target.heading_index + 1]
    after = lines[target.end_index :]
    body = replacement.strip()

    rebuilt = list(before)
    if body:
        rebuilt.extend(["", *body.splitlines()])
    if after:
        rebuilt.extend(["", *after])
    return "\n".join(rebuilt).strip()
