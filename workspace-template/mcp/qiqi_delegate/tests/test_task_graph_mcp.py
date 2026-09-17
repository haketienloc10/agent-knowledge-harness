from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
                "route": "codex-balanced",
                "task_packet": {
                    "objective": "Update shared contract.",
                    "scope": ["contract"],
                    "acceptance_criteria": ["contract verification passes"],
                },
            },
            {
                "node_id": "backend",
                "repository": "backend",
                "route": "codex-balanced",
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

    async def test_outer_loop_executes_one_node_through_existing_delegate_primitive(self) -> None:
        delegate = AsyncMock(
            return_value={
                "session_id": "native-session-contracts",
                "turn_id": "qiqi-turn-contracts",
                "state": "settled",
                "agent_response": "native final response",
            }
        )
        with patch("task_graph_mcp.delegate_repo_task", delegate):
            async with Client(mcp) as client:
                started_result = await client.call_tool("start_graph", {"graph": graph_payload()})
                self.assertFalse(started_result.is_error)
                started = started_result.structured_content
                run_id = started["graph_run_id"]
                self.assertEqual(started["graph_state"], "ready")
                self.assertEqual(started["runnable_nodes"], ["contracts"])

                delegated_result = await client.call_tool(
                    "delegate_next", {"graph_run_id": run_id}
                )
                self.assertFalse(delegated_result.is_error)
                delegated = delegated_result.structured_content
                self.assertEqual(delegated["graph_state"], "awaiting_review")
                self.assertIsNone(delegated["current_wave_id"])
                self.assertEqual(len(delegated["results"]), 1)
                self.assertEqual(delegated["results"][0]["node_id"], "contracts")
                self.assertEqual(delegated["results"][0]["runtime_state"], "settled")
                self.assertEqual(
                    delegated["results"][0]["session_id"],
                    "native-session-contracts",
                )

                current_result = await client.call_tool(
                    "get_graph", {"graph_run_id": run_id}
                )
                current = current_result.structured_content
                self.assertEqual(current["graph_state"], "awaiting_review")
                self.assertEqual(current["nodes"][0]["runtime_state"], "settled")
                self.assertEqual(
                    current["nodes"][0]["result"]["agent_response"],
                    "native final response",
                )

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

        delegate.assert_awaited_once_with(
            repository="contracts",
            route="codex-balanced",
            objective="Update shared contract.",
            scope=["contract"],
            acceptance_criteria=["contract verification passes"],
            out_of_scope=[],
            context=None,
            constraints=[],
            known_unknowns=[],
            session_id=None,
        )

    async def test_blocked_direct_result_is_persisted_for_qiqi_review(self) -> None:
        delegate = AsyncMock(
            return_value={
                "session_id": "native-session-contracts",
                "turn_id": "qiqi-turn-contracts",
                "state": "blocked",
                "agent_response": None,
                "blocker_type": "agent_blocked",
            }
        )
        with patch("task_graph_mcp.delegate_repo_task", delegate):
            async with Client(mcp) as client:
                started = (
                    await client.call_tool("start_graph", {"graph": graph_payload()})
                ).structured_content
                result = await client.call_tool(
                    "delegate_next", {"graph_run_id": started["graph_run_id"]}
                )

        self.assertFalse(result.is_error)
        payload = result.structured_content
        self.assertEqual(payload["graph_state"], "awaiting_review")
        self.assertEqual(payload["results"][0]["runtime_state"], "blocked")
        self.assertEqual(payload["results"][0]["blocker_type"], "agent_blocked")

    async def test_missing_execution_route_is_model_visible_and_starts_no_attempt(self) -> None:
        graph = graph_payload()
        graph["nodes"][0].pop("route")
        delegate = AsyncMock()

        with patch("task_graph_mcp.delegate_repo_task", delegate):
            async with Client(mcp) as client:
                started = (
                    await client.call_tool("start_graph", {"graph": graph})
                ).structured_content
                result = await client.call_tool(
                    "delegate_next", {"graph_run_id": started["graph_run_id"]}
                )

        self.assertTrue(result.is_error)
        text = error_text(result)
        self.assertIn("code=graph_execution_invalid", text)
        self.assertIn("has no route", text)
        delegate.assert_not_awaited()
        self.assertEqual(
            self.runtime.store.list_attempts(started["graph_run_id"], "contracts"),
            [],
        )

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
