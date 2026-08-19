from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import init_store  # noqa: E402
from mcp import Client  # noqa: E402
from server import mcp  # noqa: E402


def valid_entry(*, content: str = "smoke") -> dict:
    return {
        "canonical_name": "smoke-retry-rule",
        "title": "Smoke retry rule",
        "scope": {"kind": "domain", "id": "smoke.payment"},
        "routing": {
            "summary": "Smoke payments must not retry after confirmed commit.",
            "when_to_read": ["testing knowledge retrieval"],
            "keywords": ["smoke", "payment", "retry", "commit"],
            "aliases": ["test retry thanh toán"],
        },
        "content": content,
        "sources": [{"kind": "manual", "locator": "server contract test"}],
    }


def error_text(result) -> str:
    return "\n".join(
        block.text
        for block in result.content
        if getattr(block, "type", None) == "text"
    )


class KnowledgeServerContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_tools_list_exposes_nested_write_schema(self):
        async with Client(mcp) as client:
            listed = await client.list_tools()
        tools = {tool.name: tool for tool in listed.tools}
        self.assertEqual(set(tools), {"knowledge_read", "knowledge_write"})

        write_tool = tools["knowledge_write"]
        description = write_tool.description or ""
        self.assertIn("knowledge-distill", description)
        self.assertIn("task premise", description)
        self.assertIn("Compression must not increase certainty", description)

        schema = write_tool.input_schema
        entries = schema["properties"]["entries"]
        item_schema = entries["items"]
        if "$ref" in item_schema:
            ref_name = item_schema["$ref"].rsplit("/", 1)[-1]
            entry = schema["$defs"][ref_name]
        else:
            entry = item_schema

        self.assertIn("routing", entry["properties"])
        for misplaced in ("summary", "when_to_read", "keywords", "aliases"):
            self.assertNotIn(misplaced, entry["properties"])
        self.assertFalse(entry.get("additionalProperties", True))

    async def test_flat_routing_payload_fails_before_tool_body_with_hint(self):
        bad_entry = valid_entry()
        routing = bad_entry.pop("routing")
        bad_entry.update(routing)
        async with Client(mcp) as client:
            result = await client.call_tool(
                "knowledge_write",
                {"entries": [bad_entry]},
            )
        self.assertTrue(result.is_error)
        self.assertIn(
            "must be nested under the 'routing' object",
            error_text(result),
        )

    async def test_empty_review_returns_structured_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init_store(root)
            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):
                async with Client(mcp) as client:
                    result = await client.call_tool(
                        "knowledge_write",
                        {"entries": []},
                    )
        self.assertFalse(result.is_error)
        self.assertEqual(
            result.structured_content,
            {"reviewed": True, "changes": []},
        )

    async def test_stale_revision_error_tells_agent_exact_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init_store(root)
            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):
                async with Client(mcp) as client:
                    created = await client.call_tool(
                        "knowledge_write",
                        {"entries": [valid_entry(content="version one")]},
                    )
                    self.assertFalse(created.is_error)
                    change = created.structured_content["changes"][0]
                    old_revision = change["revision"]
                    item_id = change["id"]

                    update = valid_entry(content="version two")
                    update["id"] = item_id
                    update["expected_revision"] = old_revision
                    updated = await client.call_tool(
                        "knowledge_write",
                        {"entries": [update]},
                    )
                    self.assertFalse(updated.is_error)
                    self.assertNotEqual(
                        old_revision,
                        updated.structured_content["changes"][0]["revision"],
                    )

                    stale = valid_entry(content="stale version")
                    stale["id"] = item_id
                    stale["expected_revision"] = old_revision
                    rejected = await client.call_tool(
                        "knowledge_write",
                        {"entries": [stale]},
                    )

        self.assertTrue(rejected.is_error)
        text = error_text(rejected)
        self.assertIn("code=revision_conflict", text)
        self.assertIn("action=call knowledge_read again", text)
        self.assertIn("expected_revision", text)


if __name__ == "__main__":
    unittest.main()
