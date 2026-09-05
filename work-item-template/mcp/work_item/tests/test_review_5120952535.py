from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.mcpserver.exceptions import ToolError
from artifacts import ArtifactConflictError
from core import ConflictError, ValidationError
from server import _raise_actionable_error


class WorkItemReview5120952535Test(unittest.TestCase):
    def assert_actionable(self, exc, code: str) -> None:
        with self.assertRaises(ToolError) as raised:
            _raise_actionable_error(exc)
        text = str(raised.exception)
        self.assertIn(f"code={code}", text)
        self.assertIn("; action=", text)

    def test_generic_artifact_conflict_has_action(self):
        self.assert_actionable(ArtifactConflictError("generic artifact conflict"), "artifact_conflict")

    def test_generic_work_item_conflict_has_action(self):
        self.assert_actionable(ConflictError("generic work item conflict"), "work_item_conflict")

    def test_validation_error_has_action(self):
        self.assert_actionable(ValidationError("invalid work item request"), "work_item_validation")


if __name__ == "__main__":
    unittest.main()
