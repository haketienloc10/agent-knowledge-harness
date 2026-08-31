from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (  # noqa: E402
    check_store,
    init_store,
    reindex_store,
    write_knowledge,
)
from sections import SectionError, parse_sections, read_section, replace_section  # noqa: E402


def entry(*, name: str, content: str) -> dict:
    return {
        "canonical_name": name,
        "title": f"Heading regression {name}",
        "scope": {"kind": "domain", "id": "knowledge.sections"},
        "routing": {
            "summary": "Section heading whitespace remains compatible with Markdown ATX rules.",
            "when_to_read": ["validating semantic section headings"],
            "keywords": ["knowledge", "semantic section", "markdown heading"],
            "aliases": [],
        },
        "content": content,
        "sources": [{"kind": "manual", "locator": "review 5058125369 regression"}],
    }


class InitStoreIdempotenceTest(unittest.TestCase):
    def test_init_store_can_be_rerun_without_replacing_existing_store_material(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "store"
            first = init_store(root)
            self.assertEqual(first["index_path"], "INDEX.md")

            index_path = root / "INDEX.md"
            original_index = index_path.read_bytes()
            sentinel = root / "domains" / "existing-material.txt"
            sentinel.write_text("preserve me", encoding="utf-8")

            second = init_store(root)
            third = init_store(root)

            self.assertEqual(second, first)
            self.assertEqual(third, first)
            self.assertEqual(index_path.read_bytes(), original_index)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")
            for namespace in ("global", "systems", "repos", "domains"):
                self.assertTrue((root / namespace).is_dir())


class SectionHeadingWhitespaceTest(unittest.TestCase):
    def test_valid_atx_heading_whitespace_is_accepted_and_preserved_exactly(self):
        cases = {
            "leading-spaces": "   ## Contract",
            "tab-separator": "##\tContract",
            "three-spaces-tab": "   ###\tVerification",
        }
        for name, heading in cases.items():
            with self.subTest(name=name):
                content = (
                    "<!-- knowledge-section:contract -->\n"
                    f"{heading}\n\n"
                    "Durable body."
                )
                sections = parse_sections(content)
                self.assertEqual([section.section_id for section in sections], ["contract"])
                self.assertEqual(sections[0].heading, heading)
                self.assertEqual(read_section(content, "contract")["heading"], heading)

                replaced = replace_section(content, "contract", "Updated durable body.")
                self.assertEqual(parse_sections(replaced)[0].heading, heading)
                self.assertEqual(read_section(replaced, "contract")["content"], "Updated durable body.")

    def test_heading_whitespace_boundary_stays_strict(self):
        invalid_headings = (
            "    ## Four-space indented code",
            "##No separator",
            "####### Too many hashes",
        )
        for heading in invalid_headings:
            with self.subTest(heading=heading):
                content = (
                    "<!-- knowledge-section:contract -->\n"
                    f"{heading}\n\n"
                    "Body."
                )
                with self.assertRaises(SectionError) as raised:
                    parse_sections(content)
                self.assertIn("Markdown H2-H6 heading", str(raised.exception))

    def test_valid_heading_whitespace_survives_canonical_store_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "store"
            init_store(root)
            entries = [
                entry(
                    name="leading-space-heading",
                    content=(
                        "<!-- knowledge-section:contract -->\n"
                        "   ## Contract\n\n"
                        "Leading-space heading."
                    ),
                ),
                entry(
                    name="tab-heading",
                    content=(
                        "<!-- knowledge-section:verification -->\n"
                        "##\tVerification\n\n"
                        "Tab-separated heading."
                    ),
                ),
            ]
            write_knowledge(root, entries)
            checked = check_store(root)
            self.assertTrue(checked["ok"], checked["errors"])
            self.assertEqual(reindex_store(root)["documents"], 2)
            self.assertTrue(check_store(root)["ok"])


if __name__ == "__main__":
    unittest.main()
