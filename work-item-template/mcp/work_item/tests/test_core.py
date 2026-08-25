from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (
    ConflictError,
    ValidationError,
    create_work_item,
    get_work_item,
    list_work_items,
    new_document,
    update_work_item,
)


class WorkItemCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "state" / "work-items.sqlite3"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create(self, item_id: str = "redmine:116655") -> dict:
        doc = new_document(
            item_id=item_id,
            title="Payment status",
            summary="Initial investigation",
            current_requirements=["Expose paymentStatus on order detail"],
            repositories=["backend-api", "frontend-web"],
        )
        return create_work_item(self.db, doc)

    def test_create_get_and_list(self) -> None:
        created = self._create()
        self.assertEqual(created["revision"], 1)
        self.assertEqual(created["repos"]["backend-api"]["status"], "pending")

        loaded = get_work_item(self.db, "redmine:116655")
        self.assertEqual(loaded["title"], "Payment status")
        self.assertEqual(loaded["revision"], 1)

        rows = list_work_items(self.db, status="active", repository="backend-api")
        self.assertEqual([row["id"] for row in rows], ["redmine:116655"])
        self.assertEqual(rows[0]["repositories"], ["backend-api", "frontend-web"])

    def test_update_captures_question_decision_change_and_repo_state_atomically(self) -> None:
        created = self._create()
        updated = update_work_item(
            self.db,
            created["id"],
            created["revision"],
            {
                "phase": "implementation",
                "current_requirements": [
                    "Expose paymentStatus on order detail",
                    "Expose paymentStatus on order list",
                ],
                "questions": [
                    {
                        "id": "q1",
                        "status": "resolved",
                        "question": "Should the field exist when value is unknown?",
                        "answer": "Yes, return null",
                        "resolved_by": "customer",
                        "decision_id": "d1",
                    }
                ],
                "decisions": [
                    {
                        "id": "d1",
                        "status": "active",
                        "summary": "paymentStatus is always present; unknown is null",
                        "decided_by": "customer",
                    }
                ],
                "changes": [
                    {
                        "id": "c1",
                        "type": "requirement_added",
                        "status": "accepted",
                        "summary": "Expose paymentStatus on order list",
                        "caused_by_decision": "d1",
                    }
                ],
                "repos": {
                    "backend-api": {
                        "status": "done",
                        "summary": "Implementation completed",
                        "verification": ["unit tests passed"],
                    }
                },
                "handoffs": [
                    {
                        "id": "h1",
                        "from": "backend-api",
                        "to": "frontend-web",
                        "status": "pending",
                        "summary": "Consume paymentStatus",
                        "evidence": ["commit abc123"],
                    }
                ],
                "next_actions": [
                    {"repo": "frontend-web", "action": "Consume paymentStatus"}
                ],
                "checkpoints": [
                    {"repo": "backend-api", "summary": "Backend UT passed"}
                ],
            },
        )
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["repos"]["backend-api"]["status"], "done")
        self.assertEqual(updated["repos"]["frontend-web"]["status"], "pending")
        self.assertEqual(updated["decisions"][0]["id"], "d1")
        self.assertEqual(updated["changes"][0]["type"], "requirement_added")

    def test_stale_revision_is_rejected(self) -> None:
        created = self._create()
        update_work_item(
            self.db,
            created["id"],
            created["revision"],
            {"summary": "Backend investigation complete"},
        )
        with self.assertRaises(ConflictError):
            update_work_item(
                self.db,
                created["id"],
                created["revision"],
                {"summary": "Stale write"},
            )

    def test_required_field_cannot_be_removed_by_patch(self) -> None:
        created = self._create()
        with self.assertRaises(ValidationError):
            update_work_item(
                self.db,
                created["id"],
                created["revision"],
                {"current_requirements": None},
            )

    def test_immutable_metadata_cannot_be_patched(self) -> None:
        created = self._create()
        with self.assertRaises(ValidationError):
            update_work_item(
                self.db,
                created["id"],
                created["revision"],
                {"id": "redmine:999"},
            )

    def test_invalid_nested_status_is_rejected(self) -> None:
        created = self._create()
        with self.assertRaises(ValidationError):
            update_work_item(
                self.db,
                created["id"],
                created["revision"],
                {"repos": {"backend-api": {"status": "magic"}}},
            )

    def test_same_id_cannot_be_created_twice(self) -> None:
        self._create()
        with self.assertRaises(ConflictError):
            self._create()

    def test_semantic_objects_require_material_fields(self) -> None:
        created = self._create()
        with self.assertRaises(ValidationError):
            update_work_item(
                self.db,
                created["id"],
                created["revision"],
                {"handoffs": [{"id": "h1", "status": "pending"}]},
            )

    def test_two_writers_from_same_revision_cannot_both_commit(self) -> None:
        created = self._create()
        outcomes: list[str] = []
        barrier = threading.Barrier(2)

        def writer(summary: str) -> None:
            barrier.wait()
            try:
                update_work_item(
                    self.db,
                    created["id"],
                    created["revision"],
                    {"summary": summary},
                )
                outcomes.append("ok")
            except ConflictError:
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
        self.assertEqual(get_work_item(self.db, created["id"])["revision"], 2)


if __name__ == "__main__":
    unittest.main()
