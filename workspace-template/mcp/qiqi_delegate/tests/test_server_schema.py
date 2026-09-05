from __future__ import annotations

import asyncio
import sys
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


class PublicTaskSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tools = asyncio.run(mcp.list_tools())
        matching = [tool for tool in tools if tool.name == "delegate_repo_task"]
        if len(matching) != 1:
            raise AssertionError(f"expected one delegate_repo_task tool, got {len(matching)}")
        cls.schema = matching[0].input_schema

    def test_required_and_forbidden_top_level_fields(self) -> None:
        properties = self.schema["properties"]
        self.assertEqual(
            set(self.schema["required"]),
            {"repository", "route", "objective", "scope", "acceptance_criteria"},
        )
        self.assertTrue(FORBIDDEN_PUBLIC_FIELDS.isdisjoint(properties))

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
