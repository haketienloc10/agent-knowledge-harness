from __future__ import annotations

import re
from dataclasses import dataclass


MAX_KNOWLEDGE_SECTIONS = 100
MAX_SECTION_ID_CHARS = 100
MAX_SECTION_HEADING_CHARS = 300
MAX_SECTION_BODY_CHARS = 24_000
SECTION_MARKER_PREFIX = "<!-- knowledge-section:"
SECTION_MARKER_RE = re.compile(
    r"^<!-- knowledge-section:([a-z0-9]+(?:-[a-z0-9]+)*) -->$"
)
SECTION_HEADING_RE = re.compile(r"^#{2,6} +\S.*$")
LIST_ITEM_RE = re.compile(
    r"^ {0,3}(?:[-+*]|\d{1,9}[.)])(?P<gap>[ \t]+)(?P<content>.*)$"
)


class SectionError(ValueError):
    pass


@dataclass(frozen=True)
class SectionSpan:
    section_id: str
    heading: str
    marker_index: int
    heading_index: int
    end_index: int


@dataclass(frozen=True)
class FenceState:
    char: str
    minimum_length: int
    container_indent: int
    max_closing_indent: int


def _section_body_lines(lines: list[str], span: SectionSpan) -> list[str]:
    """Remove only canonical structural blank separators, never content whitespace."""
    body = list(lines[span.heading_index + 1 : span.end_index])
    if body and body[0] == "":
        body = body[1:]
    if body and body[-1] == "":
        body = body[:-1]
    return body


def _leading_indent(line: str) -> tuple[str, int]:
    """Return content after leading spaces/tabs plus its CommonMark-style column width."""
    index = 0
    columns = 0
    while index < len(line) and line[index] in {" ", "\t"}:
        if line[index] == " ":
            columns += 1
        else:
            columns += 4 - (columns % 4)
        index += 1
    return line[index:], columns


def _column_width(value: str) -> int:
    columns = 0
    for char in value:
        if char == "\t":
            columns += 4 - (columns % 4)
        else:
            columns += 1
    return columns


def _fence_run(value: str) -> tuple[str, int] | None:
    if len(value) < 3:
        return None
    fence_char = value[0]
    if fence_char not in {"`", "~"}:
        return None
    run = 0
    while run < len(value) and value[run] == fence_char:
        run += 1
    if run < 3:
        return None
    rest = value[run:]
    if fence_char == "`" and "`" in rest:
        return None
    return fence_char, run


def _opening_fence(line: str) -> FenceState | None:
    """Return lightweight fence state used only for reserved-marker recognition.

    This scanner is deliberately smaller than a full Markdown parser. It recognizes
    ordinary CommonMark fences with up to three leading columns and fences that begin
    directly as list-item content (for example ``- ```markdown``). Marker-like lines
    indented four or more columns are handled separately as non-live Markdown
    code/container content, so list-continuation fences do not need a full container stack.
    """
    stripped, indent_columns = _leading_indent(line)
    if indent_columns <= 3:
        fence = _fence_run(stripped)
        if fence is not None:
            return FenceState(
                char=fence[0],
                minimum_length=fence[1],
                container_indent=0,
                max_closing_indent=3,
            )

    list_match = LIST_ITEM_RE.fullmatch(line)
    if list_match is None:
        return None
    gap = list_match.group("gap")
    if _column_width(gap) > 4:
        return None
    content = list_match.group("content")
    fence = _fence_run(content)
    if fence is None:
        return None
    content_prefix = line[: list_match.start("content")]
    container_indent = _column_width(content_prefix)
    return FenceState(
        char=fence[0],
        minimum_length=fence[1],
        container_indent=container_indent,
        max_closing_indent=container_indent + 3,
    )


def _is_closing_fence(line: str, fence: FenceState) -> bool:
    stripped, indent_columns = _leading_indent(line)
    if indent_columns > fence.max_closing_indent:
        return False
    run = 0
    while run < len(stripped) and stripped[run] == fence.char:
        run += 1
    return run >= fence.minimum_length and not stripped[run:].strip()


def _reserved_marker_lines(content: str) -> list[tuple[int, str]]:
    """Return reserved marker-like lines that are live Markdown, not code/examples."""
    lines = content.splitlines()
    fence: FenceState | None = None
    found: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if fence is not None:
            _, indent_columns = _leading_indent(line)
            if line.strip() and indent_columns < fence.container_indent:
                # An outdented nonblank line leaves a list container. An unclosed fenced
                # block inside that list ends with its parent container, so process this
                # line again as ordinary outer Markdown instead of hiding live markers.
                fence = None
            else:
                if _is_closing_fence(line, fence):
                    fence = None
                continue

        opening = _opening_fence(line)
        if opening is not None:
            fence = opening
            continue

        marker_text, indent_columns = _leading_indent(line)
        if not marker_text.startswith(SECTION_MARKER_PREFIX):
            continue
        # Four columns is Markdown indented-code territory at top level and also the
        # common raw indentation of fenced/list continuation content. Such text cannot
        # be a top-level live section marker. One-to-three columns remain candidates so
        # parse_sections can reject accidentally indented live-marker syntax explicitly.
        if indent_columns >= 4:
            continue
        found.append((index, line))
    return found


def parse_sections(content: str) -> list[SectionSpan]:
    """Parse optional stable semantic sections from one knowledge content body.

    Section identity comes from an exact standalone marker immediately followed by a
    Markdown H2-H6 heading. Section boundaries are marker-to-marker, not heading-level
    based, so nested Markdown headings remain ordinary section content. Marker examples
    inside fenced Markdown code blocks or indented/container code are ignored and never
    become live section state.
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

    for span in spans:
        body = "\n".join(_section_body_lines(lines, span))
        if len(body) > MAX_SECTION_BODY_CHARS:
            raise SectionError(
                f"knowledge section {span.section_id!r} body exceeds "
                f"{MAX_SECTION_BODY_CHARS} characters"
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
