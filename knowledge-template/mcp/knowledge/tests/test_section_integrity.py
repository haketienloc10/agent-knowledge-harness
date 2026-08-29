from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (  # noqa: E402
    MAX_CONTENT_CHARS,
    MAX_DOCUMENT_BYTES,
    ValidationError,
    check_store,
    reindex_store,
    render_index,
    write_knowledge,
)
from sections import MAX_SECTION_BODY_CHARS  # noqa: E402


def entry(*, content: str) -> dict:
    return {
        "canonical_name": "section-integrity-rule",
        "title": "Section integrity rule",
        "scope": {"kind": "domain", "id": "knowledge.sections"},
        "routing": {
            "summary": "Semantic section structure must stay valid across all store paths.",
            "when_to_read": ["editing structured durable knowledge"],
            "keywords": ["knowledge", "semantic section", "integrity"],
            "aliases": [],
        },
        "content": content,
        "sources": [{"kind": "manual", "locator": "section integrity test"}],
    }


VALID_CONTENT = """<!-- knowledge-section:contract -->
## Contract

Stable body."""


class KnowledgeSectionIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ("global", "systems", "repos", "domains"):
            (self.root / name).mkdir()
        (self.root / "INDEX.md").write_text(render_index({}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_core_write_rejects_malformed_reserved_marker_before_mutation(self):
        malformed = "<!-- knowledge-section:Bad_Id -->\n## Bad\n\nbody"
        with self.assertRaises(ValidationError) as raised:
            write_knowledge(self.root, [entry(content=malformed)])
        self.assertIn("malformed knowledge section marker", str(raised.exception))
        self.assertEqual(list((self.root / "domains").rglob("*.md")), [])

    def test_core_write_rejects_heading_beyond_public_schema_bound(self):
        overlong_heading = "## " + ("x" * 298)
        with self.assertRaises(ValidationError) as raised:
            write_knowledge(
                self.root,
                [
                    entry(
                        content=(
                            "<!-- knowledge-section:contract -->\n"
                            f"{overlong_heading}\n\nbody"
                        )
                    )
                ],
            )
        self.assertIn("heading exceeds 300 characters", str(raised.exception))
        self.assertEqual(list((self.root / "domains").rglob("*.md")), [])

    def test_check_and_reindex_reject_malformed_human_edited_section_structure(self):
        created = write_knowledge(self.root, [entry(content=VALID_CONTENT)])["changes"][0]
        path = self.root / created["path"]
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                "<!-- knowledge-section:contract -->",
                "<!-- knowledge-section:Bad_Id -->",
            ),
            encoding="utf-8",
        )

        checked = check_store(self.root)
        self.assertFalse(checked["ok"])
        self.assertTrue(
            any("malformed knowledge section marker" in error for error in checked["errors"]),
            checked["errors"],
        )
        with self.assertRaises(ValidationError) as raised:
            reindex_store(self.root)
        self.assertIn("malformed knowledge section marker", str(raised.exception))

    def test_check_and_reindex_reject_human_edited_section_beyond_read_bound(self):
        created = write_knowledge(self.root, [entry(content=VALID_CONTENT)])["changes"][0]
        path = self.root / created["path"]
        text = path.read_text(encoding="utf-8")
        oversized = (
            "<!-- knowledge-section:contract -->\n"
            "## Contract\n\n"
            + ("x" * (MAX_SECTION_BODY_CHARS + 1))
        )
        path.write_text(text.replace(VALID_CONTENT, oversized), encoding="utf-8")
        self.assertLess(path.stat().st_size, MAX_DOCUMENT_BYTES)

        checked = check_store(self.root)
        self.assertFalse(checked["ok"])
        self.assertTrue(
            any("content exceeds 24000 characters" in error for error in checked["errors"]),
            checked["errors"],
        )
        with self.assertRaises(ValidationError) as raised:
            reindex_store(self.root)
        self.assertIn("content exceeds 24000 characters", str(raised.exception))

    def test_check_and_reindex_reject_total_content_beyond_write_bound(self):
        created = write_knowledge(self.root, [entry(content=VALID_CONTENT)])["changes"][0]
        path = self.root / created["path"]
        text = path.read_text(encoding="utf-8")
        body_size = MAX_CONTENT_CHARS // 2
        oversized = (
            "<!-- knowledge-section:first -->\n"
            "## First\n\n"
            + ("a" * body_size)
            + "\n\n<!-- knowledge-section:second -->\n"
            "## Second\n\n"
            + ("b" * body_size)
        )
        self.assertLess(body_size, MAX_SECTION_BODY_CHARS)
        self.assertGreater(len(oversized), MAX_CONTENT_CHARS)
        path.write_text(text.replace(VALID_CONTENT, oversized), encoding="utf-8")
        self.assertLess(path.stat().st_size, MAX_DOCUMENT_BYTES)

        checked = check_store(self.root)
        self.assertFalse(checked["ok"])
        self.assertTrue(
            any("content exceeds 24000 characters" in error for error in checked["errors"]),
            checked["errors"],
        )
        with self.assertRaises(ValidationError) as raised:
            reindex_store(self.root)
        self.assertIn("content exceeds 24000 characters", str(raised.exception))

    def test_fenced_marker_example_is_valid_through_core_integrity_paths(self):
        content = """```markdown
<!-- knowledge-section:Bad_Id -->
## Illustrative marker only
```

<!-- knowledge-section:contract -->
## Contract

Stable body."""
        write_knowledge(self.root, [entry(content=content)])
        checked = check_store(self.root)
        self.assertTrue(checked["ok"], checked["errors"])
        reindexed = reindex_store(self.root)
        self.assertEqual(reindexed["documents"], 1)
        self.assertTrue(check_store(self.root)["ok"])

    def test_list_nested_fenced_marker_example_is_valid_through_integrity_paths(self):
        content = """- Example marker syntax:
  ```markdown
  <!-- knowledge-section:Bad_Id -->
  ## Illustrative marker only
  ```

<!-- knowledge-section:contract -->
## Contract

Stable body."""
        write_knowledge(self.root, [entry(content=content)])
        checked = check_store(self.root)
        self.assertTrue(checked["ok"], checked["errors"])
        reindexed = reindex_store(self.root)
        self.assertEqual(reindexed["documents"], 1)
        self.assertTrue(check_store(self.root)["ok"])


if __name__ == "__main__":
    unittest.main()
