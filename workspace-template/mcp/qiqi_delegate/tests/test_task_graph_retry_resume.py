from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import build_task_packet  # noqa: E402
from mcp import Client  # noqa: E402
from task_graph import GraphNode, TaskGraph  # noqa: E402
from task_graph_mcp import mcp  # noqa: E402
from task_graph_runtime import (  # noqa: E402
    GraphRuntime,
    decisions_from_payload,
)
from task_graph_store import GraphRuntimeStore  # noqa: E402


class SelectiveRetryRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
        self.store = GraphRuntimeStore(db_path)
        self.runtime = GraphRuntime(self.store)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def packet(self, objective: str):
        return build_task_packet(
            objective=objective,
            scope=["repository-local implementation"],
            acceptance_criteria=["focused verification passes"],
        )

    def graph(self) -> TaskGraph:
        return TaskGraph(
            nodes=(
                GraphNode(
                    node_id="contracts",
                    repository="contracts",
                    route="codex-balanced",
                    task_packet=self.packet("Update shared contract."),
                ),
                GraphNode(
                    node_id="backend",
                    repository="backend",
                    route="codex-balanced",
                    depends_on=("contracts",),
                    task_packet=self.packet("Update backend consumer."),
                ),
            )
        )

    async def test_fresh_retry_uses_new_taskpacket_snapshot_with_review_feedback(self) -> None:
        graph = self.graph()
        original_packet = graph.nodes[0].task_packet
        started = self.runtime.start_graph(
            graph,
            repository_names={"contracts", "backend"},
        )
        run_id = started["graph_run_id"]

        async def first_executor(node: GraphNode) -> dict:
            self.assertIs(node.task_packet, original_packet)
            return {
                "session_id": "session-contracts-1",
                "turn_id": "turn-contracts-1",
                "state": "settled",
                "agent_response": "first result",
            }

        reviewable = await self.runtime.delegate_next(run_id, executor=first_executor)
        retried = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [
                    {
                        "node_id": "contracts",
                        "action": "retry",
                        "resume_session": False,
                        "feedback": ["Contract verification still fails."],
                    }
                ]
            ),
            expected_revision=reviewable["revision"],
        )

        self.assertEqual(retried["graph_state"], "ready")
        self.assertEqual(retried["runnable_nodes"], ["contracts"])
        self.assertFalse(retried["nodes"][0]["retry_pending"]["resume_session"])
        self.assertEqual(
            retried["nodes"][0]["retry_pending"]["feedback"],
            ["Contract verification still fails."],
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

        second = await self.runtime.delegate_next(run_id, executor=retry_executor)

        self.assertEqual(second["results"][0]["node_id"], "contracts")
        self.assertFalse(second["results"][0]["resume_session"])
        self.assertEqual(len(seen_packets), 1)
        retry_packet = seen_packets[0]
        self.assertIsNot(retry_packet, original_packet)
        self.assertEqual(retry_packet.objective, original_packet.objective)
        self.assertEqual(retry_packet.scope, original_packet.scope)
        self.assertEqual(
            retry_packet.acceptance_criteria,
            original_packet.acceptance_criteria,
        )
        self.assertIsNone(original_packet.context)
        self.assertIsNotNone(retry_packet.context)
        claim = retry_packet.context.claims_to_investigate[-1]
        self.assertEqual(claim.claim, "Contract verification still fails.")
        self.assertEqual(claim.source, "QiQi semantic review")

        attempts = self.store.list_attempts(run_id, "contracts")
        self.assertEqual(len(attempts), 2)
        self.assertFalse(attempts[1]["resume_session"])
        self.assertEqual(attempts[1]["session_id"], "session-contracts-2")
        self.assertEqual(self.store.list_attempts(run_id, "backend"), [])

    async def test_retry_resume_uses_exact_previous_native_session(self) -> None:
        graph = self.graph()
        started = self.runtime.start_graph(
            graph,
            repository_names={"contracts", "backend"},
        )
        run_id = started["graph_run_id"]

        async def first_executor(_: GraphNode) -> dict:
            return {
                "session_id": "session-contracts",
                "turn_id": "turn-contracts-1",
                "state": "settled",
                "agent_response": "first result",
            }

        reviewable = await self.runtime.delegate_next(run_id, executor=first_executor)
        retried = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [
                    {
                        "node_id": "contracts",
                        "action": "retry",
                        "resume_session": True,
                        "feedback": ["Fix the remaining assertion."],
                    }
                ]
            ),
            expected_revision=reviewable["revision"],
        )
        self.assertEqual(
            retried["decision_outcomes"][0]["retry_execution"]["session_id"],
            "session-contracts",
        )

        async def should_not_start(_: GraphNode) -> dict:
            raise AssertionError("fresh START executor must not run for RESUME")

        resumed: list[tuple[str, str]] = []

        async def resume_executor(node: GraphNode, session_id: str) -> dict:
            resumed.append((node.node_id, session_id))
            return {
                "session_id": session_id,
                "turn_id": "turn-contracts-2",
                "state": "settled",
                "agent_response": "resumed result",
            }

        second = await self.runtime.delegate_next(
            run_id,
            executor=should_not_start,
            resume_executor=resume_executor,
        )

        self.assertEqual(resumed, [("contracts", "session-contracts")])
        self.assertTrue(second["results"][0]["resume_session"])
        attempts = self.store.list_attempts(run_id, "contracts")
        self.assertEqual(len(attempts), 2)
        self.assertTrue(attempts[1]["resume_session"])
        self.assertEqual(attempts[1]["session_id"], "session-contracts")

    async def test_resume_retry_without_previous_session_fails_before_semantic_transition(self) -> None:
        graph = self.graph()
        started = self.runtime.start_graph(
            graph,
            repository_names={"contracts", "backend"},
        )
        run_id = started["graph_run_id"]

        async def exploding_executor(_: GraphNode) -> dict:
            raise RuntimeError("failed before native session capture")

        with self.assertRaisesRegex(RuntimeError, "failed before native session capture"):
            await self.runtime.delegate_next(run_id, executor=exploding_executor)

        reviewable = self.runtime.get_graph(run_id)
        with self.assertRaisesRegex(RuntimeError, "no previous native session"):
            self.runtime.submit_decisions(
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

        current = self.runtime.get_graph(run_id)
        self.assertEqual(current["graph_state"], "awaiting_review")
        self.assertEqual(current["nodes"][0]["runtime_state"], "failed")
        self.assertIsNone(current["nodes"][0]["retry_pending"])

    async def test_retry_keeps_accepted_dependency_satisfied(self) -> None:
        graph = self.graph()
        started = self.runtime.start_graph(
            graph,
            repository_names={"contracts", "backend"},
        )
        run_id = started["graph_run_id"]

        async def executor(node: GraphNode) -> dict:
            return {
                "session_id": f"session-{node.node_id}",
                "turn_id": f"turn-{node.node_id}",
                "state": "settled",
                "agent_response": f"result-{node.node_id}",
            }

        contracts_review = await self.runtime.delegate_next(run_id, executor=executor)
        after_accept = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [{"node_id": "contracts", "action": "accept"}]
            ),
            expected_revision=contracts_review["revision"],
        )
        self.assertEqual(after_accept["runnable_nodes"], ["backend"])

        backend_review = await self.runtime.delegate_next(run_id, executor=executor)
        after_retry = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [{"node_id": "backend", "action": "retry"}]
            ),
            expected_revision=backend_review["revision"],
        )

        states = {item["node_id"]: item for item in after_retry["nodes"]}
        self.assertEqual(states["contracts"]["semantic_state"], "satisfied")
        self.assertEqual(states["backend"]["semantic_state"], "pending")
        self.assertEqual(after_retry["runnable_nodes"], ["backend"])
        self.assertEqual(len(self.store.list_attempts(run_id, "contracts")), 1)

    def test_retry_transport_is_strict(self) -> None:
        retry = decisions_from_payload(
            [
                {
                    "node_id": "backend",
                    "action": "retry",
                    "resume_session": True,
                    "feedback": ["Investigate the failing criterion."],
                }
            ]
        )[0]
        self.assertTrue(retry.resume_session)
        self.assertEqual(retry.feedback, ("Investigate the failing criterion.",))

        with self.assertRaisesRegex(ValueError, "only valid for action='retry'"):
            decisions_from_payload(
                [
                    {
                        "node_id": "backend",
                        "action": "accept",
                        "resume_session": False,
                    }
                ]
            )
        with self.assertRaisesRegex(ValueError, "feedback must be a list"):
            decisions_from_payload(
                [
                    {
                        "node_id": "backend",
                        "action": "retry",
                        "feedback": "not-a-list",
                    }
                ]
            )


class SelectiveRetryMcpTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_mcp_retry_resume_forwards_exact_session_and_feedback_context(self) -> None:
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
        delegate = AsyncMock(
            side_effect=[
                {
                    "session_id": "native-session-backend",
                    "turn_id": "turn-backend-1",
                    "state": "settled",
                    "agent_response": "first result",
                },
                {
                    "session_id": "native-session-backend",
                    "turn_id": "turn-backend-2",
                    "state": "settled",
                    "agent_response": "resumed result",
                },
            ]
        )

        with patch("task_graph_mcp.delegate_repo_task", delegate):
            async with Client(mcp) as client:
                started = (
                    await client.call_tool("start_graph", {"graph": graph})
                ).structured_content
                first = (
                    await client.call_tool(
                        "delegate_next", {"graph_run_id": started["graph_run_id"]}
                    )
                ).structured_content
                retried_result = await client.call_tool(
                    "submit_decisions",
                    {
                        "graph_run_id": started["graph_run_id"],
                        "decisions": [
                            {
                                "node_id": "backend",
                                "action": "retry",
                                "resume_session": True,
                                "feedback": ["Backend verification still fails."],
                            }
                        ],
                        "expected_revision": first["revision"],
                    },
                )
                self.assertFalse(retried_result.is_error)
                second_result = await client.call_tool(
                    "delegate_next", {"graph_run_id": started["graph_run_id"]}
                )
                self.assertFalse(second_result.is_error)
                second = second_result.structured_content

        self.assertEqual(delegate.await_count, 2)
        first_call = delegate.await_args_list[0].kwargs
        second_call = delegate.await_args_list[1].kwargs
        self.assertIsNone(first_call["session_id"])
        self.assertEqual(second_call["session_id"], "native-session-backend")
        self.assertIsNotNone(second_call["context"])
        claims = second_call["context"].claims_to_investigate
        self.assertEqual(claims[-1].claim, "Backend verification still fails.")
        self.assertEqual(claims[-1].source, "QiQi semantic review")
        self.assertTrue(second["results"][0]["resume_session"])


if __name__ == "__main__":
    unittest.main()
