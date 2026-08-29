from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (  # noqa: E402
    check_store,
    init_store,
    read_knowledge,
    reindex_store,
    write_knowledge,
)
from sections import parse_sections, read_section, replace_section  # noqa: E402


def create_entry(content: str) -> dict:
    return {
        "canonical_name": "review-line-boundaries",
        "title": "Review line boundaries",
        "scope": {"kind": "domain", "id": "knowledge.review"},
        "routing": {
            "summary": "Section parsing follows Markdown block and line-boundary semantics.",
            "when_to_read": ["reviewing semantic Knowledge section parsing"],
            "keywords": ["knowledge", "markdown", "section", "boundary"],
            "aliases": [],
        },
        "content": content,
        "sources": [
            {
                "kind": "repo",
                "locator": "agent-knowledge-harness:knowledge-template/mcp/knowledge/sections.py",
                "ref": "review-5058234594",
            }
        ],
    }


class Review5058234594Test(unittest.TestCase):
    def test_setext_heading_reopens_type7_html_block_boundary(self):
        content = "\n".join(
            [
                "Title",
                "-----",
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

        spans = parse_sections(content)
        self.assertEqual([span.section_id for span in spans], ["real"])
        self.assertEqual(read_section(content, "real")["content"], "real body")

        replaced = replace_section(content, "real", "updated body")
        self.assertIn(
            "<custom-element>\n<!-- knowledge-section:example -->\n## Example\n"
            "example body\n</custom-element>",
            replaced,
        )
        self.assertEqual(read_section(replaced, "real")["content"], "updated body")

    def test_standalone_equals_line_does_not_fake_a_setext_boundary(self):
        content = "\n".join(
            [
                "===",
                "<custom-element>",
                "<!-- knowledge-section:still-live -->",
                "## Still live",
                "body",
            ]
        )

        # A Setext underline needs preceding paragraph content. Standalone `===` is
        # ordinary paragraph text, so the following type-7 tag cannot interrupt it and
        # therefore cannot hide the reserved marker that follows.
        spans = parse_sections(content)
        self.assertEqual([span.section_id for span in spans], ["still-live"])

    def test_unicode_text_separators_are_not_markdown_line_endings(self):
        for separator in ("\u2028", "\x85", "\f"):
            with self.subTest(separator=repr(separator)):
                inline_example = (
                    f"prefix{separator}<!-- knowledge-section:inline -->"
                    f"{separator}## Inline"
                )
                content = (
                    inline_example
                    + "\n\n<!-- knowledge-section:real -->\n## Real\nreal body"
                )

                spans = parse_sections(content)
                self.assertEqual([span.section_id for span in spans], ["real"])

                replaced = replace_section(content, "real", "updated body")
                self.assertTrue(replaced.startswith(inline_example))
                self.assertIn(separator, replaced)
                self.assertEqual(
                    read_section(replaced, "real")["content"], "updated body"
                )

    def test_canonical_write_read_preserves_unicode_text_separators(self):
        for separator in ("\u2028", "\x85", "\f"):
            with self.subTest(separator=repr(separator)):
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    init_store(root)
                    inline_example = (
                        f"prefix{separator}<!-- knowledge-section:inline -->"
                        f"{separator}## Inline"
                    )
                    content = (
                        inline_example
                        + "\n\n<!-- knowledge-section:real -->\n## Real\nreal body"
                    )
                    created = write_knowledge(root, [create_entry(content)])["changes"][0]

                    reread = read_knowledge(root, [created["id"]])["results"][0]
                    self.assertEqual(reread["content"], content)
                    self.assertEqual(
                        [span.section_id for span in parse_sections(reread["content"])],
                        ["real"],
                    )
                    checked = check_store(root)
                    self.assertTrue(checked["ok"], checked["errors"])
                    reindexed = reindex_store(root)
                    self.assertEqual(reindexed["documents"], 1)

    def test_cr_lf_and_crlf_remain_markdown_line_boundaries(self):
        for line_ending in ("\n", "\r", "\r\n"):
            with self.subTest(line_ending=repr(line_ending)):
                content = line_ending.join(
                    [
                        "<!-- knowledge-section:first -->",
                        "## First",
                        "body",
                        "",
                        "<!-- knowledge-section:second -->",
                        "## Second",
                        "body",
                    ]
                )
                self.assertEqual(
                    [span.section_id for span in parse_sections(content)],
                    ["first", "second"],
                )


if __name__ == "__main__":
    unittest.main()
