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


def _resolve_ref(schema: dict, node: dict) -> dict:
    ref = node.get("$ref")
    if not ref:
        return node
    prefix = "#/$defs/"
    if not isinstance(ref, str) or not ref.startswith(prefix):
        raise AssertionError(f"unsupported schema ref: {ref!r}")
    return schema["$defs"][ref[len(prefix) :]]



def _literal_values(node: dict) -> list[str]:
    if "const" in node:
        return [node["const"]]
    return list(node.get("enum", []))


def _assert_no_open_nested_object_schema(test: unittest.TestCase, schema: dict) -> None:
    seen_refs: set[str] = set()

    def walk(node, *, is_root: bool = False):
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        ref = node.get("$ref")
        if isinstance(ref, str):
            if ref in seen_refs:
                return
            seen_refs.add(ref)
            walk(_resolve_ref(schema, node))
            return
        if not is_root and (node.get("type") == "object" or "properties" in node):
            test.assertFalse(
                node.get("additionalProperties", True),
                f"open object schema remains: {node!r}",
            )
        for key in ("properties", "items", "oneOf", "anyOf", "allOf"):
            value = node.get(key)
            if key == "properties" and isinstance(value, dict):
                walk(list(value.values()))
            else:
                walk(value)

    walk(schema, is_root=True)



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
                "get_node_review",
                "delegate_next",
                "submit_decisions",
            }.issubset(names)
        )

    async def test_graph_tools_expose_repo_task_as_the_only_public_node_kind(self) -> None:
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        for tool_name in ("start_graph", "reconcile_graph"):
            with self.subTest(tool=tool_name):
                schema = tools[tool_name].input_schema
                graph_schema = _resolve_ref(schema, schema["properties"]["graph"])
                node_schema = _resolve_ref(schema, graph_schema["properties"]["nodes"]["items"])
                kind_schema = node_schema["properties"]["kind"]

                allowed = kind_schema.get("enum")
                if allowed is None and "const" in kind_schema:
                    allowed = [kind_schema["const"]]
                self.assertEqual(allowed, ["repo_task"])
                self.assertEqual(kind_schema.get("default"), "repo_task")
                description = kind_schema.get("description", "")
                self.assertIn("omit this field", description)
                self.assertIn("Do not invent", description)

    async def test_graph_task_packet_public_schema_matches_canonical_fields(self) -> None:
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        canonical_fields = {
            "objective",
            "scope",
            "acceptance_criteria",
            "out_of_scope",
            "context",
            "constraints",
            "known_unknowns",
        }
        for tool_name in ("start_graph", "reconcile_graph"):
            with self.subTest(tool=tool_name):
                schema = tools[tool_name].input_schema
                graph_schema = _resolve_ref(schema, schema["properties"]["graph"])
                node_schema = _resolve_ref(schema, graph_schema["properties"]["nodes"]["items"])
                packet_schema = _resolve_ref(schema, node_schema["properties"]["task_packet"])
                self.assertEqual(set(packet_schema["properties"]), canonical_fields)
                self.assertEqual(
                    set(packet_schema["required"]),
                    {"objective", "scope", "acceptance_criteria"},
                )
                self.assertFalse(packet_schema.get("additionalProperties", True))
                self.assertEqual(packet_schema["properties"]["scope"].get("minItems"), 1)
                self.assertEqual(
                    packet_schema["properties"]["acceptance_criteria"].get("minItems"),
                    1,
                )

    async def test_submit_decisions_public_schema_constrains_actions_and_retry_metadata(self) -> None:
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        schema = tools["submit_decisions"].input_schema
        decisions = schema["properties"]["decisions"]
        self.assertEqual(decisions.get("minItems"), 1)
        item = decisions["items"]
        self.assertEqual(item.get("discriminator", {}).get("propertyName"), "action")
        variants = [_resolve_ref(schema, option) for option in item["oneOf"]]
        by_action = {
            _literal_values(variant["properties"]["action"])[0]: variant
            for variant in variants
        }
        self.assertEqual(set(by_action), {"accept", "retry", "replan", "block"})
        for action in ("accept", "replan", "block"):
            self.assertEqual(set(by_action[action]["properties"]), {"node_id", "action"})
            self.assertFalse(by_action[action].get("additionalProperties", True))
        retry = by_action["retry"]
        self.assertEqual(
            set(retry["properties"]),
            {"node_id", "action", "resume_session", "feedback"},
        )
        self.assertFalse(retry.get("additionalProperties", True))
        self.assertEqual(retry["properties"]["resume_session"].get("default"), False)
        self.assertEqual(
            schema["properties"]["expected_revision"].get("minimum"),
            0,
        )

    async def test_graph_public_input_schemas_have_no_open_nested_object_payloads(self) -> None:
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        for tool_name in (
            "start_graph",
            "get_graph",
            "get_node_review",
            "reconcile_graph",
            "delegate_next",
            "submit_decisions",
        ):
            with self.subTest(tool=tool_name):
                _assert_no_open_nested_object_schema(self, tools[tool_name].input_schema)

    async def test_submit_decisions_rejects_reason_at_public_schema_boundary(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "submit_decisions",
                {
                    "graph_run_id": "not-reached",
                    "expected_revision": 0,
                    "decisions": [
                        {
                            "node_id": "backend_e2e",
                            "action": "accept",
                            "reason": "review evidence",
                        }
                    ],
                },
            )

        self.assertTrue(result.is_error)
        self.assertIn("reason", error_text(result))

    async def test_start_graph_rejects_unknown_task_packet_field_at_public_schema_boundary(self) -> None:
        payload = graph_payload()
        payload["nodes"][0]["task_packet"]["reason"] = "invented semantic field"

        async with Client(mcp) as client:
            result = await client.call_tool("start_graph", {"graph": payload})

        self.assertTrue(result.is_error)
        self.assertIn("reason", error_text(result))

    async def test_start_graph_rejects_invented_kind_at_public_schema_boundary(self) -> None:
        payload = graph_payload()
        payload["nodes"][0]["kind"] = "task"

        async with Client(mcp) as client:
            result = await client.call_tool("start_graph", {"graph": payload})

        self.assertTrue(result.is_error)
        self.assertIn("repo_task", error_text(result))

    async def test_outer_loop_executes_reviews_and_accepts_one_node(self) -> None:
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
                self.assertEqual(started["review_required"], [])

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
                    delegated["review_required"][0]["acceptance_criteria"],
                    ["contract verification passes"],
                )
                self.assertNotIn("agent_response", delegated["results"][0])
                self.assertNotIn("result", delegated["nodes"][0])
                self.assertNotIn("result", delegated["review_required"][0])
                attempt_id = delegated["review_required"][0]["attempt_id"]

                review_result = await client.call_tool(
                    "get_node_review",
                    {
                        "graph_run_id": run_id,
                        "node_id": "contracts",
                        "attempt_id": attempt_id,
                    },
                )
                self.assertFalse(review_result.is_error)
                review = review_result.structured_content
                self.assertEqual(review["attempt_id"], attempt_id)
                self.assertEqual(
                    review["result"]["agent_response"],
                    "native final response",
                )

                current_result = await client.call_tool(
                    "get_graph", {"graph_run_id": run_id}
                )
                current = current_result.structured_content
                self.assertEqual(current["graph_state"], "awaiting_review")
                self.assertEqual(current["nodes"][0]["runtime_state"], "settled")
                self.assertNotIn("result", current["nodes"][0])
                self.assertEqual([item["node_id"] for item in current["review_required"]], ["contracts"])
                self.assertNotIn("result", current["review_required"][0])

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
                self.assertEqual(decided["review_required"], [])
                self.assertEqual(
                    decided["decision_outcomes"],
                    [
                        {
                            "node_id": "contracts",
                            "action": "accept",
                            "semantic_state": "satisfied",
                        }
                    ],
                )

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

    async def test_get_node_review_rejects_stale_review_locator(self) -> None:
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
                started = (
                    await client.call_tool("start_graph", {"graph": graph_payload()})
                ).structured_content
                reviewable = (
                    await client.call_tool(
                        "delegate_next", {"graph_run_id": started["graph_run_id"]}
                    )
                ).structured_content
                result = await client.call_tool(
                    "get_node_review",
                    {
                        "graph_run_id": started["graph_run_id"],
                        "node_id": "contracts",
                        "attempt_id": "attempt-stale",
                    },
                )

        self.assertTrue(result.is_error)
        self.assertIn("code=graph_state_conflict", error_text(result))
        self.assertIn("stale review attempt", error_text(result))
        self.assertTrue(reviewable["review_required"][0]["attempt_id"])

    async def test_get_node_review_hydrates_accepted_upstream_evidence_for_replan(self) -> None:
        delegate = AsyncMock(
            side_effect=[
                {
                    "session_id": "native-session-contracts",
                    "turn_id": "qiqi-turn-contracts",
                    "state": "settled",
                    "agent_response": "accepted contract evidence",
                },
                {
                    "session_id": "native-session-backend",
                    "turn_id": "qiqi-turn-backend",
                    "state": "settled",
                    "agent_response": "backend found a replan dependency",
                },
            ]
        )
        with patch("task_graph_mcp.delegate_repo_task", delegate):
            async with Client(mcp) as client:
                started = (
                    await client.call_tool("start_graph", {"graph": graph_payload()})
                ).structured_content
                contracts_review = (
                    await client.call_tool(
                        "delegate_next", {"graph_run_id": started["graph_run_id"]}
                    )
                ).structured_content
                accepted = (
                    await client.call_tool(
                        "submit_decisions",
                        {
                            "graph_run_id": started["graph_run_id"],
                            "decisions": [
                                {"node_id": "contracts", "action": "accept"}
                            ],
                            "expected_revision": contracts_review["revision"],
                        },
                    )
                ).structured_content
                accepted_attempt_id = accepted["nodes"][0]["current_attempt_id"]

                backend_review = (
                    await client.call_tool(
                        "delegate_next", {"graph_run_id": started["graph_run_id"]}
                    )
                ).structured_content
                self.assertEqual(backend_review["graph_state"], "awaiting_review")

                evidence_result = await client.call_tool(
                    "get_node_review",
                    {
                        "graph_run_id": started["graph_run_id"],
                        "node_id": "contracts",
                        "attempt_id": accepted_attempt_id,
                    },
                )

        self.assertFalse(evidence_result.is_error)
        evidence = evidence_result.structured_content
        self.assertEqual(evidence["semantic_state"], "satisfied")
        self.assertEqual(
            evidence["result"]["agent_response"],
            "accepted contract evidence",
        )

    async def test_replan_decision_blocks_current_graph_and_returns_handoff_signal(self) -> None:
        delegate = AsyncMock(
            return_value={
                "session_id": "native-session-contracts",
                "turn_id": "qiqi-turn-contracts",
                "state": "settled",
                "agent_response": "discovered a new authoritative dependency",
            }
        )
        with patch("task_graph_mcp.delegate_repo_task", delegate):
            async with Client(mcp) as client:
                started = (
                    await client.call_tool("start_graph", {"graph": graph_payload()})
                ).structured_content
                reviewable = (
                    await client.call_tool(
                        "delegate_next", {"graph_run_id": started["graph_run_id"]}
                    )
                ).structured_content
                result = await client.call_tool(
                    "submit_decisions",
                    {
                        "graph_run_id": started["graph_run_id"],
                        "decisions": [{"node_id": "contracts", "action": "replan"}],
                        "expected_revision": reviewable["revision"],
                    },
                )

        self.assertFalse(result.is_error)
        payload = result.structured_content
        self.assertEqual(payload["graph_state"], "blocked")
        self.assertEqual(payload["replan_required_nodes"], ["contracts"])
        self.assertEqual(payload["nodes"][0]["semantic_state"], "blocked")
        self.assertEqual(payload["review_required"], [])

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
        self.assertEqual(payload["review_required"][0]["runtime_state"], "blocked")

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
