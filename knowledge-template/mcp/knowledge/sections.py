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
ATX_HEADING_RE = re.compile(r"^#{1,6}(?:[ \t]+|$)")
LIST_ITEM_RE = re.compile(
    r"^ {0,3}(?:[-+*]|\d{1,9}[.)])(?P<gap>[ \t]+)(?P<content>.*)$"
)
HTML_LITERAL_TAG_RE = re.compile(
    r"^<(?:pre|script|style|textarea)(?=[ \t>]|$)", re.IGNORECASE
)
HTML_LITERAL_END_RE = re.compile(
    r"</(?:pre|script|style|textarea)>", re.IGNORECASE
)
HTML_BLOCK_TAG_RE = re.compile(
    r"^</?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|"
    r"colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|"
    r"frame|frameset|h1|h2|h3|h4|h5|h6|head|header|hr|html|iframe|legend|li|link|main|"
    r"menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|"
    r"tbody|td|tfoot|th|thead|title|tr|track|ul)(?=[ \t>/]|$)",
    re.IGNORECASE,
)
HTML_TAG_NAME = r"[A-Za-z][A-Za-z0-9-]*"
HTML_ATTR_NAME = r"[A-Za-z_:][A-Za-z0-9_.:-]*"
HTML_ATTR_VALUE = r'(?:[^\s"\'=<>`]+|\'[^\']*\'|"[^"]*")'
HTML_ATTRIBUTE = rf"[ \t]+{HTML_ATTR_NAME}(?:[ \t]*=[ \t]*{HTML_ATTR_VALUE})?"
HTML_COMPLETE_TAG_RE = re.compile(
    rf"^(?:<{HTML_TAG_NAME}(?:{HTML_ATTRIBUTE})*[ \t]*/?>|"
    rf"</{HTML_TAG_NAME}[ \t]*>)[ \t]*$"
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


@dataclass(frozen=True)
class HtmlBlockState:
    kind: int
    container_indent: int


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


def _list_item_layout(line: str) -> tuple[int, int, str] | None:
    """Return bullet indent, content indent, and content for one supported list item."""
    match = LIST_ITEM_RE.fullmatch(line)
    if match is None or _column_width(match.group("gap")) > 4:
        return None
    _, bullet_indent = _leading_indent(line)
    content_indent = _column_width(line[: match.start("content")])
    return bullet_indent, content_indent, match.group("content")


def _leaf_block_content(
    line: str, container_indent: int
) -> tuple[str, int] | None:
    """Return content + owning indent for one Markdown leaf-block opener candidate."""
    layout = _list_item_layout(line)
    if layout is not None:
        _, item_content_indent, item_content = layout
        return item_content, item_content_indent

    stripped, indent_columns = _leading_indent(line)
    if indent_columns < container_indent:
        return None
    relative_indent = indent_columns - container_indent
    if relative_indent > 3:
        return None
    return stripped, container_indent


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


def _opening_fence(line: str, container_indent: int = 0) -> FenceState | None:
    """Return lightweight fence state used only for reserved-marker recognition.

    This scanner is deliberately smaller than a full Markdown parser. It recognizes
    ordinary CommonMark fences, fences that begin directly as list-item content, and
    continuation fences relative to the currently active list container. That container
    context is required before classifying a two/three-space continuation fence; raw
    indentation alone cannot distinguish it from a top-level fence.
    """
    candidate = _leaf_block_content(line, container_indent)
    if candidate is None:
        return None
    content, owner_indent = candidate
    fence = _fence_run(content)
    if fence is None:
        return None
    return FenceState(
        char=fence[0],
        minimum_length=fence[1],
        container_indent=owner_indent,
        max_closing_indent=owner_indent + 3,
    )


def _is_closing_fence(line: str, fence: FenceState) -> bool:
    stripped, indent_columns = _leading_indent(line)
    if indent_columns < fence.container_indent or indent_columns > fence.max_closing_indent:
        return False
    run = 0
    while run < len(stripped) and stripped[run] == fence.char:
        run += 1
    return run >= fence.minimum_length and not stripped[run:].strip()


def _opening_html_block(
    line: str,
    container_indent: int = 0,
    *,
    allow_type7: bool,
) -> HtmlBlockState | None:
    """Recognize CommonMark HTML-block starts for reserved-marker suppression.

    Types 1-6 may interrupt a paragraph. Type 7 is recognized only at an observed block
    boundary because CommonMark does not allow it to interrupt a paragraph. Reserved
    knowledge-section marker lines are handled before this helper so their HTML-comment
    syntax remains live section syntax rather than being swallowed as type-2 HTML blocks.
    """
    candidate = _leaf_block_content(line, container_indent)
    if candidate is None:
        return None
    content, owner_indent = candidate
    if HTML_LITERAL_TAG_RE.match(content):
        return HtmlBlockState(kind=1, container_indent=owner_indent)
    if content.startswith("<!--"):
        return HtmlBlockState(kind=2, container_indent=owner_indent)
    if content.startswith("<?"):
        return HtmlBlockState(kind=3, container_indent=owner_indent)
    if re.match(r"^<![A-Za-z]", content):
        return HtmlBlockState(kind=4, container_indent=owner_indent)
    if content.startswith("<![CDATA["):
        return HtmlBlockState(kind=5, container_indent=owner_indent)
    if HTML_BLOCK_TAG_RE.match(content):
        return HtmlBlockState(kind=6, container_indent=owner_indent)
    if allow_type7 and HTML_COMPLETE_TAG_RE.fullmatch(content):
        return HtmlBlockState(kind=7, container_indent=owner_indent)
    return None


def _html_block_ends(line: str, block: HtmlBlockState) -> bool:
    if block.kind == 1:
        return HTML_LITERAL_END_RE.search(line) is not None
    if block.kind == 2:
        return "-->" in line
    if block.kind == 3:
        return "?>" in line
    if block.kind == 4:
        return ">" in line
    if block.kind == 5:
        return "]]>" in line
    if block.kind in {6, 7}:
        return not line.strip()
    raise AssertionError(f"unsupported HTML block kind: {block.kind}")


def _update_list_containers(line: str, list_indents: list[int]) -> None:
    """Track enough list-container indentation to classify continuation leaf blocks."""
    if not line.strip():
        return
    layout = _list_item_layout(line)
    if layout is not None:
        bullet_indent, content_indent, _ = layout
        while list_indents and bullet_indent < list_indents[-1]:
            list_indents.pop()
        list_indents.append(content_indent)
        return

    _, indent_columns = _leading_indent(line)
    while list_indents and indent_columns < list_indents[-1]:
        list_indents.pop()


def _reserved_marker_lines(content: str) -> list[tuple[int, str]]:
    """Return reserved marker-like lines that are live Markdown, not code/examples."""
    lines = content.splitlines()
    fence: FenceState | None = None
    html_block: HtmlBlockState | None = None
    list_indents: list[int] = []
    found: list[tuple[int, str]] = []
    allow_type7 = True
    for index, line in enumerate(lines):
        if fence is not None:
            _, indent_columns = _leading_indent(line)
            if line.strip() and indent_columns < fence.container_indent:
                # An outdented nonblank line leaves a list container. An unclosed fenced
                # block inside that list ends with its parent container, so process this
                # line again as ordinary outer Markdown instead of hiding live markers.
                fence = None
                allow_type7 = True
            else:
                if _is_closing_fence(line, fence):
                    fence = None
                    allow_type7 = True
                continue

        if html_block is not None:
            _, indent_columns = _leading_indent(line)
            if line.strip() and indent_columns < html_block.container_indent:
                # CommonMark HTML blocks also end at the containing block boundary.
                # Re-process this outdented line as outer Markdown.
                html_block = None
                allow_type7 = True
            else:
                if _html_block_ends(line, html_block):
                    html_block = None
                    allow_type7 = True
                continue

        if not line.strip():
            allow_type7 = True
            continue

        _update_list_containers(line, list_indents)
        active_container_indent = list_indents[-1] if list_indents else 0

        marker_text, indent_columns = _leading_indent(line)
        if marker_text.startswith(SECTION_MARKER_PREFIX):
            # Reserved section syntax intentionally resembles an HTML comment. It must
            # remain live at top level, while identical text inside an already-active
            # HTML/fenced/code block is ignored above.
            if indent_columns < 4:
                found.append((index, line))
            allow_type7 = True
            continue

        opening_fence = _opening_fence(line, active_container_indent)
        if opening_fence is not None:
            fence = opening_fence
            allow_type7 = True
            continue

        opening_html = _opening_html_block(
            line,
            active_container_indent,
            allow_type7=allow_type7,
        )
        if opening_html is not None:
            if not _html_block_ends(line, opening_html):
                html_block = opening_html
            allow_type7 = True
            continue

        # Four columns is Markdown indented-code territory at top level and also the
        # common raw indentation of fenced/list continuation content. Non-marker text
        # there cannot make the next type-7 HTML tag interrupt a paragraph at top level.
        if indent_columns >= 4:
            allow_type7 = True
            continue

        # We do not implement a complete CommonMark paragraph parser here; this flag is
        # intentionally conservative and exists only to avoid treating standalone type-7
        # HTML tags as block starts when the immediately preceding line is ordinary text.
        allow_type7 = ATX_HEADING_RE.match(marker_text) is not None
    return found


def parse_sections(content: str) -> list[SectionSpan]:
    """Parse optional stable semantic sections from one knowledge content body.

    Section identity comes from an exact standalone marker immediately followed by a
    Markdown H2-H6 heading. Section boundaries are marker-to-marker, not heading-level
    based, so nested Markdown headings remain ordinary section content. Marker examples inside fenced Markdown code blocks or indented/container code are ignored;
    marker examples inside raw HTML blocks are ignored as well. None of these examples
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
            "allowed only inside fenced Markdown code blocks or raw HTML blocks"
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

    # A replacement body may legitimately contain fenced/raw-HTML examples, but it must
    # not use an unclosed leaf block to swallow later live section markers. Reparse the
    # complete document and require the exact stable section identities/headings to survive.
    rebuilt_spans = parse_sections(rebuilt_content)
    original_structure = [(span.section_id, span.heading) for span in spans]
    rebuilt_structure = [(span.section_id, span.heading) for span in rebuilt_spans]
    if rebuilt_structure != original_structure:
        raise SectionError(
            "section replacement must preserve all existing semantic section markers "
            "and headings"
        )
    return rebuilt_content
