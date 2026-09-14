from pathlib import Path
import unittest

import yaml


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_PATH = WORKSPACE_ROOT / "instructions" / "agent-routing.yaml"
EXAMPLES = {
    "claude": WORKSPACE_ROOT / "docs" / "examples" / "agent-routing.claude-code.yaml",
    "codex": WORKSPACE_ROOT / "docs" / "examples" / "agent-routing.codex.yaml",
}
FORBIDDEN_LEGACY_TOKENS = (
    "{result_dir}",
    "result_path",
    "prompt_transport",
    "result.schema.json",
)
MCP_OWNED_ROUTE_ARGS = {
    "--settings",
    "--dangerously-bypass-hook-trust",
    "--enable",
    "--disable",
}


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


class RoutingExampleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical = load_yaml(CANONICAL_PATH)

    def test_examples_match_canonical_agent_and_routes(self) -> None:
        for agent_name, path in EXAMPLES.items():
            with self.subTest(agent=agent_name):
                example = load_yaml(path)
                self.assertEqual(2, example.get("version"))
                self.assertEqual(
                    {agent_name: self.canonical["agents"][agent_name]},
                    example.get("agents"),
                )
                expected_routes = {
                    name: route
                    for name, route in self.canonical["routes"].items()
                    if route.get("agent") == agent_name
                }
                self.assertEqual(expected_routes, example.get("routes"))

    def test_examples_preserve_native_handoff_contract(self) -> None:
        for agent_name, path in EXAMPLES.items():
            with self.subTest(agent=agent_name):
                example = load_yaml(path)
                agent = example["agents"][agent_name]
                for key in ("start_args", "resume_args"):
                    values = agent[key]
                    self.assertIsInstance(values, list)
                    self.assertEqual(
                        1,
                        values.count("{handoff_args}"),
                        f"{path.name}:{agent_name}.{key} must contain exactly one handoff slot",
                    )
                self.assertNotIn("{session_id}", agent["start_args"])
                self.assertIn("{session_id}", agent["resume_args"])

    def test_examples_reject_legacy_result_transport_and_mcp_owned_route_args(self) -> None:
        for agent_name, path in EXAMPLES.items():
            with self.subTest(agent=agent_name):
                text = path.read_text(encoding="utf-8")
                for token in FORBIDDEN_LEGACY_TOKENS:
                    self.assertNotIn(token, text)

                example = load_yaml(path)
                for route_name, route in example["routes"].items():
                    args = route.get("args", [])
                    self.assertIsInstance(args, list)
                    self.assertFalse(
                        any(
                            value in MCP_OWNED_ROUTE_ARGS or value.startswith("hooks.")
                            for value in args
                        ),
                        f"{path.name}:{route_name} must not configure MCP-owned handoff flags",
                    )


if __name__ == "__main__":
    unittest.main()
