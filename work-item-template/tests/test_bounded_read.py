from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "skills" / "work-item" / "scripts" / "read.py"


def primary(extra_scope_lines: int = 0) -> str:
    filler = "\n".join(f"- unrelated scope line {i}" for i in range(extra_scope_lines))
    return f"""---
id: "redmine:88"
revision: 7
status: active
phase: investigation
---

# Objective

Investigate bounded hydration.

# Current Requirements

- Keep filesystem-native Work Items.

# Acceptance Criteria

- Startup stays bounded.

# Scope

{filler}

# Decisions

- Preserve canonical current-state semantics.

# Open Questions

- None

# Blockers

- None

# Current State

Investigation is active.

# Next Actions

- Read only material evidence.
"""


def investigation(long_finding: str = "Finding A") -> str:
    return f"""---
based_on_work_item_revision: 7
---

# Scope

Hydration behavior only.

# Verified Findings

- {long_finding}

# Relevant Evidence

- Evidence A

# Open Questions

- None

# Conclusion

Use bounded reads.
"""


class BoundedWorkItemReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.temp.name) / "redmine~88"
        self.dossier.mkdir()
        (self.dossier / "00_WORK_ITEM.md").write_text(primary(), encoding="utf-8")
        (self.dossier / "20_investigation.md").write_text(investigation(), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_reader(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-S", str(READER), "--dossier", str(self.dossier), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_bootstrap_omits_large_unrelated_sections_and_stays_bounded(self) -> None:
        (self.dossier / "00_WORK_ITEM.md").write_text(primary(extra_scope_lines=700), encoding="utf-8")
        completed = self.run_reader("--profile", "bootstrap", "--expected-revision", "7")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertLessEqual(len(completed.stdout.encode("utf-8")), 8192)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["coverage"]["mode"], "bootstrap")
        self.assertFalse(payload["coverage"]["complete_file"])
        self.assertIn("Scope", payload["coverage"]["omitted_top_level_sections"])
        self.assertNotIn("unrelated scope line 699", payload["content"])
        self.assertEqual(payload["metadata"]["revision"], 7)

    def test_heading_index_is_compact_and_does_not_emit_body(self) -> None:
        completed = self.run_reader("--file", "20_investigation.md", "--headings")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["coverage"]["mode"], "headings")
        self.assertIn(
            "Verified Findings",
            [item["heading"] for item in payload["headings"]],
        )
        self.assertNotIn("Finding A", completed.stdout)

    def test_exact_sections_preserve_coverage_without_neighbor_hydration(self) -> None:
        completed = self.run_reader(
            "--file",
            "20_investigation.md",
            "--section",
            "Verified Findings",
            "--section",
            "Conclusion",
            "--expected-revision",
            "7",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertIn("Finding A", payload["content"])
        self.assertIn("Use bounded reads.", payload["content"])
        self.assertNotIn("Evidence A", payload["content"])
        self.assertIn("Relevant Evidence", payload["coverage"]["omitted_top_level_sections"])
        self.assertEqual(payload["file_metadata"]["based_on_work_item_revision"], 7)
        self.assertFalse(payload["coverage"]["complete_file"])

    def test_missing_section_fails_without_partial_stdout(self) -> None:
        completed = self.run_reader(
            "--file",
            "20_investigation.md",
            "--section",
            "Does Not Exist",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        error = json.loads(completed.stderr)
        self.assertEqual(error["error"], "section_not_found")

    def test_revision_mismatch_fails_before_lifecycle_hydration(self) -> None:
        completed = self.run_reader(
            "--file",
            "20_investigation.md",
            "--section",
            "Conclusion",
            "--expected-revision",
            "6",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        error = json.loads(completed.stderr)
        self.assertEqual(error["error"], "revision_mismatch")
        self.assertEqual(error["actual_revision"], 7)

    def test_oversized_selected_surface_fails_instead_of_truncating(self) -> None:
        huge = "x" * 12000
        (self.dossier / "20_investigation.md").write_text(investigation(huge), encoding="utf-8")
        completed = self.run_reader(
            "--file",
            "20_investigation.md",
            "--section",
            "Verified Findings",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        error = json.loads(completed.stderr)
        self.assertEqual(error["error"], "output_budget_exceeded")
        self.assertEqual(error["max_bytes"], 8192)

    def test_line_fallback_is_bounded_and_reports_coverage(self) -> None:
        completed = self.run_reader(
            "--file",
            "20_investigation.md",
            "--lines",
            "2:5",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["coverage"]["start_line"], 2)
        self.assertEqual(payload["coverage"]["end_line"], 5)
        self.assertFalse(payload["coverage"]["complete_file"])

    def test_line_range_above_hard_limit_is_rejected_by_cli(self) -> None:
        completed = self.run_reader(
            "--file",
            "20_investigation.md",
            "--lines",
            "1:121",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("at most 120 lines", completed.stderr)

    def test_file_without_selector_has_no_full_file_happy_path(self) -> None:
        completed = self.run_reader("--file", "20_investigation.md")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("--file requires exactly one", completed.stderr)


if __name__ == "__main__":
    unittest.main()
