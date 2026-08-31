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


def sectioned_content() -> str:
    return """Short preamble.

<!-- knowledge-section:contract -->
## Contract

Original contract.

<!-- knowledge-section:verification -->
## Verification

Original verification."""


def error_text(result) -> str:
    return "\n".join(
        block.text
        for block in result.content
        if getattr(block, "type", None) == "text"
    )


class KnowledgeServerContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_tools_list_exposes_progressive_disclosure_contract(self):
        async with Client(mcp) as client:
            listed = await client.list_tools()
        tools = {tool.name: tool for tool in listed.tools}
        self.assertEqual(
            set(tools),
            {
                "knowledge_search",
                "knowledge_read",
                "knowledge_read_metadata",
                "knowledge_read_section",
                "knowledge_write",
                "knowledge_update",
            },
        )

        search_schema = tools["knowledge_search"].input_schema
        self.assertEqual(set(search_schema["properties"]), {"keywords", "context", "limit"})

        read_schema = tools["knowledge_read"].input_schema
        self.assertEqual(set(read_schema["properties"]), {"ids"})
        ids_schema = read_schema["properties"]["ids"]
        self.assertEqual(ids_schema.get("maxItems"), 2)

        metadata_schema = tools["knowledge_read_metadata"].input_schema
        self.assertEqual(set(metadata_schema["properties"]), {"ids"})

        section_schema = tools["knowledge_read_section"].input_schema
        self.assertEqual(set(section_schema["properties"]), {"id", "section_id"})

        write_schema = tools["knowledge_write"].input_schema
        entries = write_schema["properties"]["entries"]
        item_schema = entries["items"]
        if "$ref" in item_schema:
            ref_name = item_schema["$ref"].rsplit("/", 1)[-1]
            entry = write_schema["$defs"][ref_name]
        else:
            entry = item_schema
        self.assertIn("routing", entry["properties"])
        for misplaced in ("summary", "when_to_read", "keywords", "aliases"):
            self.assertNotIn(misplaced, entry["properties"])
        self.assertFalse(entry.get("additionalProperties", True))

        update_schema = tools["knowledge_update"].input_schema
        self.assertEqual(
            set(update_schema["properties"]),
            {"id", "expected_revision", "changes"},
        )

    async def test_search_is_thin_then_read_hydrates_exact_id(self):
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
                    item_id = created.structured_content["changes"][0]["id"]

                    searched = await client.call_tool(
                        "knowledge_search",
                        {"keywords": ["payment retry", "test retry thanh toán"], "limit": 10},
                    )
                    self.assertFalse(searched.is_error)
                    hit = searched.structured_content["results"][0]
                    self.assertEqual(hit["id"], item_id)
                    for forbidden in ("content", "sources", "revision", "path", "canonical_name"):
                        self.assertNotIn(forbidden, hit)

                    read = await client.call_tool(
                        "knowledge_read",
                        {"ids": [item_id]},
                    )
                    self.assertFalse(read.is_error)
                    hydrated = read.structured_content["results"][0]
                    self.assertEqual(hydrated["content"], "version one")
                    self.assertIn("revision", hydrated)
                    self.assertIn("routing", hydrated)
                    self.assertNotIn("path", hydrated)

    async def test_metadata_and_section_reads_avoid_full_document_hydration(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init_store(root)
            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):
                async with Client(mcp) as client:
                    created = await client.call_tool(
                        "knowledge_write",
                        {"entries": [valid_entry(content=sectioned_content())]},
                    )
                    item_id = created.structured_content["changes"][0]["id"]

                    metadata = await client.call_tool(
                        "knowledge_read_metadata",
                        {"ids": [item_id]},
                    )
                    self.assertFalse(metadata.is_error)
                    meta_item = metadata.structured_content["results"][0]
                    self.assertNotIn("content", meta_item)
                    self.assertIn("revision", meta_item)
                    self.assertEqual(
                        [section["id"] for section in meta_item["sections"]],
                        ["contract", "verification"],
                    )

                    section = await client.call_tool(
                        "knowledge_read_section",
                        {"id": item_id, "section_id": "verification"},
                    )
                    self.assertFalse(section.is_error)
                    self.assertEqual(section.structured_content["heading"], "## Verification")
                    self.assertEqual(section.structured_content["content"], "Original verification.")
                    self.assertEqual(
                        section.structured_content["revision"],
                        meta_item["revision"],
                    )

    async def test_partial_update_patches_metadata_or_one_section(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init_store(root)
            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):
                async with Client(mcp) as client:
                    created = await client.call_tool(
                        "knowledge_write",
                        {"entries": [valid_entry(content=sectioned_content())]},
                    )
                    change = created.structured_content["changes"][0]
                    item_id = change["id"]

                    metadata_update = await client.call_tool(
                        "knowledge_update",
                        {
                            "id": item_id,
                            "expected_revision": change["revision"],
                            "changes": {
                                "metadata": {
                                    "routing": {
                                        "summary": "Updated metadata without resending full content."
                                    }
                                }
                            },
                        },
                    )
                    self.assertFalse(metadata_update.is_error)
                    revision = metadata_update.structured_content["changes"][0]["revision"]

                    section_update = await client.call_tool(
                        "knowledge_update",
                        {
                            "id": item_id,
                            "expected_revision": revision,
                            "changes": {
                                "section": {
                                    "id": "verification",
                                    "content": "Run focused verification, then full verification.",
                                }
                            },
                        },
                    )
                    self.assertFalse(section_update.is_error)

                    full = await client.call_tool("knowledge_read", {"ids": [item_id]})
                    item = full.structured_content["results"][0]
                    self.assertEqual(
                        item["routing"]["summary"],
                        "Updated metadata without resending full content.",
                    )
                    self.assertIn("Original contract.", item["content"])
                    self.assertIn("Run focused verification", item["content"])
                    self.assertNotIn("Original verification.", item["content"])

    async def test_partial_update_rejects_missing_section_without_creating_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init_store(root)
            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):
                async with Client(mcp) as client:
                    created = await client.call_tool(
                        "knowledge_write",
                        {"entries": [valid_entry(content=sectioned_content())]},
                    )
                    change = created.structured_content["changes"][0]
                    rejected = await client.call_tool(
                        "knowledge_update",
                        {
                            "id": change["id"],
                            "expected_revision": change["revision"],
                            "changes": {
                                "section": {"id": "not-there", "content": "body"}
                            },
                        },
                    )
        self.assertTrue(rejected.is_error)
        self.assertIn("code=missing_section", error_text(rejected))

    async def test_full_write_rejects_malformed_reserved_section_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init_store(root)
            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):
                async with Client(mcp) as client:
                    rejected = await client.call_tool(
                        "knowledge_write",
                        {
                            "entries": [
                                valid_entry(
                                    content="<!-- knowledge-section:Bad_Id -->\n## Bad\n\nbody"
                                )
                            ]
                        },
                    )
        self.assertTrue(rejected.is_error)
        self.assertIn("code=knowledge_validation", error_text(rejected))

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
        self.assertIn("must be nested under the 'routing' object", error_text(result))

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
        self.assertEqual(result.structured_content, {"reviewed": True, "changes": []})

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
        self.assertIn("read the exact knowledge target again", text)
        self.assertIn("expected_revision", text)


if __name__ == "__main__":
    unittest.main()
