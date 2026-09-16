from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import (
    ClaimToInvestigateInput,
    TaskContextInput,
    TrustedFactInput,
    mcp,
)


FORBIDDEN_PUBLIC_FIELDS = {
    "user_request",
    "required_context",
    "verification",
    "work_item_id",
    "work_item_ref",
    "work_item_revision",
}
TRACKED_LOCATOR_EXAMPLE = (
    "work_item_path=<absolute dossier path>; id=<canonical id>; revision=<n>"
)


def _resolve_ref(schema: dict, node: dict) -> dict:
    ref = node.get("$ref")
    if not ref:
        return node
    prefix = "#/$defs/"
    if not isinstance(ref, str) or not ref.startswith(prefix):
        raise AssertionError(f"unsupported schema ref: {ref!r}")
    return schema["$defs"][ref[len(prefix) :]]


def _non_null_schema(schema: dict, node: dict) -> dict:
    options = node.get("anyOf")
    if not options:
        return _resolve_ref(schema, node)
    resolved = [_resolve_ref(schema, option) for option in options]
    non_null = [option for option in resolved if option.get("type") != "null"]
    if len(non_null) != 1:
        raise AssertionError(f"expected exactly one non-null schema, got {resolved!r}")
    return non_null[0]


def _harness_source_root(workspace: Path) -> Path | None:
    candidate = workspace.parent
    workspace_template = candidate / "workspace-template"
    markers = (
        candidate / "scripts" / "migrate-workspace.sh",
        candidate / "migrations" / "0024-filesystem-work-item.json",
    )
    if (
        workspace_template.is_dir()
        and workspace_template.resolve() == workspace.resolve()
        and all(path.is_file() for path in markers)
    ):
        return candidate
    return None


def _read_locator_contract_sources(workspace: Path) -> dict[str, str]:
    sources = {
        "server": (workspace / "mcp" / "qiqi_delegate" / "server.py").read_text(
            encoding="utf-8"
        ),
        "workspace": (workspace / "AGENTS.md").read_text(encoding="utf-8"),
    }

    harness_root = _harness_source_root(workspace)
    if harness_root is not None:
        template_paths = {
            "repo": harness_root / "repo-template" / "AGENTS.md",
            "skill": (
                harness_root
                / "work-item-template"
                / "skills"
                / "work-item"
                / "SKILL.md"
            ),
        }
        missing = [name for name, path in template_paths.items() if not path.is_file()]
        if missing:
            raise AssertionError(
                "incomplete harness source tree; missing locator contract source(s): "
                + ", ".join(sorted(missing))
            )
        for name, path in template_paths.items():
            sources[name] = path.read_text(encoding="utf-8")
    return sources


class PublicTaskSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tools = asyncio.run(mcp.list_tools())
        matching = [tool for tool in tools if tool.name == "delegate_repo_task"]
        if len(matching) != 1:
            raise AssertionError(f"expected one delegate_repo_task tool, got {len(matching)}")
        cls.tool = matching[0]
        cls.schema = cls.tool.input_schema
        cls.workspace = Path(__file__).resolve().parents[3]

    def test_required_and_forbidden_top_level_fields(self) -> None:
        properties = self.schema["properties"]
        self.assertEqual(
            set(self.schema["required"]),
            {"repository", "route", "objective", "scope", "acceptance_criteria"},
        )
        self.assertTrue(FORBIDDEN_PUBLIC_FIELDS.isdisjoint(properties))

    def test_repository_field_documents_registry_name_contract(self) -> None:
        repository = self.schema["properties"]["repository"]
        description = repository.get("description", "")
        self.assertIn("repos.yaml", description)
        self.assertIn("name", description)
        self.assertIn("Do not pass a filesystem path", description)

    def test_context_exposes_only_normative_nested_fields(self) -> None:
        context = _non_null_schema(self.schema, self.schema["properties"]["context"])
        self.assertEqual(
            set(context["properties"]),
            {"trusted_facts", "claims_to_investigate"},
        )
        self.assertFalse(context.get("additionalProperties", True))

        trusted = context["properties"]["trusted_facts"]
        trusted_item = _resolve_ref(self.schema, trusted["items"])
        self.assertEqual(set(trusted_item["properties"]), {"fact", "source"})
        self.assertEqual(set(trusted_item["required"]), {"fact", "source"})
        self.assertFalse(trusted_item.get("additionalProperties", True))

        claims = context["properties"]["claims_to_investigate"]
        claim_item = _resolve_ref(self.schema, claims["items"])
        self.assertEqual(set(claim_item["properties"]), {"claim", "source"})
        self.assertEqual(set(claim_item["required"]), {"claim", "source"})
        self.assertFalse(claim_item.get("additionalProperties", True))

    def test_tracked_work_item_locator_is_allowed_without_weakening_packet_semantics(self) -> None:
        description = self.tool.description or ""
        self.assertIn("context.trusted_facts", description)
        self.assertIn(TRACKED_LOCATOR_EXAMPLE, description)
        self.assertNotIn("work_item=<id>; revision=<revision>", description)
        self.assertIn("not a substitute for", description)
        self.assertIn("objective/scope/acceptance", description)

    def test_tracked_locator_contract_does_not_drift_across_boundaries(self) -> None:
        sources = _read_locator_contract_sources(self.workspace)
        for name, text in sources.items():
            with self.subTest(source=name):
                self.assertIn("work_item_path=", text)
                self.assertIn("id=<canonical", text)
                self.assertIn("revision=<", text)
                self.assertNotIn("work_item=<id>; revision=<revision>", text)
        self.assertGreaterEqual(sources["server"].count(TRACKED_LOCATOR_EXAMPLE), 2)

    def test_materialized_workspace_does_not_require_harness_sibling_templates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            workspace = parent / "multi-repo"
            server = workspace / "mcp" / "qiqi_delegate" / "server.py"
            server.parent.mkdir(parents=True)
            server.write_text(TRACKED_LOCATOR_EXAMPLE, encoding="utf-8")
            (workspace / "AGENTS.md").write_text(TRACKED_LOCATOR_EXAMPLE, encoding="utf-8")

            with self.subTest("no sibling templates"):
                self.assertEqual(
                    set(_read_locator_contract_sources(workspace)),
                    {"server", "workspace"},
                )

            unrelated_repo_template = parent / "repo-template" / "AGENTS.md"
            unrelated_repo_template.parent.mkdir(parents=True)
            unrelated_repo_template.write_text("unrelated", encoding="utf-8")
            with self.subTest("unrelated repo-template sibling"):
                self.assertEqual(
                    set(_read_locator_contract_sources(workspace)),
                    {"server", "workspace"},
                )

            unrelated_repo_template.parent.rename(parent / "not-repo-template")
            unrelated_skill = (
                parent
                / "work-item-template"
                / "skills"
                / "work-item"
                / "SKILL.md"
            )
            unrelated_skill.parent.mkdir(parents=True)
            unrelated_skill.write_text("unrelated", encoding="utf-8")
            with self.subTest("unrelated work-item-template sibling"):
                self.assertEqual(
                    set(_read_locator_contract_sources(workspace)),
                    {"server", "workspace"},
                )

    def test_harness_marker_keeps_source_tree_completeness_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = Path(directory)
            workspace = harness / "workspace-template"
            server = workspace / "mcp" / "qiqi_delegate" / "server.py"
            server.parent.mkdir(parents=True)
            server.write_text(TRACKED_LOCATOR_EXAMPLE, encoding="utf-8")
            (workspace / "AGENTS.md").write_text(TRACKED_LOCATOR_EXAMPLE, encoding="utf-8")
            (harness / "scripts").mkdir()
            (harness / "scripts" / "migrate-workspace.sh").write_text("", encoding="utf-8")
            (harness / "migrations").mkdir()
            (harness / "migrations" / "0024-filesystem-work-item.json").write_text(
                "{}", encoding="utf-8"
            )
            repo_agents = harness / "repo-template" / "AGENTS.md"
            repo_agents.parent.mkdir()
            repo_agents.write_text(TRACKED_LOCATOR_EXAMPLE, encoding="utf-8")

            with self.assertRaisesRegex(AssertionError, "missing locator contract source"):
                _read_locator_contract_sources(workspace)

    def test_input_models_forbid_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            TrustedFactInput(fact="x", source="y", certainty="verified")
        with self.assertRaises(ValidationError):
            ClaimToInvestigateInput(claim="x", source="y", confidence="high")
        with self.assertRaises(ValidationError):
            TaskContextInput(extra_context=[])

    def test_context_converts_to_core_shape_without_empty_sections(self) -> None:
        context = TaskContextInput(
            trusted_facts=[TrustedFactInput(fact="x", source="user decision")],
            claims_to_investigate=[
                ClaimToInvestigateInput(claim="y", source="incident note")
            ],
        )
        self.assertEqual(
            context.to_core_dict(),
            {
                "trusted_facts": [{"fact": "x", "source": "user decision"}],
                "claims_to_investigate": [
                    {"claim": "y", "source": "incident note"}
                ],
            },
        )
        self.assertEqual(TaskContextInput().to_core_dict(), {})


if __name__ == "__main__":
    unittest.main()
