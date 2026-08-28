from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from artifacts import append_artifact, create_artifact, finalize_artifact
from cli import (
    _get_work_item,
    _list_work_items,
    _summarize_work_items,
    main,
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

    def _create_report(self, item_id: str = "redmine:77") -> tuple[dict, dict]:
        created = self._create(item_id, title="Artifact UX", repo="repo-a")
        artifact = create_artifact(
            self.db,
            created["id"],
            artifact_type="report",
            title="Final report",
            summary="Review from requirement through verification",
            based_on_work_item_revision=created["revision"],
        )
        artifact = append_artifact(
            self.db,
            created["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="requirements",
            section_title="Requirement review",
            content="Detailed requirement evidence that should not appear in thin show output.",
        )
        artifact = append_artifact(
            self.db,
            created["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="requirements",
            content="\nSecond stored chunk.",
        )
        artifact = finalize_artifact(
            self.db,
            created["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
        )
        return created, artifact

    def _create_redmine_raw_report(
        self, item_id: str = "redmine:112665"
    ) -> tuple[dict, dict]:
        created = self._create(item_id, title="Redmine raw report", repo="sgapi")
        artifact = create_artifact(
            self.db,
            created["id"],
            artifact_type="report",
            title="Redmine report",
            summary="Diagnostic summary must not appear in raw output",
            based_on_work_item_revision=created["revision"],
        )
        artifact = append_artifact(
            self.db,
            created["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="root-cause-requirement",
            section_title="h3. +1. Root-cause/requirement:+",
            content="p((. *Yêu cầu:* predicate isCo",
        )
        artifact = append_artifact(
            self.db,
            created["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="root-cause-requirement",
            content="mbiCarrier.\n",
        )
        artifact = append_artifact(
            self.db,
            created["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="solution",
            section_title="h3. +2. Solution:+",
            content="* Apply verified fix.",
        )
        artifact = finalize_artifact(
            self.db,
            created["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
        )
        return created, artifact

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

    def test_detail_shows_all_major_sections_and_repo_verification(self) -> None:
        created = self._create("redmine:113387", title="CPU 100%", repo="search_air")
        update_work_item(
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

        item = _get_work_item(self.db, created["id"])
        item["artifacts"] = []
        output = render_detail(item)

        for heading in (
            "SUMMARY",
            "CURRENT REQUIREMENTS (1)",
            "REPOSITORIES (1)",
            "ARTIFACTS (0)",
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

    def test_show_has_thin_index_and_text_artifact_streams_full_content(self) -> None:
        created, artifact = self._create_report()

        show_out = io.StringIO()
        with redirect_stdout(show_out):
            show_rc = main(["show", created["id"]])
        self.assertEqual(show_rc, 0)
        self.assertIn("ARTIFACTS (1)", show_out.getvalue())
        self.assertIn("report:1", show_out.getvalue())
        self.assertNotIn("Detailed requirement evidence", show_out.getvalue())

        artifact_out = io.StringIO()
        with patch(
            "cli._get_artifact_json_readonly",
            side_effect=AssertionError("text mode must not materialize full artifact JSON"),
        ):
            with redirect_stdout(artifact_out):
                artifact_rc = main(["artifact", created["id"], artifact["artifact_id"]])
        self.assertEqual(artifact_rc, 0)
        self.assertIn("Requirement review", artifact_out.getvalue())
        self.assertIn("Detailed requirement evidence", artifact_out.getvalue())
        self.assertIn("Second stored chunk", artifact_out.getvalue())

    def test_raw_artifact_stream_is_copy_paste_ready_and_hides_chunk_boundaries(self) -> None:
        created, artifact = self._create_redmine_raw_report()
        raw_out = io.StringIO()
        with patch(
            "cli._get_artifact_json_readonly",
            side_effect=AssertionError("raw mode must not materialize full artifact JSON"),
        ):
            with redirect_stdout(raw_out):
                raw_rc = main(
                    ["artifact", created["id"], artifact["artifact_id"], "--raw"]
                )

        self.assertEqual(raw_rc, 0)
        self.assertEqual(
            raw_out.getvalue(),
            "h3. +1. Root-cause/requirement:+\n\n"
            "p((. *Yêu cầu:* predicate isCombiCarrier.\n\n"
            "h3. +2. Solution:+\n\n"
            "* Apply verified fix.\n",
        )
        for diagnostic in (
            "SUMMARY",
            "revision=",
            "[root-cause-requirement]",
            "chunks=",
            "chars=",
            "bytes=",
            "Diagnostic summary",
        ):
            self.assertNotIn(diagnostic, raw_out.getvalue())

    def test_raw_artifact_can_stream_one_section_with_its_title(self) -> None:
        created, artifact = self._create_redmine_raw_report("redmine:112666")
        raw_out = io.StringIO()
        with redirect_stdout(raw_out):
            raw_rc = main(
                [
                    "artifact",
                    created["id"],
                    artifact["artifact_id"],
                    "--section",
                    "solution",
                    "--raw",
                ]
            )
        self.assertEqual(raw_rc, 0)
        self.assertEqual(
            raw_out.getvalue(),
            "h3. +2. Solution:+\n\n* Apply verified fix.\n",
        )

    def test_raw_and_json_are_mutually_exclusive(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["artifact", "redmine:1", "report:1", "--raw", "--json"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("not allowed with argument", stderr.getvalue())

    def test_list_show_and_artifact_commands_do_not_write_database(self) -> None:
        created, artifact = self._create_report("redmine:9")
        before = get_work_item(self.db, created["id"])
        before_mtime = self.db.stat().st_mtime_ns

        list_out = io.StringIO()
        with redirect_stdout(list_out):
            list_rc = main(["list"])
        show_out = io.StringIO()
        with redirect_stdout(show_out):
            show_rc = main(["show", created["id"]])
        artifact_out = io.StringIO()
        with redirect_stdout(artifact_out):
            artifact_rc = main(["artifact", created["id"], artifact["artifact_id"]])
        json_out = io.StringIO()
        with redirect_stdout(json_out):
            json_rc = main(
                ["artifact", created["id"], artifact["artifact_id"], "--json"]
            )
        raw_out = io.StringIO()
        with redirect_stdout(raw_out):
            raw_rc = main(
                ["artifact", created["id"], artifact["artifact_id"], "--raw"]
            )

        after_mtime = self.db.stat().st_mtime_ns
        after = get_work_item(self.db, created["id"])
        self.assertEqual(list_rc, 0)
        self.assertEqual(show_rc, 0)
        self.assertEqual(artifact_rc, 0)
        self.assertEqual(json_rc, 0)
        self.assertEqual(raw_rc, 0)
        self.assertEqual(before["revision"], after["revision"])
        self.assertEqual(before_mtime, after_mtime)
        self.assertIn("WORK ITEMS", list_out.getvalue())
        self.assertIn("ARTIFACTS (1)", show_out.getvalue())
        self.assertIn("Detailed requirement evidence", artifact_out.getvalue())
        self.assertIn('"content": "Detailed requirement evidence', json_out.getvalue())
        self.assertEqual(
            raw_out.getvalue(),
            "Requirement review\n\n"
            "Detailed requirement evidence that should not appear in thin show output.\n"
            "Second stored chunk.\n",
        )


if __name__ == "__main__":
    unittest.main()
