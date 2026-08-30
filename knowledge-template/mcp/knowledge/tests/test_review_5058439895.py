from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import init_store, read_knowledge, write_knowledge  # noqa: E402
from partial_update import update_knowledge  # noqa: E402
from sections import parse_sections, read_section  # noqa: E402


def create_entry(content: str) -> dict:
    return {
        "canonical_name": "review-block-boundaries",
        "title": "Review block boundaries",
        "scope": {"kind": "domain", "id": "knowledge.review"},
        "routing": {
            "summary": "Marker scanning follows CommonMark block-boundary precedence.",
            "when_to_read": ["reviewing semantic Knowledge block-boundary parsing"],
            "keywords": ["knowledge", "markdown", "section", "block boundary"],
            "aliases": [],
        },
        "content": content,
        "sources": [
            {
                "kind": "repo",
                "locator": "agent-knowledge-harness:knowledge-template/mcp/knowledge/sections.py",
                "ref": "review-5058439895",
            }
        ],
    }


class Review5058439895Test(unittest.TestCase):
    def test_type1_html_intentionally_accepts_any_literal_end_tag(self):
        content = "\n".join(
            [
                "<script>",
                "</pre>",
                "<!-- knowledge-section:real -->",
                "## Real",
                "body",
            ]
        )

        # CommonMark type-1 HTML blocks end on any literal-content end tag; the end tag
        # intentionally need not match the opener. The review suggestion to require a
        # matching </script> would therefore hide this real section incorrectly.
        self.assertEqual(
            [span.section_id for span in parse_sections(content)],
            ["real"],
        )

    def test_thematic_break_wins_over_list_item_before_unclosed_fence(self):
        content = "\n".join(
            [
                "- - -",
                "  ```markdown",
                "  <!-- knowledge-section:example -->",
                "  ## Example",
                "<!-- knowledge-section:not-live -->",
                "## Not live",
            ]
        )

        # `- - -` is a thematic break, not a list item. The two-space fence is therefore
        # top-level and remains open through EOF, so no marker inside it is live.
        self.assertEqual(parse_sections(content), [])

    def test_empty_bullet_item_tracks_w_plus_one_continuation_indent(self):
        for marker in ("-", "-   "):
            with self.subTest(marker=repr(marker)):
                content = "\n".join(
                    [
                        marker,
                        "  ```markdown",
                        "  <!-- knowledge-section:example -->",
                        "  ## Example",
                        "<!-- knowledge-section:real -->",
                        "## Real",
                        "body",
                    ]
                )
                self.assertEqual(
                    [span.section_id for span in parse_sections(content)],
                    ["real"],
                )

    def test_empty_ordered_item_uses_marker_width_plus_one(self):
        three_space_continuation = "\n".join(
            [
                "1.",
                "   ```markdown",
                "   <!-- knowledge-section:example -->",
                "   ## Example",
                "<!-- knowledge-section:real -->",
                "## Real",
                "body",
            ]
        )
        self.assertEqual(
            [span.section_id for span in parse_sections(three_space_continuation)],
            ["real"],
        )

        two_space_top_level_fence = "\n".join(
            [
                "1.",
                "  ```markdown",
                "  <!-- knowledge-section:example -->",
                "  ## Example",
                "<!-- knowledge-section:not-live -->",
                "## Not live",
            ]
        )
        self.assertEqual(parse_sections(two_space_top_level_fence), [])

    def test_empty_list_item_does_not_interrupt_open_paragraph(self):
        content = "\n".join(
            [
                "paragraph",
                "-",
                "  ```markdown",
                "  <!-- knowledge-section:example -->",
                "  ## Example",
                "<!-- knowledge-section:not-live -->",
                "## Not live",
            ]
        )

        # The empty `-` cannot interrupt the open paragraph. The following two-space
        # fence is therefore top-level, so it remains open and hides later marker text.
        self.assertEqual(parse_sections(content), [])

    def test_link_reference_definition_allows_following_type7_html_block(self):
        content = "\n".join(
            [
                "[foo]: /url",
                "<custom-element>",
                "<!-- knowledge-section:example -->",
                "## Example",
                "example body",
                "</custom-element>",
                "",
                "<!-- knowledge-section:real -->",
                "## Real",
                "real body",
            ]
        )

        self.assertEqual(
            [span.section_id for span in parse_sections(content)],
            ["real"],
        )
        self.assertEqual(read_section(content, "real")["content"], "real body")

    def test_invalid_link_reference_text_does_not_fake_block_boundary(self):
        for invalid_reference in ("[foo]: foo)", "[foo]: (foo", "[foo]: /url extra"):
            with self.subTest(invalid_reference=invalid_reference):
                content = "\n".join(
                    [
                        invalid_reference,
                        "<custom-element>",
                        "<!-- knowledge-section:real -->",
                        "## Real",
                        "body",
                    ]
                )

                # Invalid reference-like text is an ordinary paragraph. Type-7 HTML
                # cannot interrupt it, so the reserved HTML-comment marker remains live.
                self.assertEqual(
                    [span.section_id for span in parse_sections(content)],
                    ["real"],
                )

    def test_nonparagraph_blockquote_end_allows_following_type7_html(self):
        content = "\n".join(
            [
                "> # Heading",
                "<custom-element>",
                "<!-- knowledge-section:example -->",
                "## Example",
                "example body",
                "</custom-element>",
                "",
                "<!-- knowledge-section:real -->",
                "## Real",
                "real body",
            ]
        )

        self.assertEqual(
            [span.section_id for span in parse_sections(content)],
            ["real"],
        )

    def test_ordinary_blockquote_paragraph_keeps_lazy_continuation_semantics(self):
        content = "\n".join(
            [
                "> paragraph",
                "<custom-element>",
                "<!-- knowledge-section:real -->",
                "## Real",
                "body",
            ]
        )

        # A type-7 tag cannot interrupt the quoted paragraph, so the tag remains lazy
        # paragraph continuation. The reserved HTML-comment marker can interrupt it and
        # must stay live rather than being swallowed as part of a false HTML block.
        self.assertEqual(
            [span.section_id for span in parse_sections(content)],
            ["real"],
        )

    def test_indented_quoted_line_cannot_interrupt_open_quote_paragraph(self):
        content = "\n".join(
            [
                "> paragraph",
                ">     continuation",
                "<custom-element>",
                "<!-- knowledge-section:real -->",
                "## Real",
                "body",
            ]
        )

        self.assertEqual(
            [span.section_id for span in parse_sections(content)],
            ["real"],
        )

    def test_indented_line_cannot_interrupt_open_paragraph(self):
        content = "\n".join(
            [
                "paragraph",
                "    continuation",
                "<custom-element>",
                "<!-- knowledge-section:real -->",
                "## Real",
                "body",
            ]
        )

        self.assertEqual(
            [span.section_id for span in parse_sections(content)],
            ["real"],
        )

    def test_partial_update_preserves_false_marker_inside_type7_html(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            init_store(root)
            content = "\n".join(
                [
                    "[foo]: /url",
                    "<custom-element>",
                    "<!-- knowledge-section:example -->",
                    "## Example",
                    "example body",
                    "</custom-element>",
                    "",
                    "<!-- knowledge-section:real -->",
                    "## Real",
                    "real body",
                ]
            )
            created = write_knowledge(root, [create_entry(content)])["changes"][0]

            updated = update_knowledge(
                root,
                created["id"],
                created["revision"],
                {"section": {"id": "real", "content": "updated body"}},
            )["changes"][0]
            reread = read_knowledge(root, [updated["id"]])["results"][0]

            self.assertIn(
                "<custom-element>\n<!-- knowledge-section:example -->\n## Example\n"
                "example body\n</custom-element>",
                reread["content"],
            )
            self.assertEqual(
                [span.section_id for span in parse_sections(reread["content"])],
                ["real"],
            )
            self.assertEqual(
                read_section(reread["content"], "real")["content"],
                "updated body",
            )


if __name__ == "__main__":
    unittest.main()
