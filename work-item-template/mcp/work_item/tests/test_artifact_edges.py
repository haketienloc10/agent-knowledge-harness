from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from artifacts import append_artifact, create_artifact, list_artifacts, read_artifact_section
from core import NotFoundError, create_work_item, new_document


class WorkItemArtifactEdgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "work-items.sqlite3"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_artifact_tool_can_be_first_call_on_new_database(self) -> None:
        with self.assertRaises(NotFoundError):
            list_artifacts(self.db, "redmine:1")
        self.assertTrue(self.db.is_file())

    def test_chunk_content_preserves_leading_and_trailing_whitespace_exactly(self) -> None:
        item = create_work_item(
            self.db,
            new_document(item_id="redmine:2", title="Whitespace artifact"),
        )
        artifact = create_artifact(
            self.db,
            item["id"],
            artifact_type="report",
            title="Formatting report",
            summary="Preserve Markdown/code formatting",
            based_on_work_item_revision=item["revision"],
        )
        original = "\n  ```java\n    int x = 1;\n  ```\n\n"
        artifact = append_artifact(
            self.db,
            item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="code-review",
            section_title="Code review",
            content=original,
        )
        read = read_artifact_section(
            self.db,
            item["id"],
            artifact["artifact_id"],
            section_id="code-review",
        )
        self.assertEqual(read["content"], original)
        self.assertEqual(read["returned_bytes"], len(original.encode("utf-8")))


if __name__ == "__main__":
    unittest.main()
