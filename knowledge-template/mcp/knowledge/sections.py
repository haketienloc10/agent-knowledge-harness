from __future__ import annotations

import re
from dataclasses import dataclass


MAX_KNOWLEDGE_SECTIONS = 100
MAX_SECTION_ID_CHARS = 100
MAX_SECTION_HEADING_CHARS = 300
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


def _opening_fence(line: str) -> tuple[str, int] | None:
    """Return a CommonMark-style fenced-code opener, if this line is one.

    We only need fence state for reserved-marker recognition, so keep this intentionally
    small: up to three leading spaces, at least three backticks/tildes, and the CommonMark
    backtick-info restriction. Indented code blocks remain ordinary content for the
    section-marker contract; fenced examples are the supported way to show marker syntax.
    """
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3 or len(stripped) < 3:
        return None
    fence_char = stripped[0]
    if fence_char not in {"`", "~"}:
        return None
    run = 0
    while run < len(stripped) and stripped[run] == fence_char:
        run += 1
    if run < 3:
        return None
    rest = stripped[run:]
    if fence_char == "`" and "`" in rest:
        return None
    return fence_char, run


def _is_closing_fence(line: str, fence: tuple[str, int]) -> bool:
    fence_char, minimum_length = fence
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return False
    run = 0
    while run < len(stripped) and stripped[run] == fence_char:
        run += 1
    return run >= minimum_length and not stripped[run:].strip()


def _reserved_marker_lines(content: str) -> list[tuple[int, str]]:
    """Return reserved marker-like lines that are live Markdown, not fenced examples."""
    lines = content.splitlines()
    fence: tuple[str, int] | None = None
    found: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if fence is not None:
            if _is_closing_fence(line, fence):
                fence = None
            continue
        opening = _opening_fence(line)
        if opening is not None:
            fence = opening
            continue
        if line.strip().startswith(SECTION_MARKER_PREFIX):
            found.append((index, line))
    return found


def parse_sections(content: str) -> list[SectionSpan]:
    """Parse optional stable semantic sections from one knowledge content body.

    Section identity comes from an exact standalone marker immediately followed by a
    Markdown H2-H6 heading. Section boundaries are marker-to-marker, not heading-level
    based, so nested Markdown headings remain ordinary section content. Marker examples
    inside fenced Markdown code blocks are ignored and never become live section state.
    """
    if not isinstance(content, str):
        raise SectionError("knowledge content must be a string")

    lines = content.splitlines()
    raw_markers: list[tuple[int, str]] = []
    seen: set[str] = set()

    for index, line in _reserved_marker_lines(content):
        stripped = line.strip()
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
        if len(section_id) > MAX_SECTION_ID_CHARS:
            raise SectionError(
                f"knowledge section id exceeds {MAX_SECTION_ID_CHARS} characters: "
                f"{section_id}"
            )
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
        heading = lines[heading_index]
        if len(heading) > MAX_SECTION_HEADING_CHARS:
            raise SectionError(
                f"knowledge section {section_id!r} heading exceeds "
                f"{MAX_SECTION_HEADING_CHARS} characters"
            )
        end_index = (
            raw_markers[position + 1][0]
            if position + 1 < len(raw_markers)
            else len(lines)
        )
        spans.append(
            SectionSpan(
                section_id=section_id,
                heading=heading,
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


def _section_body_lines(lines: list[str], span: SectionSpan) -> list[str]:
    """Remove only canonical structural blank separators, never content whitespace."""
    body = list(lines[span.heading_index + 1 : span.end_index])
    if body and body[0] == "":
        body = body[1:]
    if body and body[-1] == "":
        body = body[:-1]
    return body


def read_section(content: str, section_id: str) -> dict[str, str]:
    for span in parse_sections(content):
        if span.section_id != section_id:
            continue
        lines = content.splitlines()
        body = "\n".join(_section_body_lines(lines, span))
        return {
            "section_id": span.section_id,
            "heading": span.heading,
            "content": body,
        }
    raise SectionError(f"knowledge section does not exist: {section_id}")


def replace_section(content: str, section_id: str, replacement: str) -> str:
    if not isinstance(replacement, str):
        raise SectionError("section replacement content must be a string")
    if _reserved_marker_lines(replacement):
        raise SectionError(
            "section replacement content must not contain live knowledge-section markers; "
            "section structure is owned by the canonical document. Marker examples are "
            "allowed only inside fenced Markdown code blocks"
        )

    spans = parse_sections(content)
    target = next((span for span in spans if span.section_id == section_id), None)
    if target is None:
        raise SectionError(f"knowledge section does not exist: {section_id}")

    lines = content.splitlines()
    before = lines[: target.heading_index + 1]
    after = lines[target.end_index :]
    body_lines = replacement.split("\n") if replacement else []

    rebuilt = list(before)
    if body_lines:
        rebuilt.extend(["", *body_lines])
    if after:
        rebuilt.extend(["", *after])
    rebuilt_content = "\n".join(rebuilt)

    # A replacement body may legitimately contain fenced examples, but it must not use
    # an unclosed fence to swallow later live section markers. Reparse the complete
    # document and require the exact stable section identities/headings to survive.
    rebuilt_spans = parse_sections(rebuilt_content)
    original_structure = [(span.section_id, span.heading) for span in spans]
    rebuilt_structure = [(span.section_id, span.heading) for span in rebuilt_spans]
    if rebuilt_structure != original_structure:
        raise SectionError(
            "section replacement must preserve all existing semantic section markers "
            "and headings"
        )
    return rebuilt_content
