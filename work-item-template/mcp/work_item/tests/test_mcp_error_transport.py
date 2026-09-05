from __future__ import annotations

import importlib.metadata
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from artifacts import ArtifactNotFoundError  # noqa: E402
from core import ConflictError, NotFoundError  # noqa: E402
from mcp import Client  # noqa: E402
from server import mcp  # noqa: E402


def error_text(result) -> str:
    return "\n".join(
        block.text
        for block in result.content
        if getattr(block, "type", None) == "text"
    )


class WorkItemMcpErrorTransportTest(unittest.IsolatedAsyncioTestCase):
    def test_sdk_version_is_reviewed(self) -> None:
        self.assertEqual(importlib.metadata.version("mcp"), "2.1.1")

    async def test_artifact_not_found_is_model_visible_tool_error(self) -> None:
        with (
            patch("server._db_path", return_value=Path("/tmp/work-item-test.db")),
            patch(
                "server.get_artifact",
                side_effect=ArtifactNotFoundError("artifact report:missing does not exist"),
            ),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "work_item_artifact_get",
                    {"id": "local:1", "artifact_id": "report:missing"},
                )

        self.assertTrue(result.is_error)
        text = error_text(result)
        self.assertIn("code=artifact_not_found", text)
        self.assertIn("work_item_artifact_list/get", text)

    async def test_history_revision_conflict_is_model_visible_tool_error(self) -> None:
        with (
            patch("server._db_path", return_value=Path("/tmp/work-item-test.db")),
            patch(
                "server.read_work_item_history",
                side_effect=ConflictError("history revision conflict: expected 2, current 3"),
            ),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "work_item_history_read",
                    {"id": "local:1", "collection": "decisions"},
                )

        self.assertTrue(result.is_error)
        text = error_text(result)
        self.assertIn("code=history_revision_conflict", text)
        self.assertIn("restart work_item_history_read", text)

    async def test_missing_work_item_remains_normal_control_flow(self) -> None:
        with (
            patch("server._db_path", return_value=Path("/tmp/work-item-test.db")),
            patch(
                "server.get_work_item_snapshot",
                side_effect=NotFoundError("work item local:missing does not exist"),
            ),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool("work_item_get", {"id": "local:missing"})

        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["found"], False)
        self.assertEqual(
            result.structured_content["error"]["code"],
            "work_item_not_found",
        )


if __name__ == "__main__":
    unittest.main()
