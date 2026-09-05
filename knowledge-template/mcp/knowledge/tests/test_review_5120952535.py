from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import ConflictError, ValidationError, init_store
from mcp import Client
from server import _raise_actionable_error, mcp


def valid_entry() -> dict:
    return {
        "canonical_name": "review-path-redaction",
        "title": "Review path redaction",
        "scope": {"kind": "domain", "id": "review.transport"},
        "routing": {
            "summary": "Review error transport path redaction.",
            "when_to_read": ["reviewing MCP error transport"],
            "keywords": ["review", "transport", "redaction"],
            "aliases": [],
        },
        "content": "review",
        "sources": [{"kind": "manual", "locator": "review regression"}],
    }


def error_text(result) -> str:
    return "\n".join(
        block.text for block in result.content if getattr(block, "type", None) == "text"
    )


class KnowledgeReview5120952535Test(unittest.IsolatedAsyncioTestCase):
    async def test_validation_tool_error_redacts_absolute_store_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "store"
            init_store(root)
            leaked = str(root / "domain" / "review" / "secret.md")
            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):
                with patch(
                    "server.write_knowledge",
                    side_effect=ValidationError(f"indexed document is invalid: {leaked}"),
                ):
                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "knowledge_write", {"entries": [valid_entry()]}
                        )
        text = error_text(result)
        self.assertTrue(result.is_error)
        self.assertIn("code=knowledge_validation", text)
        self.assertIn("<redacted-path>", text)
        self.assertNotIn(str(root), text)
        self.assertIn("; action=", text)

    def test_generic_knowledge_conflict_has_recovery_action(self):
        with self.assertRaises(Exception) as raised:
            _raise_actionable_error(ConflictError("generic knowledge conflict"))
        text = str(raised.exception)
        self.assertIn("code=knowledge_conflict", text)
        self.assertIn("; action=", text)


if __name__ == "__main__":
    unittest.main()
