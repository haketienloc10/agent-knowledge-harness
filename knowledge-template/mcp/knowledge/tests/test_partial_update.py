from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import ConflictError, ValidationError, read_knowledge, render_index, write_knowledge  # noqa: E402
from partial_update import update_knowledge  # noqa: E402
from sections import SectionError, parse_sections, read_section, replace_section  # noqa: E402


def entry(*, content: str) -> dict:
    return {
        "canonical_name": "partial-update-rule",
        "title": "Partial update rule",
        "scope": {"kind": "domain", "id": "knowledge.partial"},
        "routing": {
            "summary": "Large durable knowledge can be updated at semantic scope.",
            "when_to_read": ["editing durable knowledge"],
            "keywords": ["knowledge", "partial update", "semantic section"],
            "aliases": [],
        },
        "content": content,
        "sources": [{"kind": "manual", "locator": "partial update test"}],
    }


def sectioned_content() -> str:
    return """Short durable preamble.

<!-- knowledge-section:contract -->
## Contract

The original contract remains stable.

<!-- knowledge-section:verification -->
## Verification

Run the original verification command."""


class SectionParserTest(unittest.TestCase):
    def test_parse_and_read_sections_use_stable_marker_identity(self):
        sections = parse_sections(sectioned_content())
        self.assertEqual([section.section_id for section in sections], ["contract", "verification"])
        verification = read_section(sectioned_content(), "verification")
        self.assertEqual(verification["heading"], "## Verification")
        self.assertEqual(verification["content"], "Run the original verification command.")

    def test_replace_section_preserves_marker_heading_and_other_section(self):
        updated = replace_section(
            sectioned_content(),
            "verification",
            "Run focused tests.\n\nThen run the full suite.",
        )
        self.assertIn("<!-- knowledge-section:verification -->\n## Verification", updated)
        self.assertIn("The original contract remains stable.", updated)
        self.assertIn("Run focused tests.", updated)
        self.assertNotIn("Run the original verification command.", updated)

    def test_fenced_marker_examples_are_not_live_sections(self):
        content = """Example syntax:

```markdown
<!-- knowledge-section:Bad_Id -->
## This is only an example
```

<!-- knowledge-section:contract -->
## Contract

Live body."""
        sections = parse_sections(content)
        self.assertEqual([section.section_id for section in sections], ["contract"])
        self.assertEqual(read_section(content, "contract")["content"], "Live body.")

    def test_replacement_allows_fenced_marker_examples_without_changing_structure(self):
        replacement = """```markdown
<!-- knowledge-section:illustrative-only -->
## Illustrative only
```"""
        updated = replace_section(sectioned_content(), "contract", replacement)
        self.assertEqual(
            [section.section_id for section in parse_sections(updated)],
            ["contract", "verification"],
        )
        self.assertEqual(read_section(updated, "contract")["content"], replacement)

    def test_replacement_cannot_hide_later_sections_with_unclosed_fence(self):
        with self.assertRaises(SectionError) as raised:
            replace_section(
                sectioned_content(),
                "contract",
                "```markdown\nexample without closing fence",
            )
        self.assertIn("preserve all existing semantic section", str(raised.exception))

    def test_read_and_replace_preserve_markdown_body_whitespace(self):
        content = """<!-- knowledge-section:contract -->
## Contract

    indented_code()
line with hard break  

<!-- knowledge-section:verification -->
## Verification

verified"""
        expected = "    indented_code()\nline with hard break  "
        self.assertEqual(read_section(content, "contract")["content"], expected)
        updated = replace_section(content, "contract", expected)
        self.assertEqual(read_section(updated, "contract")["content"], expected)

    def test_duplicate_malformed_overlong_and_missing_sections_fail(self):
        duplicate = sectioned_content() + "\n\n<!-- knowledge-section:contract -->\n## Again\n\nbody"
        with self.assertRaises(SectionError):
            parse_sections(duplicate)
        with self.assertRaises(SectionError):
            parse_sections("<!-- knowledge-section:Bad_Id -->\n## Bad\n\nbody")
        with self.assertRaises(SectionError):
            parse_sections("<!-- knowledge-section:contract -->\nnot a heading")
        overlong = "a" * 101
        with self.assertRaises(SectionError) as raised:
            parse_sections(
                f"<!-- knowledge-section:{overlong} -->\n## Too long\n\nbody"
            )
        self.assertIn("exceeds 100 characters", str(raised.exception))
        with self.assertRaises(SectionError):
            read_section(sectioned_content(), "not-there")

    def test_section_replacement_cannot_inject_live_structure(self):
        with self.assertRaises(SectionError):
            replace_section(
                sectioned_content(),
                "contract",
                "<!-- knowledge-section:injected -->\n## Injected\n\nbody",
            )


class PartialUpdateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ("global", "systems", "repos", "domains"):
            (self.root / name).mkdir()
        (self.root / "INDEX.md").write_text(render_index({}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        return write_knowledge(self.root, [entry(content=sectioned_content())])["changes"][0]

    def read(self, item_id: str):
        return read_knowledge(self.root, [item_id])["results"][0]

    def test_metadata_patch_does_not_require_or_replace_content(self):
        created = self.create()
        result = update_knowledge(
            self.root,
            created["id"],
            created["revision"],
            {
                "metadata": {
                    "routing": {
                        "summary": "Updated routing summary without resending durable content."
                    }
                }
            },
        )["changes"][0]
        current = self.read(created["id"])
        self.assertNotEqual(result["revision"], created["revision"])
        self.assertEqual(current["content"], sectioned_content())
        self.assertEqual(
            current["routing"]["summary"],
            "Updated routing summary without resending durable content.",
        )
        self.assertEqual(current["routing"]["keywords"], entry(content="x")["routing"]["keywords"])

    def test_whole_content_patch_preserves_metadata(self):
        created = self.create()
        before = self.read(created["id"])
        new_content = "A compact replacement without semantic sections."
        updated = update_knowledge(
            self.root,
            created["id"],
            created["revision"],
            {"content": new_content},
        )["changes"][0]
        after = self.read(updated["id"])
        self.assertEqual(after["content"], new_content)
        self.assertEqual(after["title"], before["title"])
        self.assertEqual(after["scope"], before["scope"])
        self.assertEqual(after["routing"], before["routing"])
        self.assertEqual(after["sources"], before["sources"])

    def test_section_patch_changes_only_existing_section_body(self):
        created = self.create()
        updated = update_knowledge(
            self.root,
            created["id"],
            created["revision"],
            {
                "section": {
                    "id": "verification",
                    "content": "Run focused tests first, then the full suite.",
                }
            },
        )["changes"][0]
        after = self.read(updated["id"])
        contract = read_section(after["content"], "contract")
        verification = read_section(after["content"], "verification")
        self.assertEqual(contract["content"], "The original contract remains stable.")
        self.assertEqual(verification["heading"], "## Verification")
        self.assertEqual(
            verification["content"],
            "Run focused tests first, then the full suite.",
        )

    def test_section_patch_preserves_indented_markdown_body(self):
        created = self.create()
        replacement = "    run_exact_command()\nline with hard break  "
        updated = update_knowledge(
            self.root,
            created["id"],
            created["revision"],
            {"section": {"id": "contract", "content": replacement}},
        )["changes"][0]
        after = self.read(updated["id"])
        self.assertEqual(read_section(after["content"], "contract")["content"], replacement)

    def test_metadata_and_section_can_commit_atomically(self):
        created = self.create()
        updated = update_knowledge(
            self.root,
            created["id"],
            created["revision"],
            {
                "metadata": {"title": "Updated partial rule"},
                "section": {"id": "contract", "content": "Updated contract body."},
            },
        )["changes"][0]
        after = self.read(updated["id"])
        self.assertEqual(after["title"], "Updated partial rule")
        self.assertEqual(read_section(after["content"], "contract")["content"], "Updated contract body.")

    def test_partial_update_rejects_stale_revision(self):
        created = self.create()
        first = update_knowledge(
            self.root,
            created["id"],
            created["revision"],
            {"metadata": {"title": "First update"}},
        )["changes"][0]
        self.assertNotEqual(first["revision"], created["revision"])
        with self.assertRaises(ConflictError):
            update_knowledge(
                self.root,
                created["id"],
                created["revision"],
                {"metadata": {"title": "Stale update"}},
            )

    def test_missing_section_is_not_implicitly_created(self):
        created = self.create()
        with self.assertRaises(ValidationError) as raised:
            update_knowledge(
                self.root,
                created["id"],
                created["revision"],
                {"section": {"id": "new-section", "content": "body"}},
            )
        self.assertIn("does not exist", str(raised.exception))

    def test_full_content_and_section_replacement_are_mutually_exclusive(self):
        created = self.create()
        with self.assertRaises(ValidationError):
            update_knowledge(
                self.root,
                created["id"],
                created["revision"],
                {
                    "content": "replacement",
                    "section": {"id": "contract", "content": "body"},
                },
            )


if __name__ == "__main__":
    unittest.main()
