from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import Client  # noqa: E402
from task_graph_mcp import mcp  # noqa: E402
from task_graph_runtime import GraphRuntime  # noqa: E402
from task_graph_store import GraphRuntimeStore  # noqa: E402


def graph_payload() -> dict:
    return {
        "nodes": [
            {
                "node_id": "contracts",
                "repository": "contracts",
                "task_packet": {
                    "objective": "Update shared contract.",
                    "scope": ["contract"],
                    "acceptance_criteria": ["contract verification passes"],
                },
            },
            {
                "node_id": "backend",
                "repository": "backend",
                "depends_on": ["contracts"],
                "task_packet": {
                    "objective": "Update backend consumer.",
                    "scope": ["backend"],
                    "acceptance_criteria": ["backend verification passes"],
                },
            },
        ]
    }


def error_text(result) -> str:
    return "\n".join(
        block.text
        for block in result.content
        if getattr(block, "type", None) == "text"
    )


class TaskGraphMcpTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_public_graph_tools_are_registered(self) -> None:
        tools = await mcp.list_tools()
        names = {tool.name for tool in tools}
        self.assertTrue(
            {
                "delegate_repo_task",
                "start_graph",
                "get_graph",
                "delegate_next",
                "submit_decisions",
            }.issubset(names)
        )

    async def test_outer_loop_contract_is_exposed_without_phase6_execution(self) -> None:
        async with Client(mcp) as client:
            started_result = await client.call_tool("start_graph", {"graph": graph_payload()})
            self.assertFalse(started_result.is_error)
            started = started_result.structured_content
            run_id = started["graph_run_id"]
            self.assertEqual(started["graph_state"], "ready")
            self.assertEqual(started["runnable_nodes"], ["contracts"])

            dispatch_result = await client.call_tool(
                "delegate_next", {"graph_run_id": run_id}
            )
            self.assertFalse(dispatch_result.is_error)
            dispatch = dispatch_result.structured_content
            self.assertEqual(dispatch["dispatch"]["node"]["node_id"], "contracts")
            self.assertEqual(dispatch["dispatch"]["execution_state"], "planned")
            self.assertFalse(dispatch["dispatch"]["execution_side_effect"])
            self.assertIsNone(self.runtime.store.get_node(run_id, "contracts")["current_attempt_id"])

            attempt_id = self.runtime.store.start_attempt(run_id, "contracts", "wave-1")
            self.runtime.store.finish_attempt(
                attempt_id,
                runtime_state="settled",
                result={"state": "settled", "agent_response": "native final response"},
            )
            self.runtime.store.close_wave(run_id, "wave-1")

            current_result = await client.call_tool(
                "get_graph", {"graph_run_id": run_id}
            )
            current = current_result.structured_content
            self.assertEqual(current["graph_state"], "awaiting_review")

            decided_result = await client.call_tool(
                "submit_decisions",
                {
                    "graph_run_id": run_id,
                    "decisions": [{"node_id": "contracts", "action": "accept"}],
                    "expected_revision": current["revision"],
                },
            )
            self.assertFalse(decided_result.is_error)
            decided = decided_result.structured_content
            self.assertEqual(decided["graph_state"], "ready")
            self.assertEqual(decided["runnable_nodes"], ["backend"])

    async def test_graph_validation_error_is_model_visible(self) -> None:
        invalid = graph_payload()
        invalid["nodes"][0]["repository"] = "missing"

        async with Client(mcp) as client:
            result = await client.call_tool("start_graph", {"graph": invalid})

        self.assertTrue(result.is_error)
        text = error_text(result)
        self.assertIn("code=graph_invalid", text)
        self.assertIn("unknown repository", text)
        self.assertNotEqual(text, "Error executing tool start_graph")

    async def test_unknown_graph_run_error_is_model_visible(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_graph", {"graph_run_id": "missing-run"}
            )

        self.assertTrue(result.is_error)
        text = error_text(result)
        self.assertIn("code=unknown_graph_run", text)


if __name__ == "__main__":
    unittest.main()
