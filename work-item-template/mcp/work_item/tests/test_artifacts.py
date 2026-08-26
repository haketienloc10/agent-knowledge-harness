from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from artifacts import (
    ARTIFACT_CHUNK_MAX_BYTES,
    ArtifactConflictError,
    append_artifact,
    create_artifact,
    finalize_artifact,
    get_artifact,
    list_artifacts,
    read_artifact_section,
)
from core import ConflictError, ValidationError, create_work_item, get_work_item, new_document, update_work_item


class WorkItemArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "work-items.sqlite3"
        self.item = create_work_item(
            self.db,
            new_document(
                item_id="redmine:113387",
                title="Artifact test",
                summary="Test progressive artifact storage",
                current_requirements=["Keep Work Item state lightweight"],
                repositories=["search_air"],
            ),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_artifact(self, *, artifact_type: str = "investigation") -> dict:
        return create_artifact(
            self.db,
            self.item["id"],
            artifact_type=artifact_type,
            title="Detailed investigation",
            summary="Thin artifact summary",
            based_on_work_item_revision=self.item["revision"],
        )

    def test_create_list_get_manifest_without_body(self) -> None:
        artifact = self._create_artifact()
        self.assertEqual(artifact["artifact_id"], "investigation:1")
        self.assertEqual(artifact["state"], "draft")
        self.assertEqual(artifact["revision"], 1)
        self.assertEqual(artifact["sections"], [])

        artifact = append_artifact(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="evidence",
            section_title="Evidence",
            content="Source evidence lives here.",
        )

        listed = list_artifacts(self.db, self.item["id"])
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["section_count"], 1)
        self.assertNotIn("content", listed[0])

        manifest = get_artifact(self.db, self.item["id"], artifact["artifact_id"])
        self.assertEqual(manifest["sections"][0]["section_id"], "evidence")
        self.assertEqual(manifest["sections"][0]["chunk_count"], 1)
        self.assertNotIn("content", manifest["sections"][0])

    def test_artifact_revision_is_independent_from_work_item_revision(self) -> None:
        before = get_work_item(self.db, self.item["id"])
        artifact = self._create_artifact()
        artifact = append_artifact(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="analysis",
            section_title="Analysis",
            content="A" * 100,
        )
        artifact = append_artifact(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="analysis",
            content="B" * 100,
        )
        after = get_work_item(self.db, self.item["id"])

        self.assertEqual(before["revision"], after["revision"])
        self.assertEqual(artifact["revision"], 3)

    def test_stale_artifact_revision_is_rejected(self) -> None:
        artifact = self._create_artifact()
        append_artifact(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=1,
            section_id="analysis",
            section_title="Analysis",
            content="writer one",
        )
        with self.assertRaises(ArtifactConflictError):
            append_artifact(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                expected_artifact_revision=1,
                section_id="analysis",
                content="stale writer",
            )

    def test_create_requires_exact_current_work_item_revision(self) -> None:
        update_work_item(
            self.db,
            self.item["id"],
            self.item["revision"],
            {"summary": "Work Item moved forward"},
        )
        with self.assertRaises(ConflictError):
            self._create_artifact()

    def test_append_limit_is_utf8_bytes_not_character_count(self) -> None:
        artifact = self._create_artifact()
        too_large = "é" * (ARTIFACT_CHUNK_MAX_BYTES // 2 + 1)
        self.assertLessEqual(len(too_large), ARTIFACT_CHUNK_MAX_BYTES)
        self.assertGreater(len(too_large.encode("utf-8")), ARTIFACT_CHUNK_MAX_BYTES)
        with self.assertRaises(ValidationError):
            append_artifact(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                expected_artifact_revision=artifact["revision"],
                section_id="analysis",
                section_title="Analysis",
                content=too_large,
            )

    def test_bounded_read_uses_cursor_without_splitting_utf8_character(self) -> None:
        artifact = self._create_artifact()
        artifact = append_artifact(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="analysis",
            section_title="Analysis",
            content="abcéfg",
        )
        artifact = append_artifact(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="analysis",
            content="HIJ",
        )

        first = read_artifact_section(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            section_id="analysis",
            limit_bytes=5,
        )
        self.assertEqual(first["content"], "abcé")
        self.assertEqual(first["returned_bytes"], 5)
        self.assertIsNotNone(first["next_cursor"])

        second = read_artifact_section(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            section_id="analysis",
            cursor=first["next_cursor"],
            limit_bytes=32,
        )
        self.assertEqual(second["content"], "fgHIJ")
        self.assertIsNone(second["next_cursor"])

    def test_finalize_requires_content_and_makes_artifact_immutable(self) -> None:
        empty = self._create_artifact(artifact_type="report")
        with self.assertRaises(ValidationError):
            finalize_artifact(
                self.db,
                self.item["id"],
                empty["artifact_id"],
                expected_artifact_revision=empty["revision"],
            )

        artifact = append_artifact(
            self.db,
            self.item["id"],
            empty["artifact_id"],
            expected_artifact_revision=empty["revision"],
            section_id="assessment",
            section_title="Final assessment",
            content="Complete report content.",
        )
        artifact = finalize_artifact(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
        )
        self.assertEqual(artifact["state"], "complete")
        with self.assertRaises(ArtifactConflictError):
            append_artifact(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                expected_artifact_revision=artifact["revision"],
                section_id="assessment",
                content="late mutation",
            )


if __name__ == "__main__":
    unittest.main()
