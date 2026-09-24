from __future__ import annotations

import asyncio
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
from task_graph_runtime import GraphRuntime, decisions_from_payload  # noqa: E402
from task_graph_store import GraphRuntimeStore  # noqa: E402


class ParallelWaveRuntimeTests(unittest.IsolatedAsyncioTestCase):
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

    def node(
        self,
        node_id: str,
        repository: str,
        *,
        depends_on: tuple[str, ...] = (),
    ) -> GraphNode:
        return GraphNode(
            node_id=node_id,
            repository=repository,
            route="codex-balanced",
            depends_on=depends_on,
            task_packet=self.packet(f"Implement {node_id}."),
        )

    async def test_independent_repositories_execute_concurrently_in_one_wave(self) -> None:
        graph = TaskGraph(
            nodes=(
                self.node("backend", "backend"),
                self.node("frontend", "frontend"),
            )
        )
        started = self.runtime.start_graph(
            graph,
            repository_names={"backend", "frontend"},
        )
        run_id = started["graph_run_id"]

        entered: set[str] = set()
        release = asyncio.Event()

        async def executor(node: GraphNode) -> dict:
            entered.add(node.node_id)
            if len(entered) == 2:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            return {
                "session_id": f"session-{node.node_id}",
                "turn_id": f"turn-{node.node_id}",
                "state": "settled",
                "agent_response": f"result-{node.node_id}",
            }

        result = await self.runtime.delegate_next(run_id, executor=executor)

        self.assertEqual(entered, {"backend", "frontend"})
        self.assertEqual(
            [item["node_id"] for item in result["results"]],
            ["backend", "frontend"],
        )
        self.assertEqual(result["graph_state"], "awaiting_review")
        self.assertEqual(
            [item["node_id"] for item in result["review_required"]],
            ["backend", "frontend"],
        )
        attempts = [
            self.store.list_attempts(run_id, node_id)[0]
            for node_id in ("backend", "frontend")
        ]
        self.assertEqual({item["wave_id"] for item in attempts}, {result["wave_id"]})
        self.assertTrue(all(item["runtime_state"] == "settled" for item in attempts))

    async def test_same_repository_nodes_are_serialized_across_waves(self) -> None:
        graph = TaskGraph(
            nodes=(
                self.node("first", "shared"),
                self.node("second", "shared"),
            )
        )
        started = self.runtime.start_graph(graph, repository_names={"shared"})
        run_id = started["graph_run_id"]
        calls: list[str] = []

        async def executor(node: GraphNode) -> dict:
            calls.append(node.node_id)
            return {
                "session_id": f"session-{node.node_id}",
                "turn_id": f"turn-{node.node_id}",
                "state": "settled",
                "agent_response": "done",
            }

        first = await self.runtime.delegate_next(run_id, executor=executor)
        self.assertEqual([item["node_id"] for item in first["results"]], ["first"])
        self.assertEqual(self.store.list_attempts(run_id, "second"), [])

        accepted = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload([{"node_id": "first", "action": "accept"}]),
            expected_revision=first["revision"],
        )
        self.assertEqual(accepted["graph_state"], "ready")

        second = await self.runtime.delegate_next(run_id, executor=executor)
        self.assertEqual([item["node_id"] for item in second["results"]], ["second"])
        self.assertEqual(calls, ["first", "second"])

    async def test_per_node_review_retries_only_rejected_wave_member(self) -> None:
        graph = TaskGraph(
            nodes=(
                self.node("a", "repo-a"),
                self.node("b", "repo-b"),
                self.node("c", "repo-c"),
            )
        )
        started = self.runtime.start_graph(
            graph,
            repository_names={"repo-a", "repo-b", "repo-c"},
        )
        run_id = started["graph_run_id"]

        async def executor(node: GraphNode) -> dict:
            attempt_number = len(self.store.list_attempts(run_id, node.node_id))
            return {
                "session_id": f"session-{node.node_id}-{attempt_number}",
                "turn_id": f"turn-{node.node_id}-{attempt_number}",
                "state": "settled",
                "agent_response": "done",
            }

        wave = await self.runtime.delegate_next(run_id, executor=executor)
        reviewed = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [
                    {"node_id": "a", "action": "accept"},
                    {"node_id": "b", "action": "retry"},
                    {"node_id": "c", "action": "accept"},
                ]
            ),
            expected_revision=wave["revision"],
        )

        self.assertEqual(reviewed["graph_state"], "ready")
        self.assertEqual(reviewed["runnable_nodes"], ["b"])
        retry_wave = await self.runtime.delegate_next(run_id, executor=executor)
        self.assertEqual([item["node_id"] for item in retry_wave["results"]], ["b"])
        self.assertEqual(len(self.store.list_attempts(run_id, "a")), 1)
        self.assertEqual(len(self.store.list_attempts(run_id, "b")), 2)
        self.assertEqual(len(self.store.list_attempts(run_id, "c")), 1)

    async def test_retry_resume_and_newly_runnable_fresh_node_share_wave(self) -> None:
        graph = TaskGraph(
            nodes=(
                self.node("a", "repo-a"),
                self.node("b", "repo-b"),
                self.node("c", "repo-c", depends_on=("b",)),
            )
        )
        started = self.runtime.start_graph(
            graph,
            repository_names={"repo-a", "repo-b", "repo-c"},
        )
        run_id = started["graph_run_id"]

        async def initial_executor(node: GraphNode) -> dict:
            return {
                "session_id": f"session-{node.node_id}",
                "turn_id": f"turn-{node.node_id}-1",
                "state": "settled",
                "agent_response": "initial",
            }

        first = await self.runtime.delegate_next(run_id, executor=initial_executor)
        self.assertEqual(
            [item["node_id"] for item in first["results"]],
            ["a", "b"],
        )
        after_review = self.runtime.submit_decisions(
            run_id,
            decisions_from_payload(
                [
                    {
                        "node_id": "a",
                        "action": "retry",
                        "resume_session": True,
                        "feedback": ["Fix remaining issue."],
                    },
                    {"node_id": "b", "action": "accept"},
                ]
            ),
            expected_revision=first["revision"],
        )
        self.assertEqual(after_review["graph_state"], "ready")
        self.assertEqual(after_review["runnable_nodes"], ["a", "c"])

        fresh_calls: list[str] = []
        resume_calls: list[tuple[str, str]] = []

        async def fresh_executor(node: GraphNode) -> dict:
            fresh_calls.append(node.node_id)
            return {
                "session_id": f"session-{node.node_id}",
                "turn_id": f"turn-{node.node_id}-1",
                "state": "settled",
                "agent_response": "fresh",
            }

        async def resume_executor(node: GraphNode, session_id: str) -> dict:
            resume_calls.append((node.node_id, session_id))
            return {
                "session_id": session_id,
                "turn_id": "turn-a-2",
                "state": "settled",
                "agent_response": "resumed",
            }

        second = await self.runtime.delegate_next(
            run_id,
            executor=fresh_executor,
            resume_executor=resume_executor,
        )
        self.assertEqual(
            [item["node_id"] for item in second["results"]],
            ["a", "c"],
        )
        self.assertEqual(resume_calls, [("a", "session-a")])
        self.assertEqual(fresh_calls, ["c"])
        self.assertTrue(second["results"][0]["resume_session"])
        self.assertFalse(second["results"][1]["resume_session"])

    async def test_fast_failure_waits_for_sibling_before_closing_wave(self) -> None:
        graph = TaskGraph(
            nodes=(
                self.node("fails", "repo-a"),
                self.node("settles", "repo-b"),
            )
        )
        started = self.runtime.start_graph(
            graph,
            repository_names={"repo-a", "repo-b"},
        )
        run_id = started["graph_run_id"]
        sibling_finished = asyncio.Event()

        async def executor(node: GraphNode) -> dict:
            if node.node_id == "fails":
                raise RuntimeError("child failed")
            await asyncio.sleep(0.02)
            sibling_finished.set()
            return {
                "session_id": "session-settles",
                "turn_id": "turn-settles",
                "state": "settled",
                "agent_response": "done",
            }

        with self.assertRaisesRegex(RuntimeError, "child failed"):
            await self.runtime.delegate_next(run_id, executor=executor)

        self.assertTrue(sibling_finished.is_set())
        current = self.runtime.get_graph(run_id)
        self.assertIsNone(current["current_wave_id"])
        self.assertEqual(current["graph_state"], "awaiting_review")
        states = {item["node_id"]: item for item in current["nodes"]}
        self.assertEqual(states["fails"]["runtime_state"], "failed")
        self.assertEqual(states["settles"]["runtime_state"], "settled")
        self.assertEqual(
            {item["node_id"] for item in current["review_required"]},
            {"fails", "settles"},
        )

    async def test_cancelling_wave_terminalizes_all_claimed_attempts(self) -> None:
        graph = TaskGraph(
            nodes=(
                self.node("a", "repo-a"),
                self.node("b", "repo-b"),
            )
        )
        started = self.runtime.start_graph(
            graph,
            repository_names={"repo-a", "repo-b"},
        )
        run_id = started["graph_run_id"]
        entered: set[str] = set()
        all_entered = asyncio.Event()
        never = asyncio.Event()

        async def executor(node: GraphNode) -> dict:
            entered.add(node.node_id)
            if len(entered) == 2:
                all_entered.set()
            await never.wait()
            raise AssertionError("unreachable")

        task = asyncio.create_task(self.runtime.delegate_next(run_id, executor=executor))
        await asyncio.wait_for(all_entered.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        current = self.runtime.get_graph(run_id)
        self.assertIsNone(current["current_wave_id"])
        self.assertEqual(current["graph_state"], "awaiting_review")
        for node_id in ("a", "b"):
            attempts = self.store.list_attempts(run_id, node_id)
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0]["runtime_state"], "failed")
            self.assertEqual(
                attempts[0]["result"]["failure_type"],
                "execution_cancelled",
            )


class ParallelWaveMcpTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
        self.runtime = GraphRuntime(GraphRuntimeStore(db_path))
        self.runtime_patch = patch("task_graph_mcp._graph_runtime", self.runtime)
        self.registry_patch = patch(
            "task_graph_mcp._load_repo_registry",
            return_value={
                "backend": Path("/tmp/backend"),
                "frontend": Path("/tmp/frontend"),
                "mobile": Path("/tmp/mobile"),
                "worker": Path("/tmp/worker"),
            },
        )
        self.runtime_patch.start()
        self.registry_patch.start()

    def tearDown(self) -> None:
        self.registry_patch.stop()
        self.runtime_patch.stop()
        self.temp.cleanup()

    async def test_public_delegate_next_returns_multi_node_wave_results(self) -> None:
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
                },
                {
                    "node_id": "frontend",
                    "repository": "frontend",
                    "route": "codex-balanced",
                    "task_packet": {
                        "objective": "Update frontend.",
                        "scope": ["frontend"],
                        "acceptance_criteria": ["frontend verification passes"],
                    },
                },
            ]
        }
        entered: set[str] = set()
        release = asyncio.Event()

        async def delegated(**kwargs):
            repository = kwargs["repository"]
            entered.add(repository)
            if len(entered) == 2:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            return {
                "session_id": f"session-{repository}",
                "turn_id": f"turn-{repository}",
                "state": "settled",
                "agent_response": f"result-{repository}",
            }

        delegate = AsyncMock(side_effect=delegated)
        with patch("task_graph_mcp.delegate_repo_task", delegate):
            async with Client(mcp) as client:
                started = (
                    await client.call_tool("start_graph", {"graph": graph})
                ).structured_content
                result = await client.call_tool(
                    "delegate_next",
                    {"graph_run_id": started["graph_run_id"]},
                )

        self.assertFalse(result.is_error)
        payload = result.structured_content
        self.assertEqual(
            [item["node_id"] for item in payload["results"]],
            ["backend", "frontend"],
        )
        self.assertEqual(payload["graph_state"], "awaiting_review")
        self.assertEqual(delegate.await_count, 2)

    async def test_four_node_wave_uses_one_batch_review_hydration_call(self) -> None:
        repositories = ("backend", "frontend", "mobile", "worker")
        graph = {
            "nodes": [
                {
                    "node_id": repository,
                    "repository": repository,
                    "route": "codex-balanced",
                    "task_packet": {
                        "objective": f"Update {repository}.",
                        "scope": [repository],
                        "acceptance_criteria": [f"{repository} verification passes"],
                    },
                }
                for repository in repositories
            ]
        }

        async def delegated(**kwargs):
            repository = kwargs["repository"]
            return {
                "session_id": f"session-{repository}",
                "turn_id": f"turn-{repository}",
                "state": "settled",
                "agent_response": f"result-{repository}",
            }

        delegate = AsyncMock(side_effect=delegated)
        with patch("task_graph_mcp.delegate_repo_task", delegate):
            async with Client(mcp) as client:
                started = (
                    await client.call_tool("start_graph", {"graph": graph})
                ).structured_content
                delegated_wave = (
                    await client.call_tool(
                        "delegate_next",
                        {"graph_run_id": started["graph_run_id"]},
                    )
                ).structured_content
                self.assertEqual(
                    [item["node_id"] for item in delegated_wave["review_required"]],
                    list(repositories),
                )

                review_call = await client.call_tool(
                    "get_node_reviews",
                    {
                        "graph_run_id": started["graph_run_id"],
                        "expected_revision": delegated_wave["revision"],
                        "reviews": [
                            {
                                "node_id": item["node_id"],
                                "attempt_id": item["attempt_id"],
                            }
                            for item in delegated_wave["review_required"]
                        ],
                    },
                )
                self.assertFalse(review_call.is_error)
                hydrated = review_call.structured_content
                self.assertEqual(
                    [item["node_id"] for item in hydrated["reviews"]],
                    list(repositories),
                )
                self.assertEqual(
                    [item["result"]["agent_response"] for item in hydrated["reviews"]],
                    [f"result-{repository}" for repository in repositories],
                )

                decided = await client.call_tool(
                    "submit_decisions",
                    {
                        "graph_run_id": started["graph_run_id"],
                        "expected_revision": delegated_wave["revision"],
                        "decisions": [
                            {"node_id": repository, "action": "accept"}
                            for repository in repositories
                        ],
                    },
                )

        self.assertFalse(decided.is_error)
        self.assertEqual(decided.structured_content["graph_state"], "complete")
        self.assertEqual(delegate.await_count, 4)


if __name__ == "__main__":
    unittest.main()
