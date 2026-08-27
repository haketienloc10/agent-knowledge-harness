from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import ConflictError, NotFoundError, ValidationError
from server import _work_item_update_error_result


class WorkItemUpdateServerContractTests(unittest.TestCase):
    def test_update_tool_exposes_typed_patch(self) -> None:
        server_path = Path(__file__).resolve().parents[1] / "server.py"
        tree = ast.parse(server_path.read_text(encoding="utf-8"))
        update = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "work_item_update"
        )
        args = {
            arg.arg: ast.unparse(arg.annotation)
            for arg in update.args.args
            if arg.annotation is not None
        }
        self.assertEqual(args["changes"], "WorkItemPatch")

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
