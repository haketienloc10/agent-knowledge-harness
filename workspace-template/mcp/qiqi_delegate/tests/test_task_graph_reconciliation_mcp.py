from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client
from task_graph_mcp import mcp
from task_graph_runtime import GraphRuntime
from task_graph_store import GraphRuntimeStore


def packet(objective: str, revision: int) -> dict:
    return {
        "objective": objective,
        "scope": ["repository-local implementation"],
        "acceptance_criteria": ["focused verification passes"],
        "context": {
            "trusted_facts": [
                {
                    "fact": f"work_item_revision={revision}",
                    "source": "Work Item",
                }
            ]
        },
    }


def initial_graph_payload() -> dict:
    return {
        "nodes": [
            {
                "node_id": "contracts",
                "repository": "contracts",
                "route": "codex-balanced",
                "task_packet": packet("Update contract.", 1),
            }
        ]
    }


def revised_graph_payload() -> dict:
    return {
        "nodes": [
            {
                "node_id": "contracts",
                "repository": "contracts",
                "route": "codex-balanced",
                "task_packet": packet("Update revised contract.", 2),
            },
            {
                "node_id": "backend",
                "repository": "backend",
                "route": "codex-balanced",
                "depends_on": ["contracts"],
                "task_packet": packet("Update backend consumer.", 2),
            },
        ]
    }


def error_text(result) -> str:
    return "\n".join(
        block.text
        for block in result.content
        if getattr(block, "type", None) == "text"
    )


class TaskGraphReconciliationMcpTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
        self.runtime = GraphRuntime(GraphRuntimeStore(db_path))
        self.runtime_patch = patch("task_graph_mcp._graph_runtime", self.runtime)
        self.registry_patch = patch(
            "task_graph_mcp._load_repo_registry",
            return_value={
                "contracts": Path("/tmp/contracts"),
                "backend": Path("/tmp/backend"),
            },
        )
        self.runtime_patch.start()
        self.registry_patch.start()

    def tearDown(self) -> None:
        self.registry_patch.stop()
        self.runtime_patch.stop()
        self.temp.cleanup()

    async def test_reconcile_graph_is_public_and_reconciles_explicit_authored_graph(self) -> None:
        tools = await mcp.list_tools()
        self.assertIn("reconcile_graph", {tool.name for tool in tools})

        async with Client(mcp) as client:
            started_result = await client.call_tool(
                "start_graph",
                {"graph": initial_graph_payload()},
            )
            self.assertFalse(started_result.is_error)
            started = started_result.structured_content

            reconciled_result = await client.call_tool(
                "reconcile_graph",
                {
                    "graph_run_id": started["graph_run_id"],
                    "graph": revised_graph_payload(),
                    "expected_revision": started["revision"],
                },
            )
            self.assertFalse(reconciled_result.is_error)
            reconciled = reconciled_result.structured_content
            self.assertEqual(reconciled["graph_state"], "ready")
            self.assertEqual(reconciled["runnable_nodes"], ["contracts"])
            self.assertEqual(reconciled["reconciliation"]["changed_nodes"], ["contracts"])
            self.assertEqual(reconciled["reconciliation"]["added_nodes"], ["backend"])

            stale_result = await client.call_tool(
                "reconcile_graph",
                {
                    "graph_run_id": started["graph_run_id"],
                    "graph": revised_graph_payload(),
                    "expected_revision": started["revision"],
                },
            )
            self.assertTrue(stale_result.is_error)
            self.assertIn("code=graph_revision_conflict", error_text(stale_result))

    def test_codex_whitelist_exposes_reconcile_graph(self) -> None:
        workspace_root = Path(__file__).resolve().parents[3]
        config = (workspace_root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('"reconcile_graph"', config)


if __name__ == "__main__":
    unittest.main()
