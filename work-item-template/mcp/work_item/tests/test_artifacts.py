from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from artifacts import (
    ARTIFACT_APPEND_MAX_BYTES,
    ArtifactConflictError,
    append_artifact_chunk,
    create_artifact,
    finalize_artifact,
    get_artifact,
    get_artifact_index,
    list_artifacts,
    read_artifact_section,
)
from core import (
    ConflictError,
    ValidationError,
    create_work_item,
    get_work_item,
    new_document,
)


class WorkItemArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "work-items.sqlite3"
        self.item = create_work_item(
            self.db,
            new_document(
                item_id="redmine:113387",
                title="CPU 100%",
                summary="Investigate reported infinite loop",
                current_requirements=["Verify root cause before implementation"],
                repositories=["search_air"],
            ),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_artifact(
        self,
        *,
        artifact_type: str = "investigation",
        artifact_id: str | None = None,
    ) -> dict:
        return create_artifact(
            self.db,
            self.item["id"],
            artifact_type=artifact_type,
            title=f"{artifact_type.title()} detail",
            summary="Thin summary",
            based_on_work_item_revision=self.item["revision"],
            artifact_id=artifact_id,
        )

    def test_existing_work_item_db_gains_artifact_tables_without_task_revision_change(self) -> None:
        before = get_work_item(self.db, self.item["id"])
        self.assertEqual(list_artifacts(self.db, self.item["id"]), [])
        after = get_work_item(self.db, self.item["id"])
        self.assertEqual(before["revision"], after["revision"])
        self.assertEqual(before["updated_at"], after["updated_at"])

    def test_create_list_and_get_manifest_without_body(self) -> None:
        artifact = self._create_artifact()
        self.assertEqual(artifact["artifact_id"], "investigation:1")
        self.assertEqual(artifact["state"], "draft")
        self.assertEqual(artifact["revision"], 1)
        self.assertEqual(artifact["section_count"], 0)
        self.assertEqual(artifact["total_bytes"], 0)

        listed = list_artifacts(self.db, self.item["id"])
        self.assertEqual([entry["artifact_id"] for entry in listed], ["investigation:1"])
        self.assertEqual(listed[0]["summary"], "Thin summary")

        manifest = get_artifact(self.db, self.item["id"], artifact["artifact_id"])
        self.assertEqual(manifest["sections"], [])
        self.assertNotIn("content", manifest)

    def test_generated_ids_are_atomic_monotonic_per_type(self) -> None:
        first = self._create_artifact(artifact_type="report")
        second = self._create_artifact(artifact_type="report")
        review = self._create_artifact(artifact_type="review")
        self.assertEqual(first["artifact_id"], "report:1")
        self.assertEqual(second["artifact_id"], "report:2")
        self.assertEqual(review["artifact_id"], "review:1")

    def test_create_rejects_stale_work_item_revision_and_wrong_id_prefix(self) -> None:
        with self.assertRaises(ConflictError):
            create_artifact(
                self.db,
                self.item["id"],
                artifact_type="plan",
                title="Plan",
                summary="",
                based_on_work_item_revision=self.item["revision"] + 1,
            )
        with self.assertRaises(ValidationError):
            create_artifact(
                self.db,
                self.item["id"],
                artifact_type="plan",
                title="Plan",
                summary="",
                based_on_work_item_revision=self.item["revision"],
                artifact_id="report:1",
            )

    def test_append_requires_first_section_title_and_preserves_work_item_revision(self) -> None:
        artifact = self._create_artifact()
        with self.assertRaises(ValidationError):
            append_artifact_chunk(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                expected_artifact_revision=artifact["revision"],
                section_id="evidence",
                content="Evidence A",
            )

        appended = append_artifact_chunk(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="evidence",
            section_title="Evidence",
            content="Evidence A\n",
        )
        self.assertEqual(appended["revision"], 2)
        self.assertEqual(appended["appended"]["chunk_index"], 0)
        self.assertEqual(get_work_item(self.db, self.item["id"])["revision"], self.item["revision"])

    def test_append_rejects_utf8_chunk_over_16_kib(self) -> None:
        artifact = self._create_artifact()
        oversized = "é" * ((ARTIFACT_APPEND_MAX_BYTES // 2) + 1)
        self.assertGreater(len(oversized.encode("utf-8")), ARTIFACT_APPEND_MAX_BYTES)
        with self.assertRaises(ValidationError):
            append_artifact_chunk(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                expected_artifact_revision=artifact["revision"],
                section_id="detail",
                section_title="Detail",
                content=oversized,
            )

    def test_section_title_is_stable_and_stale_artifact_revision_conflicts(self) -> None:
        artifact = self._create_artifact()
        appended = append_artifact_chunk(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="root-cause",
            section_title="Root cause",
            content="chunk-1",
        )
        with self.assertRaises(ArtifactConflictError):
            append_artifact_chunk(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                expected_artifact_revision=artifact["revision"],
                section_id="root-cause",
                content="stale",
            )
        with self.assertRaises(ValidationError):
            append_artifact_chunk(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                expected_artifact_revision=appended["revision"],
                section_id="root-cause",
                section_title="Different title",
                content="chunk-2",
            )

    def test_read_is_cursor_based_and_bounded_to_two_chunks(self) -> None:
        artifact = self._create_artifact()
        revision = artifact["revision"]
        for index, content in enumerate(("A", "B", "C")):
            result = append_artifact_chunk(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                expected_artifact_revision=revision,
                section_id="analysis",
                section_title="Analysis" if index == 0 else None,
                content=content,
            )
            revision = result["revision"]

        first = read_artifact_section(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            "analysis",
            cursor=0,
            limit_chunks=2,
        )
        self.assertEqual(first["content"], "AB")
        self.assertEqual(first["returned_chunks"], 2)
        self.assertEqual(first["next_cursor"], 2)
        self.assertTrue(first["has_more"])

        second = read_artifact_section(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            "analysis",
            cursor=first["next_cursor"],
            limit_chunks=2,
        )
        self.assertEqual(second["content"], "C")
        self.assertIsNone(second["next_cursor"])
        self.assertFalse(second["has_more"])

        with self.assertRaises(ValidationError):
            read_artifact_section(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                "analysis",
                limit_chunks=3,
            )

    def test_finalize_requires_content_and_complete_artifact_is_immutable(self) -> None:
        artifact = self._create_artifact(artifact_type="report")
        with self.assertRaises(ValidationError):
            finalize_artifact(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                expected_artifact_revision=artifact["revision"],
            )

        appended = append_artifact_chunk(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="assessment",
            section_title="Final assessment",
            content="Requirements and verification reviewed.",
        )
        completed = finalize_artifact(
            self.db,
            self.item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=appended["revision"],
            summary="Review complete",
        )
        self.assertEqual(completed["state"], "complete")
        self.assertEqual(completed["summary"], "Review complete")
        self.assertEqual(completed["revision"], appended["revision"] + 1)

        with self.assertRaises(ValidationError):
            append_artifact_chunk(
                self.db,
                self.item["id"],
                artifact["artifact_id"],
                expected_artifact_revision=completed["revision"],
                section_id="assessment",
                content="late mutation",
            )

    def test_artifact_index_is_thin_bounded_and_reports_truncation(self) -> None:
        for artifact_type in ("intake", "investigation", "plan"):
            self._create_artifact(artifact_type=artifact_type)
        index = get_artifact_index(self.db, self.item["id"], limit=2)
        self.assertEqual(index["count"], 3)
        self.assertEqual(len(index["items"]), 2)
        self.assertTrue(index["truncated"])
        self.assertNotIn("summary", index["items"][0])
        self.assertNotIn("sections", index["items"][0])

    def test_two_artifact_writers_from_same_revision_cannot_both_append(self) -> None:
        artifact = self._create_artifact()
        outcomes: list[str] = []
        barrier = threading.Barrier(2)

        def writer(section_id: str) -> None:
            barrier.wait()
            try:
                append_artifact_chunk(
                    self.db,
                    self.item["id"],
                    artifact["artifact_id"],
                    expected_artifact_revision=artifact["revision"],
                    section_id=section_id,
                    section_title=section_id,
                    content=section_id,
                )
                outcomes.append("ok")
            except ArtifactConflictError:
                outcomes.append("conflict")

        threads = [
            threading.Thread(target=writer, args=("writer-a",)),
            threading.Thread(target=writer, args=("writer-b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertCountEqual(outcomes, ["ok", "conflict"])
        self.assertEqual(
            get_artifact(self.db, self.item["id"], artifact["artifact_id"])["revision"],
            2,
        )


if __name__ == "__main__":
    unittest.main()
