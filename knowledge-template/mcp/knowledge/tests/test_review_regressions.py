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


def entry(*, content: str) -> dict:
    return {
        "canonical_name": "review-regression-rule",
        "title": "Review regression rule",
        "scope": {"kind": "domain", "id": "knowledge.review"},
        "routing": {
            "summary": "Review regressions must preserve scoped Knowledge semantics.",
            "when_to_read": ["testing scoped Knowledge review fixes"],
            "keywords": ["knowledge", "review", "semantic section"],
            "aliases": [],
        },
        "content": content,
        "sources": [{"kind": "manual", "locator": "review regression test"}],
    }


SECTIONED = """<!-- knowledge-section:contract -->
## Contract

Original contract.

<!-- knowledge-section:verification -->
## Verification

Original verification."""


def _resolve_schema(schema: dict, node: dict) -> dict:
    ref = node.get("$ref")
    if not ref:
        return node
    name = ref.rsplit("/", 1)[-1]
    return schema["$defs"][name]


class KnowledgeReviewRegressionTest(unittest.IsolatedAsyncioTestCase):
    async def test_generated_update_schema_accepts_revision_from_all_exact_reads(self):
        async with Client(mcp) as client:
            listed = await client.list_tools()
        tools = {tool.name: tool for tool in listed.tools}
        schema = tools["knowledge_update"].input_schema
        revision_schema = _resolve_schema(
            schema, schema["properties"]["expected_revision"]
        )
        description = revision_schema["description"]
        for tool in (
            "knowledge_read",
            "knowledge_read_metadata",
            "knowledge_read_section",
        ):
            self.assertIn(tool, description)
        self.assertIn("knowledge_update.expected_revision", description)

    async def test_scoped_section_read_update_preserves_markdown_whitespace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init_store(root)
            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):
                async with Client(mcp) as client:
                    created = await client.call_tool(
                        "knowledge_write", {"entries": [entry(content=SECTIONED)]}
                    )
                    self.assertFalse(created.is_error)
                    change = created.structured_content["changes"][0]
                    body = "    indented_code()\nline with hard break  "

                    updated = await client.call_tool(
                        "knowledge_update",
                        {
                            "id": change["id"],
                            "expected_revision": change["revision"],
                            "changes": {
                                "section": {"id": "contract", "content": body}
                            },
                        },
                    )
                    self.assertFalse(updated.is_error)

                    section = await client.call_tool(
                        "knowledge_read_section",
                        {"id": change["id"], "section_id": "contract"},
                    )
                    self.assertFalse(section.is_error)
                    self.assertEqual(section.structured_content["content"], body)

    async def test_metadata_section_index_preserves_exact_stored_heading(self):
        content = """<!-- knowledge-section:contract -->
## Contract  

Live body."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init_store(root)
            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):
                async with Client(mcp) as client:
                    created = await client.call_tool(
                        "knowledge_write", {"entries": [entry(content=content)]}
                    )
                    self.assertFalse(created.is_error)
                    item_id = created.structured_content["changes"][0]["id"]
                    metadata = await client.call_tool(
                        "knowledge_read_metadata", {"ids": [item_id]}
                    )
                    self.assertFalse(metadata.is_error)
                    self.assertEqual(
                        metadata.structured_content["results"][0]["sections"],
                        [{"id": "contract", "heading": "## Contract  "}],
                    )

    async def test_fenced_marker_example_is_not_exposed_as_section(self):
        content = """```markdown
<!-- knowledge-section:not-live -->
## Example only
```

<!-- knowledge-section:contract -->
## Contract

Live body."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init_store(root)
            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):
                async with Client(mcp) as client:
                    created = await client.call_tool(
                        "knowledge_write", {"entries": [entry(content=content)]}
                    )
                    self.assertFalse(created.is_error)
                    item_id = created.structured_content["changes"][0]["id"]
                    metadata = await client.call_tool(
                        "knowledge_read_metadata", {"ids": [item_id]}
                    )
                    self.assertFalse(metadata.is_error)
                    self.assertEqual(
                        metadata.structured_content["results"][0]["sections"],
                        [{"id": "contract", "heading": "## Contract"}],
                    )


if __name__ == "__main__":
    unittest.main()
