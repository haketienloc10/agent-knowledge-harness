from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import check_store, reindex_store, render_index, write_knowledge  # noqa: E402
from sections import SectionError, parse_sections, read_section, replace_section  # noqa: E402


def entry(*, content: str) -> dict:
    return {
        "canonical_name": "html-block-section-rule",
        "title": "HTML block section rule",
        "scope": {"kind": "domain", "id": "knowledge.sections"},
        "routing": {
            "summary": "Raw HTML marker examples must not become semantic sections.",
            "when_to_read": ["documenting knowledge section marker syntax"],
            "keywords": ["knowledge", "semantic section", "raw html"],
            "aliases": [],
        },
        "content": content,
        "sources": [{"kind": "manual", "locator": "HTML block section regression"}],
    }


def live_tail() -> str:
    return """<!-- knowledge-section:live -->
## Live

Durable body."""


class HtmlBlockSectionParserTest(unittest.TestCase):
    def test_markers_inside_commonmark_html_block_types_are_not_live(self):
        cases = {
            "type1-pre": """<pre>
<!-- knowledge-section:Bad_Id -->
## Example only
</pre>""",
            "type2-comment": """<!-- ordinary HTML comment
<!-- knowledge-section:not-live -->
## Example only
-->""",
            "type3-processing-instruction": """<?example
<!-- knowledge-section:not-live -->
?>""",
            "type4-declaration": """<!DOCTYPE html
<!-- knowledge-section:not-live -->
>""",
            "type5-cdata": """<![CDATA[
<!-- knowledge-section:not-live -->
## Example only
]]>""",
            "type6-block-tag": """<div class
<!-- knowledge-section:not-live -->
## Example only""",
            "type7-complete-tag": """<custom data-kind=example>
<!-- knowledge-section:not-live -->
## Example only""",
        }
        for name, raw_html in cases.items():
            with self.subTest(name=name):
                content = f"{raw_html}\n\n{live_tail()}"
                sections = parse_sections(content)
                self.assertEqual([section.section_id for section in sections], ["live"])
                self.assertEqual(read_section(content, "live")["content"], "Durable body.")

    def test_literal_html_block_can_interrupt_paragraph_but_type7_cannot(self):
        type1 = """Paragraph text.
<pre>
<!-- knowledge-section:not-live -->
## Example only
</pre>
<!-- knowledge-section:live -->
## Live

Durable body."""
        self.assertEqual(
            [section.section_id for section in parse_sections(type1)],
            ["live"],
        )

        type7 = """Paragraph text.
<custom>
<!-- knowledge-section:live -->
## Live

Durable body."""
        self.assertEqual(
            [section.section_id for section in parse_sections(type7)],
            ["live"],
        )

    def test_list_outdent_restores_block_boundary_for_type7_html(self):
        content = """- List paragraph.
<custom>
<!-- knowledge-section:not-live -->
## Example only

<!-- knowledge-section:live -->
## Live

Durable body."""
        self.assertEqual(
            [section.section_id for section in parse_sections(content)],
            ["live"],
        )

    def test_top_level_reserved_marker_keeps_precedence_over_html_comment_syntax(self):
        self.assertEqual(
            [section.section_id for section in parse_sections(live_tail())],
            ["live"],
        )
        with self.assertRaises(SectionError) as raised:
            parse_sections("<!-- knowledge-section:Bad_Id -->\n## Bad\n\nbody")
        self.assertIn("malformed knowledge section marker", str(raised.exception))

    def test_outdent_ends_unclosed_list_html_block_before_outer_live_marker(self):
        content = """- <pre>
  <!-- knowledge-section:not-live -->
  ## Example only
<!-- knowledge-section:live -->
## Live

Durable body."""
        self.assertEqual(
            [section.section_id for section in parse_sections(content)],
            ["live"],
        )

    def test_section_replacement_allows_marker_example_inside_raw_html(self):
        content = """<!-- knowledge-section:contract -->
## Contract

Original.

<!-- knowledge-section:verification -->
## Verification

Verified."""
        replacement = """<pre>
<!-- knowledge-section:illustrative-only -->
## Illustrative only
</pre>"""
        updated = replace_section(content, "contract", replacement)
        self.assertEqual(
            [section.section_id for section in parse_sections(updated)],
            ["contract", "verification"],
        )
        self.assertEqual(read_section(updated, "contract")["content"], replacement)


class HtmlBlockSectionIntegrityTest(unittest.TestCase):
    def test_raw_html_marker_example_is_valid_through_write_check_and_reindex(self):
        content = f"""<pre>
<!-- knowledge-section:Bad_Id -->
## Illustrative only
</pre>

{live_tail()}"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("global", "systems", "repos", "domains"):
                (root / name).mkdir()
            (root / "INDEX.md").write_text(render_index({}), encoding="utf-8")

            write_knowledge(root, [entry(content=content)])
            checked = check_store(root)
            self.assertTrue(checked["ok"], checked["errors"])
            self.assertEqual(reindex_store(root)["documents"], 1)
            self.assertTrue(check_store(root)["ok"])


if __name__ == "__main__":
    unittest.main()
