from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from cli import _summarize_work_items, main, render_detail, render_list
from core import create_work_item, get_work_item, list_work_items, new_document, update_work_item


class WorkItemCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "work-items.sqlite3"
        self.old_db = os.environ.get("WORK_ITEM_DB_PATH")
        os.environ["WORK_ITEM_DB_PATH"] = str(self.db)

    def tearDown(self) -> None:
        if self.old_db is None:
            os.environ.pop("WORK_ITEM_DB_PATH", None)
        else:
            os.environ["WORK_ITEM_DB_PATH"] = self.old_db
        self.temp.cleanup()

    def _create(self, item_id: str, *, title: str, repo: str) -> dict:
        return create_work_item(
            self.db,
            new_document(
                item_id=item_id,
                title=title,
                summary="Initial investigation",
                current_requirements=["Verify the reported behavior"],
                repositories=[repo],
            ),
        )

    def test_list_shows_total_and_status_counts(self) -> None:
        self._create("redmine:1", title="First ticket", repo="repo-a")
        second = self._create("redmine:2", title="Second ticket", repo="repo-b")
        update_work_item(
            self.db,
            second["id"],
            second["revision"],
            {"status": "done", "phase": "completed"},
        )

        summary = _summarize_work_items(self.db)
        output = render_list(summary, list_work_items(self.db, limit=50))

        self.assertIn("TOTAL 2", output)
        self.assertIn("ACTIVE 1", output)
        self.assertIn("DONE 1", output)
        self.assertIn("redmine:1", output)
        self.assertIn("redmine:2", output)

    def test_detail_shows_all_major_sections_and_repo_verification(self) -> None:
        created = self._create("redmine:113387", title="CPU 100%", repo="search_air")
        updated = update_work_item(
            self.db,
            created["id"],
            created["revision"],
            {
                "repos": {
                    "search_air": {
                        "status": "done",
                        "summary": "Concurrency hazard verified",
                        "verification": ["ant compile passed", "stress test passed"],
                    }
                },
                "next_actions": [
                    {"repo": "search_air", "action": "Review delivery state"}
                ],
                "checkpoints": [
                    {"kind": "verification", "summary": "Patch verification complete"}
                ],
            },
        )

        output = render_detail(updated)

        for heading in (
            "SUMMARY",
            "CURRENT REQUIREMENTS (1)",
            "REPOSITORIES (1)",
            "QUESTIONS (0)",
            "DECISIONS (0)",
            "CHANGES (0)",
            "BLOCKERS (0)",
            "HANDOFFS (0)",
            "NEXT ACTIONS (1)",
            "CHECKPOINTS (1)",
        ):
            self.assertIn(heading, output)
        self.assertIn("search_air  [DONE]", output)
        self.assertIn("ant compile passed", output)
        self.assertIn("stress test passed", output)
        self.assertIn("revision=2", output)

    def test_list_command_does_not_change_revision(self) -> None:
        created = self._create("redmine:9", title="Read only", repo="repo-a")
        before = get_work_item(self.db, created["id"])

        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["list"])

        after = get_work_item(self.db, created["id"])
        self.assertEqual(rc, 0)
        self.assertEqual(before["revision"], after["revision"])
        self.assertIn("WORK ITEMS", out.getvalue())


if __name__ == "__main__":
    unittest.main()
