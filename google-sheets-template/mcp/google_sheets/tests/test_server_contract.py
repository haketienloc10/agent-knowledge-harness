from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER = PROJECT_ROOT / "server.py"
CORE = PROJECT_ROOT / "core.py"


class ServerContractTests(unittest.TestCase):
    def test_server_exposes_only_two_read_tools(self) -> None:
        tree = ast.parse(SERVER.read_text(encoding="utf-8"))
        tool_names = []
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "mcp"
                    and decorator.func.attr == "tool"
                ):
                    tool_names.append(node.name)
        self.assertEqual(
            tool_names,
            ["google_sheets_list_sheets", "google_sheets_read_range"],
        )

    def test_core_uses_readonly_scope_and_no_mutating_http_methods(self) -> None:
        source = CORE.read_text(encoding="utf-8")
        self.assertIn("https://www.googleapis.com/auth/spreadsheets.readonly", source)
        for forbidden in (".post(", ".put(", ".patch(", ".delete("):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("spreadsheets.readwrite", source)
        self.assertNotIn("https://www.googleapis.com/auth/drive", source)

    def test_read_range_forces_formatted_values(self) -> None:
        source = CORE.read_text(encoding="utf-8")
        self.assertIn('"valueRenderOption": "FORMATTED_VALUE"', source)
        self.assertNotIn('"valueRenderOption": "FORMULA"', source)


if __name__ == "__main__":
    unittest.main()
