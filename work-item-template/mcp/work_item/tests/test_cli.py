from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from artifacts import append_artifact_chunk, create_artifact, finalize_artifact
from cli import (
    _artifact_index,
    _artifact_manifest,
    _get_work_item,
    _list_work_items,
    _summarize_work_items,
    main,
    render_artifact_manifest,
    render_detail,
    render_list,
)
from core import create_work_item, get_work_item, new_document, update_work_item


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

    def _create_report(self, item: dict) -> dict:
        artifact = create_artifact(
            self.db,
            item["id"],
            artifact_type="report",
            title="Task review report",
            summary="Review from intake through verification",
            based_on_work_item_revision=item["revision"],
        )
        appended = append_artifact_chunk(
            self.db,
            item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="requirements",
            section_title="Requirement review",
            content="Original requirement understood and covered.\n",
        )
        appended = append_artifact_chunk(
            self.db,
            item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=appended["revision"],
            section_id="verification",
            section_title="Verification",
            content="Unit tests passed.\n",
        )
        return finalize_artifact(
            self.db,
            item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=appended["revision"],
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
        output = render_list(summary, _list_work_items(self.db, limit=50))

        self.assertIn("TOTAL 2", output)
        self.assertIn("ACTIVE 1", output)
        self.assertIn("DONE 1", output)
        self.assertIn("redmine:1", output)
        self.assertIn("redmine:2", output)

    def test_detail_shows_all_major_sections_repo_verification_and_thin_artifacts(self) -> None:
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
        report = self._create_report(updated)

        artifacts = _artifact_index(self.db, created["id"])
        output = render_detail(_get_work_item(self.db, created["id"]), artifacts)

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
            "ARTIFACTS (1)",
        ):
            self.assertIn(heading, output)
        self.assertIn("search_air  [DONE]", output)
        self.assertIn("ant compile passed", output)
        self.assertIn("stress test passed", output)
        self.assertIn("revision=2", output)
        self.assertIn(report["artifact_id"], output)
        self.assertIn("sections=2", output)
        self.assertNotIn("Original requirement understood and covered.", output)

    def test_artifact_manifest_has_outline_but_no_body(self) -> None:
        item = self._create("redmine:22", title="Artifact", repo="repo-a")
        report = self._create_report(item)
        manifest = _artifact_manifest(self.db, item["id"], report["artifact_id"])
        output = render_artifact_manifest(manifest)

        self.assertIn("SECTION MANIFEST (2)", output)
        self.assertIn("requirements", output)
        self.assertIn("verification", output)
        self.assertNotIn("Original requirement understood and covered.", output)
        self.assertNotIn("Unit tests passed.", output)

    def test_artifact_command_streams_full_or_selected_section(self) -> None:
        item = self._create("redmine:23", title="Artifact stream", repo="repo-a")
        report = self._create_report(item)

        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["artifact", item["id"], report["artifact_id"]])
        self.assertEqual(rc, 0)
        self.assertIn("Original requirement understood and covered.", out.getvalue())
        self.assertIn("Unit tests passed.", out.getvalue())

        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(
                [
                    "artifact",
                    item["id"],
                    report["artifact_id"],
                    "--section",
                    "verification",
                ]
            )
        self.assertEqual(rc, 0)
        self.assertNotIn("Original requirement understood and covered.", out.getvalue())
        self.assertIn("Unit tests passed.", out.getvalue())

    def test_list_show_and_artifact_commands_do_not_write_database(self) -> None:
        item = self._create("redmine:9", title="Read only", repo="repo-a")
        report = self._create_report(item)
        before = get_work_item(self.db, item["id"])
        before_mtime = self.db.stat().st_mtime_ns

        for argv in (
            ["list"],
            ["show", item["id"]],
            ["artifact", item["id"], report["artifact_id"], "--manifest"],
            ["artifact", item["id"], report["artifact_id"], "--section", "verification"],
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(argv), 0)

        after_mtime = self.db.stat().st_mtime_ns
        after = get_work_item(self.db, item["id"])
        self.assertEqual(before["revision"], after["revision"])
        self.assertEqual(before_mtime, after_mtime)


if __name__ == "__main__":
    unittest.main()
