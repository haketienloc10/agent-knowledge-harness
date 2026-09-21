from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import build_task_packet  # noqa: E402
from mcp import Client  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from task_graph import GraphNode, TaskGraph  # noqa: E402
from task_graph_mcp import mcp  # noqa: E402
from task_graph_runtime import (  # noqa: E402
    GraphRuntime,
    RecoverableRepoTaskExecutionError,
    decisions_from_payload,
)
from task_graph_store import GraphRuntimeStore  # noqa: E402


class RetryReviewRuntimeRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
        self.store = GraphRuntimeStore(db_path)
        self.runtime = GraphRuntime(self.store)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def graph(self, *, with_trusted_fact: bool = False) -> TaskGraph:
        context = None
        if with_trusted_fact:
            context = {
                "trusted_facts": [
                    {
                        "fact": "Contract baseline is authoritative.",
                        "source": "Work Item revision 12",
                    }
                ]
            }
        packet = build_task_packet(
            objective="Update contracts.",
            scope=["contracts"],
            acceptance_criteria=["contract verification passes"],
            context=context,
        )
        return TaskGraph(
            nodes=(
                GraphNode(
                    node_id="contracts",
                    repository="contracts",
                    route="codex-balanced",
                    task_packet=packet,
                ),
            )
        )

    async def settled_executor(self, node: GraphNode) -> dict:
        return {
            "session_id": f"session-{node.node_id}",
            "turn_id": f"turn-{node.node_id}",
            "state": "settled",
            "agent_response": "result",
        }

    async def test_retry_feedback_repeating_trusted_fact_keeps_trusted_classification(self) -> None:
        graph = self.graph(with_trusted_fact=True)
        original_packet = graph.nodes[0].task_packet
        started = self.runtime.start_graph(graph, repository_names={"contracts"})
        run_id = started["graph_run_id"]
        reviewable = await self.runtime.delegate_next(
            run_id,
            executor=self.settled_executor,
        )

        self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [
                    {
                        "node_id": "contracts",
                        "action": "retry",
                        "feedback": ["contract baseline is authoritative."],
                    }
                ]
            ),
            expected_revision=reviewable["revision"],
        )

        seen_packets = []

        async def retry_executor(node: GraphNode) -> dict:
            seen_packets.append(node.task_packet)
            return {
                "session_id": "session-contracts-2",
                "turn_id": "turn-contracts-2",
                "state": "settled",
                "agent_response": "retry result",
            }

        await self.runtime.delegate_next(run_id, executor=retry_executor)

        self.assertEqual(len(seen_packets), 1)
        retry_packet = seen_packets[0]
        self.assertIsNot(retry_packet, original_packet)
        self.assertIsNotNone(retry_packet.context)
        self.assertEqual(
            [item.fact for item in retry_packet.context.trusted_facts],
            ["Contract baseline is authoritative."],
        )
        self.assertEqual(retry_packet.context.claims_to_investigate, ())
        self.assertEqual(
            [item.fact for item in original_packet.context.trusted_facts],
            ["Contract baseline is authoritative."],
        )

    async def test_recoverable_start_failure_persists_exact_session_for_resume(self) -> None:
        graph = self.graph()
        started = self.runtime.start_graph(graph, repository_names={"contracts"})
        run_id = started["graph_run_id"]

        async def recoverable_failure(_: GraphNode) -> dict:
            raise RecoverableRepoTaskExecutionError(
                "native result capture failed after session registration",
                session_id="native-session-contracts",
            )

        with self.assertRaises(RecoverableRepoTaskExecutionError):
            await self.runtime.delegate_next(run_id, executor=recoverable_failure)

        reviewable = self.runtime.get_graph(run_id)
        self.assertEqual(reviewable["graph_state"], "awaiting_review")
        self.assertEqual(reviewable["nodes"][0]["runtime_state"], "failed")
        self.assertEqual(
            reviewable["nodes"][0]["session_id"],
            "native-session-contracts",
        )

        retried = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [
                    {
                        "node_id": "contracts",
                        "action": "retry",
                        "resume_session": True,
                    }
                ]
            ),
            expected_revision=reviewable["revision"],
        )
        self.assertEqual(
            retried["decision_outcomes"][0]["retry_execution"]["session_id"],
            "native-session-contracts",
        )

        resumed = []

        async def should_not_start(_: GraphNode) -> dict:
            raise AssertionError("fresh START must not run")

        async def resume_executor(node: GraphNode, session_id: str) -> dict:
            resumed.append((node.node_id, session_id))
            return {
                "session_id": session_id,
                "turn_id": "turn-contracts-2",
                "state": "settled",
                "agent_response": "resumed",
            }

        await self.runtime.delegate_next(
            run_id,
            executor=should_not_start,
            resume_executor=resume_executor,
        )
        self.assertEqual(
            resumed,
            [("contracts", "native-session-contracts")],
        )


class RetryReviewMcpRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
        self.runtime = GraphRuntime(GraphRuntimeStore(db_path))
        self.runtime_patch = patch("task_graph_mcp._graph_runtime", self.runtime)
        self.registry_patch = patch(
            "task_graph_mcp._load_repo_registry",
            return_value={"backend": Path("/tmp/backend")},
        )
        self.runtime_patch.start()
        self.registry_patch.start()

    def tearDown(self) -> None:
        self.registry_patch.stop()
        self.runtime_patch.stop()
        self.temp.cleanup()

    async def test_direct_recovery_clause_becomes_graph_resume_session(self) -> None:
        graph = {
            "nodes": [
                {
                    "node_id": "backend",
                    "repository": "backend",
                    "route": "codex-balanced",
                    "task_packet": {
                        "objective": "Update backend.",
                        "scope": ["backend"],
                        "acceptance_criteria": ["backend verification passes"],
                    },
                }
            ]
        }
        preserved = "native-session-backend"
        direct_error = ToolError(
            "code=native_result_capture_failed; native final response was not captured; "
            "native session ownership was preserved and can be resumed with "
            f"session_id={preserved!r}; action=use the preserved session_id in this "
            "error to RESUME the exact native session after repairing result capture"
        )
        delegate = AsyncMock(side_effect=direct_error)

        with patch("task_graph_mcp.delegate_repo_task", delegate):
            async with Client(mcp) as client:
                started = (
                    await client.call_tool("start_graph", {"graph": graph})
                ).structured_content
                failed = await client.call_tool(
                    "delegate_next", {"graph_run_id": started["graph_run_id"]}
                )
                self.assertTrue(failed.is_error)
                current = (
                    await client.call_tool(
                        "get_graph", {"graph_run_id": started["graph_run_id"]}
                    )
                ).structured_content
                self.assertEqual(current["nodes"][0]["session_id"], preserved)

                retry = await client.call_tool(
                    "submit_decisions",
                    {
                        "graph_run_id": started["graph_run_id"],
                        "decisions": [
                            {
                                "node_id": "backend",
                                "action": "retry",
                                "resume_session": True,
                            }
                        ],
                        "expected_revision": current["revision"],
                    },
                )

        self.assertFalse(retry.is_error)
        self.assertEqual(
            retry.structured_content["decision_outcomes"][0]["retry_execution"]["session_id"],
            preserved,
        )


if __name__ == "__main__":
    unittest.main()
