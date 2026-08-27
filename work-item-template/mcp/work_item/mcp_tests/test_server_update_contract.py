from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import get_type_hints

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import ConflictError, NotFoundError, ValidationError
from models import WorkItemPatch
from server import _work_item_update_error_result, work_item_update


class WorkItemUpdateServerContractTests(unittest.TestCase):
    def test_update_tool_exposes_typed_patch(self) -> None:
        hints = get_type_hints(work_item_update)
        self.assertIs(hints["changes"], WorkItemPatch)

    def test_validation_failure_is_structured(self) -> None:
        result = _work_item_update_error_result(
            "research:mail",
            ValidationError("questions[0].question must not be empty"),
        )
        self.assertFalse(result["updated"])
        self.assertEqual(result["id"], "research:mail")
        self.assertEqual(result["error"]["code"], "work_item_validation")
        self.assertIn("questions[0].question", result["error"]["message"])
        self.assertIn("WorkItemPatch", result["error"]["action"])

    def test_revision_conflict_is_structured(self) -> None:
        result = _work_item_update_error_result(
            "research:mail",
            ConflictError("revision conflict for research:mail: expected 2, current 3"),
        )
        self.assertFalse(result["updated"])
        self.assertEqual(result["error"]["code"], "revision_conflict")
        self.assertIn("work_item_get", result["error"]["action"])
        self.assertIn("full", result["error"]["action"])

    def test_missing_item_is_structured(self) -> None:
        result = _work_item_update_error_result(
            "research:missing",
            NotFoundError("work item not found: research:missing"),
        )
        self.assertFalse(result["updated"])
        self.assertEqual(result["error"]["code"], "work_item_not_found")


if __name__ == "__main__":
    unittest.main()
