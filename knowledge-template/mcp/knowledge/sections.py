from __future__ import annotations

import re
from dataclasses import dataclass

from markdown_it import MarkdownIt


MAX_KNOWLEDGE_SECTIONS = 100
MAX_SECTION_ID_CHARS = 100
MAX_SECTION_HEADING_CHARS = 300
MAX_SECTION_BODY_CHARS = 24_000
SECTION_MARKER_PREFIX = "<!-- knowledge-section:"
SECTION_MARKER_RE = re.compile(
    r"^<!-- knowledge-section:([a-z0-9]+(?:-[a-z0-9]+)*) -->$"
)
# Semantic sections intentionally use non-empty ATX H2-H6 headings. CommonMark permits
# up to three leading spaces and either spaces or tabs after the opening hash sequence.
SECTION_HEADING_RE = re.compile(r"^ {0,3}#{2,6}[ \t]+\S.*$")
MARKDOWN_LINE_ENDING_RE = re.compile(r"\r\n|\r|\n")
_TOP_LEVEL = 0
_HEADING_TAGS = {"h2", "h3", "h4", "h5", "h6"}
_MARKDOWN = MarkdownIt("commonmark", {"html": True})


class SectionError(ValueError):
    pass


@dataclass(frozen=True)
class SectionSpan:
    section_id: str
    heading: str
    marker_index: int
    heading_index: int
    end_index: int


def split_markdown_lines(value: str) -> list[str]:
    """Split only on CR/LF Markdown line endings, never Unicode text separators.

    Match ``str.splitlines()`` terminal behavior for Markdown line endings so a canonical
    file's final newline does not become semantic content. Interior empty lines remain.
    """
    if value == "":
        return []
    lines = MARKDOWN_LINE_ENDING_RE.split(value)
    if lines and lines[-1] == "" and value.endswith(("\r", "\n")):
        lines.pop()
    return lines


def _section_body_lines(lines: list[str], span: SectionSpan) -> list[str]:
    """Remove only canonical structural blank separators, never content whitespace."""
    body = list(lines[span.heading_index + 1 : span.end_index])
    if body and body[0] == "":
        body = body[1:]
    if body and body[-1] == "":
        body = body[:-1]
    return body


def _commonmark_tokens(content: str):
    """Parse a line-normalized view solely for maintained CommonMark block classification."""
    normalized = "\n".join(split_markdown_lines(content))
    return _MARKDOWN.parse(normalized)


def _top_level_marker_blocks(content: str) -> list[tuple[int, str, str]]:
    """Return top-level semantic marker blocks as ``(line, id, exact_heading)``.

    CommonMark block ownership is delegated to markdown-it-py. Consequently marker-looking
    text inside fences, indented code, lists/quotes, or raw HTML is never promoted by a
    home-grown container state machine. This layer owns only the Knowledge-specific lexical
    contract: one exact top-level marker followed immediately by one non-empty ATX H2-H6.
    """
    lines = split_markdown_lines(content)
    tokens = _commonmark_tokens(content)
    found: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    for position, token in enumerate(tokens):
        if (
            token.type != "html_block"
            or token.level != _TOP_LEVEL
            or token.map is None
        ):
            continue

        marker_index, block_end = token.map
        if marker_index >= len(lines):
            continue

        marker_line = lines[marker_index]
        stripped = marker_line.strip()
        if not stripped.startswith(SECTION_MARKER_PREFIX):
            continue

        if marker_line != stripped:
            raise SectionError(
                f"knowledge section marker at line {marker_index + 1} must not be indented"
            )

        match = SECTION_MARKER_RE.fullmatch(marker_line)
        if match is None or block_end != marker_index + 1:
            raise SectionError(
                f"malformed knowledge section marker at line {marker_index + 1}; expected "
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

        heading_index = marker_index + 1
        if heading_index >= len(lines) or position + 2 >= len(tokens):
            raise SectionError(
                f"knowledge section {section_id!r} marker must be immediately followed "
                "by a Markdown H2-H6 heading"
            )

        heading_token = tokens[position + 1]
        inline_token = tokens[position + 2]
        is_immediate_heading = (
            heading_token.type == "heading_open"
            and heading_token.level == _TOP_LEVEL
            and heading_token.tag in _HEADING_TAGS
            and heading_token.map == [heading_index, heading_index + 1]
            and inline_token.type == "inline"
            and inline_token.level == 1
            and bool(inline_token.content.strip())
        )
        heading = lines[heading_index]
        if not is_immediate_heading or SECTION_HEADING_RE.fullmatch(heading) is None:
            raise SectionError(
                f"knowledge section {section_id!r} marker must be immediately followed "
                "by a Markdown H2-H6 heading"
            )
        if len(heading) > MAX_SECTION_HEADING_CHARS:
            raise SectionError(
                f"knowledge section {section_id!r} heading exceeds "
                f"{MAX_SECTION_HEADING_CHARS} characters"
            )

        seen.add(section_id)
        found.append((marker_index, section_id, heading))

    return found


def parse_sections(content: str) -> list[SectionSpan]:
    """Parse optional stable semantic sections from one Knowledge content body.

    Section identity comes from an exact top-level marker immediately followed by a
    non-empty ATX Markdown H2-H6 heading. CommonMark block classification is owned by
    markdown-it-py rather than this module; this module only enforces Knowledge marker,
    heading, size, identity, and replacement invariants.
    """
    if not isinstance(content, str):
        raise SectionError("knowledge content must be a string")

    lines = split_markdown_lines(content)
    raw_markers = _top_level_marker_blocks(content)

    if len(raw_markers) > MAX_KNOWLEDGE_SECTIONS:
        raise SectionError(
            f"knowledge content exceeds {MAX_KNOWLEDGE_SECTIONS} semantic sections"
        )

    spans: list[SectionSpan] = []
    for position, (marker_index, section_id, heading) in enumerate(raw_markers):
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
                heading_index=marker_index + 1,
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
        lines = split_markdown_lines(content)
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

    # Reject any replacement that introduces live top-level semantic structure. Marker
    # examples remain valid inside CommonMark fences, code/container blocks, or raw HTML.
    if _top_level_marker_blocks(replacement):
        raise SectionError(
            "section replacement content must not contain live knowledge-section markers; "
            "section structure is owned by the canonical document"
        )

    spans = parse_sections(content)
    target = next((span for span in spans if span.section_id == section_id), None)
    if target is None:
        raise SectionError(f"knowledge section does not exist: {section_id}")

    lines = split_markdown_lines(content)
    before = lines[: target.heading_index + 1]
    after = lines[target.end_index :]
    # Preserve historical terminal-empty behavior while splitting only on Markdown CR/LF.
    body_lines = MARKDOWN_LINE_ENDING_RE.split(replacement) if replacement else []

    rebuilt = list(before)
    if body_lines:
        rebuilt.extend(["", *body_lines])
    if after:
        rebuilt.extend(["", *after])
    rebuilt_content = "\n".join(rebuilt)

    # Reparse the complete document after replacement. An unclosed leaf block may not
    # swallow a later live marker; section identity + exact heading structure must survive.
    rebuilt_spans = parse_sections(rebuilt_content)
    original_structure = [(span.section_id, span.heading) for span in spans]
    rebuilt_structure = [(span.section_id, span.heading) for span in rebuilt_spans]
    if rebuilt_structure != original_structure:
        raise SectionError(
            "section replacement must preserve all existing semantic section markers "
            "and headings"
        )
    return rebuilt_content
