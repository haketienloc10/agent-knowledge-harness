from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (
    ConflictError,
    ValidationError,
    create_work_item,
    get_work_item_snapshot,
    load_work_item_document,
    new_document,
    read_work_item_history,
    update_work_item,
    validate_document,
)


class WorkItemBoundedReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "work-items.sqlite3"
        doc = new_document(
            item_id="redmine:31",
            title="Bounded history reads",
            summary="Current task truth",
            repositories=["api", "web"],
        )
        self.item = create_work_item(self.db, doc)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _seed_history(self) -> dict:
        questions = [
            {
                "id": f"q{i}",
                "status": "open" if i >= 28 else "resolved",
                "question": f"Question {i}?",
                **({"answer": f"Answer {i}"} if i < 28 else {}),
            }
            for i in range(30)
        ]
        decisions = [
            {
                "id": f"d{i}",
                "status": "active" if i >= 25 else "superseded",
                "summary": f"Decision {i}",
                **({"superseded_by": "d25"} if i < 25 else {}),
            }
            for i in range(30)
        ]
        checkpoints = [
            {
                "repo": "api" if i % 2 == 0 else "web",
                "summary": f"Checkpoint {i}",
                "kind": "verification",
            }
            for i in range(100)
        ]
        return update_work_item(
            self.db,
            self.item["id"],
            self.item["revision"],
            {
                "questions": questions,
                "decisions": decisions,
                "changes": [
                    {
                        "id": f"c{i}",
                        "type": "scope_changed",
                        "status": "accepted",
                        "summary": f"Change {i}",
                    }
                    for i in range(30)
                ],
                "checkpoints": checkpoints,
                "blockers": [
                    {"id": "b1", "status": "resolved", "summary": "Old blocker"},
                    {"id": "b2", "status": "open", "summary": "Current blocker"},
                ],
                "handoffs": [
                    {"id": "h1", "from": "api", "to": "web", "status": "resolved", "summary": "Old handoff"},
                    {"id": "h2", "from": "api", "to": "web", "status": "pending", "summary": "Current handoff"},
                ],
                "next_actions": [{"repo": "web", "action": "Continue implementation"}],
            },
        )

    def test_snapshot_is_current_state_projection_not_full_history(self) -> None:
        before = get_work_item_snapshot(self.db, self.item["id"])
        self._seed_history()
        after = get_work_item_snapshot(self.db, self.item["id"])

        for historical_name in ("questions", "decisions", "changes", "checkpoints", "blockers", "handoffs"):
            self.assertNotIn(historical_name, after)

        self.assertEqual([q["id"] for q in after["open_questions"]], ["q28", "q29"])
        self.assertEqual([d["id"] for d in after["active_decisions"]], [f"d{i}" for i in range(25, 30)])
        self.assertEqual([b["id"] for b in after["open_blockers"]], ["b2"])
        self.assertEqual([h["id"] for h in after["pending_handoffs"]], ["h2"])
        self.assertEqual(after["history"]["checkpoints"], {"total": 100})
        self.assertEqual(after["history"]["questions"], {"total": 30, "current": 2, "hidden": 28})
        self.assertLess(
            len(json.dumps(after, ensure_ascii=False)) - len(json.dumps(before, ensure_ascii=False)),
            2_500,
        )

    def test_history_read_is_single_collection_bounded_and_canonical_order(self) -> None:
        seeded = self._seed_history()
        first = read_work_item_history(
            self.db, seeded["id"], collection="checkpoints", repository="api", limit=7
        )
        self.assertEqual(first["revision"], seeded["revision"])
        self.assertEqual(first["total"], 50)
        self.assertEqual(first["returned"], 7)
        self.assertEqual(
            [item["summary"] for item in first["items"]],
            [f"Checkpoint {i}" for i in range(0, 14, 2)],
        )
        second = read_work_item_history(
            self.db,
            seeded["id"],
            collection="checkpoints",
            repository="api",
            cursor=first["next_cursor"],
            limit=7,
        )
        self.assertEqual(
            [item["summary"] for item in second["items"]],
            [f"Checkpoint {i}" for i in range(14, 28, 2)],
        )

    def test_history_status_filter_is_collection_specific(self) -> None:
        seeded = self._seed_history()
        page = read_work_item_history(
            self.db, seeded["id"], collection="questions", status="resolved", limit=5
        )
        self.assertEqual(page["total"], 28)
        self.assertTrue(all(item["status"] == "resolved" for item in page["items"]))

        with self.assertRaisesRegex(ValidationError, "status filter is not supported"):
            read_work_item_history(self.db, seeded["id"], collection="checkpoints", status="resolved")
        with self.assertRaisesRegex(ValidationError, "repository filter is not supported"):
            read_work_item_history(self.db, seeded["id"], collection="decisions", repository="api")

    def test_history_cursor_is_bound_to_item_query_and_whole_work_item_revision(self) -> None:
        seeded = self._seed_history()
        first = read_work_item_history(
            self.db, seeded["id"], collection="decisions", status="superseded", limit=3
        )
        cursor = first["next_cursor"]
        self.assertIsNotNone(cursor)

        with self.assertRaisesRegex(ValidationError, "does not match collection or filters"):
            read_work_item_history(
                self.db,
                seeded["id"],
                collection="decisions",
                status="active",
                cursor=cursor,
                limit=3,
            )

        other = create_work_item(
            self.db,
            new_document(item_id="redmine:other", title="Other work item"),
        )
        other = update_work_item(
            self.db,
            other["id"],
            other["revision"],
            {
                "decisions": [
                    {
                        "id": f"other-d{i}",
                        "status": "superseded",
                        "summary": f"Other decision {i}",
                        "superseded_by": "other-next",
                    }
                    for i in range(6)
                ]
            },
        )
        self.assertEqual(other["revision"], seeded["revision"])
        with self.assertRaisesRegex(ValidationError, "does not match Work Item"):
            read_work_item_history(
                self.db,
                other["id"],
                collection="decisions",
                status="superseded",
                cursor=cursor,
                limit=3,
            )

        changed = update_work_item(
            self.db, seeded["id"], seeded["revision"], {"summary": "Revision advanced"}
        )
        self.assertEqual(changed["revision"], seeded["revision"] + 1)
        with self.assertRaisesRegex(ConflictError, "history revision conflict"):
            read_work_item_history(
                self.db,
                seeded["id"],
                collection="decisions",
                status="superseded",
                cursor=cursor,
                limit=3,
            )

    def test_canonical_question_and_decision_status_are_required(self) -> None:
        doc = new_document(item_id="redmine:strict", title="Strict lifecycle")
        doc["questions"] = [{"id": "q1", "question": "Missing status?"}]
        with self.assertRaisesRegex(ValidationError, r"questions\[0\]\.status is required"):
            validate_document(doc)

        doc = new_document(item_id="redmine:strict2", title="Strict lifecycle")
        doc["decisions"] = [{"id": "d1", "summary": "Missing status"}]
        with self.assertRaisesRegex(ValidationError, r"decisions\[0\]\.status is required"):
            validate_document(doc)


class LegacyLifecycleMigrationTests(unittest.TestCase):
    def test_legacy_missing_and_null_statuses_are_persisted_once_and_revision_advances(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "legacy.sqlite3"
            conn = sqlite3.connect(db)
            conn.execute(
                """
                CREATE TABLE work_items (
                    id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            document = {
                "id": "redmine:legacy",
                "title": "Legacy",
                "status": "active",
                "phase": "investigation",
                "summary": "",
                "current_requirements": [],
                "questions": [
                    {"id": "q1", "question": "Legacy missing question"},
                    {"id": "q2", "status": None, "question": "Legacy null question"},
                ],
                "decisions": [
                    {"id": "d1", "summary": "Legacy missing decision"},
                    {"id": "d2", "status": None, "summary": "Legacy null decision"},
                ],
                "changes": [],
                "repos": {},
                "blockers": [],
                "handoffs": [],
                "next_actions": [],
                "checkpoints": [],
            }
            conn.execute(
                "INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)",
                (
                    document["id"],
                    7,
                    "active",
                    json.dumps(document),
                    "2026-09-01T00:00:00+00:00",
                    "2026-09-01T00:00:00+00:00",
                ),
            )
            conn.commit()
            conn.close()

            loaded = load_work_item_document(db, "redmine:legacy")
            self.assertEqual(loaded["revision"], 8)
            self.assertEqual([item["status"] for item in loaded["questions"]], ["open", "open"])
            self.assertEqual([item["status"] for item in loaded["decisions"]], ["active", "active"])
            self.assertEqual(load_work_item_document(db, "redmine:legacy")["revision"], 8)


if __name__ == "__main__":
    unittest.main()
