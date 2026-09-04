from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import ConflictError, NotFoundError, ValidationError
from server import _work_item_update_error_result


class WorkItemUpdateServerContractTests(unittest.TestCase):
    def test_update_tool_exposes_typed_grouped_mutation(self) -> None:
        server_path = Path(__file__).resolve().parents[1] / "server.py"
        text = server_path.read_text(encoding="utf-8")
        tree = ast.parse(text)
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
        self.assertEqual(args["mutation"], "WorkItemMutation")
        source = ast.get_source_segment(text, update) or ""
        source_lower = source.lower()
        self.assertIn("mutation.to_core_mutation()", source)
        self.assertIn("mutate_work_item", source)
        self.assertNotIn("update_work_item(", source)
        self.assertIn("direct typed groups", source_lower)
        self.assertIn("there is no op/value envelope", source_lower)
        self.assertIn("cross-group ordering is not", source_lower)
        self.assertNotIn("applied in caller order", source_lower)

    def test_validation_failure_is_structured(self) -> None:
        result = _work_item_update_error_result(
            "research:mail",
            ValidationError("question_upsert cannot rewrite immutable questions:q1.question"),
        )
        self.assertFalse(result["updated"])
        self.assertEqual(result["id"], "research:mail")
        self.assertEqual(result["error"]["code"], "work_item_validation")
        self.assertIn("question_upsert", result["error"]["message"])
        self.assertIn("WorkItemMutation", result["error"]["action"])
        self.assertIn("grouped fields", result["error"]["action"])
        self.assertIn("op/value", result["error"]["action"])

    def test_revision_conflict_is_structured_without_full_history_retry_guidance(self) -> None:
        result = _work_item_update_error_result(
            "research:mail",
            ConflictError("revision conflict for research:mail: expected 2, current 3"),
        )
        self.assertFalse(result["updated"])
        self.assertEqual(result["error"]["code"], "revision_conflict")
        self.assertIn("work_item_get", result["error"]["action"])
        self.assertIn("never auto-rebases", result["error"]["action"])
        self.assertNotIn("full historical", result["error"]["action"])

    def test_missing_item_is_structured(self) -> None:
        result = _work_item_update_error_result(
            "research:missing",
            NotFoundError("work item not found: research:missing"),
        )
        self.assertFalse(result["updated"])
        self.assertEqual(result["error"]["code"], "work_item_not_found")


if __name__ == "__main__":
    unittest.main()
