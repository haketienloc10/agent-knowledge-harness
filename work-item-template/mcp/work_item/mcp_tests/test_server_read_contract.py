from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import DecisionRecord, QuestionRecord, WorkItemHistoryPage, WorkItemSnapshot


class WorkItemReadContractTests(unittest.TestCase):
    def _server_functions(self) -> tuple[str, dict[str, ast.AsyncFunctionDef]]:
        server_path = Path(__file__).resolve().parents[1] / "server.py"
        text = server_path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        funcs = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
        }
        return text, funcs

    def test_public_get_uses_bounded_snapshot_projection(self) -> None:
        text, funcs = self._server_functions()
        source = ast.get_source_segment(text, funcs["work_item_get"]) or ""
        self.assertIn("get_work_item_snapshot", source)
        self.assertIn("WorkItemSnapshot.model_validate", source)
        self.assertNotIn("get_work_item(_db_path()", source)

        properties = WorkItemSnapshot.model_json_schema()["properties"]
        for field in (
            "open_questions",
            "active_decisions",
            "open_blockers",
            "pending_handoffs",
            "history",
            "artifacts",
        ):
            self.assertIn(field, properties)
        for full_history_field in (
            "questions",
            "decisions",
            "changes",
            "blockers",
            "handoffs",
            "checkpoints",
        ):
            self.assertNotIn(full_history_field, properties)

    def test_history_tool_is_single_collection_and_typed(self) -> None:
        text, funcs = self._server_functions()
        history = funcs["work_item_history_read"]
        args = {
            arg.arg: ast.unparse(arg.annotation)
            for arg in history.args.args
            if arg.annotation is not None
        }
        self.assertEqual(args["collection"], "HistoryCollection")
        self.assertEqual(args["status"], "HistoryStatus | None")
        self.assertIn("repository", args)
        self.assertIn("cursor", args)
        source = ast.get_source_segment(text, history) or ""
        self.assertIn("read_work_item_history", source)
        self.assertIn("WorkItemHistoryPage.model_validate", source)

        schema = WorkItemHistoryPage.model_json_schema()
        self.assertIn("collection", schema["properties"])
        self.assertIn("next_cursor", schema["properties"])
        self.assertIn("revision", schema["properties"])

    def test_canonical_question_and_decision_records_require_lifecycle_status(self) -> None:
        with self.assertRaises(PydanticValidationError):
            QuestionRecord.model_validate({"id": "q1", "question": "Missing status"})
        with self.assertRaises(PydanticValidationError):
            DecisionRecord.model_validate({"id": "d1", "summary": "Missing status"})

        question = QuestionRecord.model_validate(
            {"id": "q1", "question": "Explicit", "status": "open"}
        )
        decision = DecisionRecord.model_validate(
            {"id": "d1", "summary": "Explicit", "status": "active"}
        )
        self.assertEqual(question.status, "open")
        self.assertEqual(decision.status, "active")

    def test_server_exposes_five_work_item_tools_plus_six_artifact_tools(self) -> None:
        server_path = Path(__file__).resolve().parents[1] / "server.py"
        tree = ast.parse(server_path.read_text(encoding="utf-8"))
        tools = []
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "mcp"
                    and decorator.func.attr == "tool"
                ):
                    tools.append(node.name)
        self.assertEqual(
            tools,
            [
                "work_item_get",
                "work_item_history_read",
                "work_item_list",
                "work_item_create",
                "work_item_update",
                "work_item_artifact_list",
                "work_item_artifact_get",
                "work_item_artifact_create",
                "work_item_artifact_append",
                "work_item_artifact_read",
                "work_item_artifact_finalize",
            ],
        )


if __name__ == "__main__":
    unittest.main()
