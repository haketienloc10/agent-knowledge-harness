from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import WorkItemMutation


MUTATION_FIELDS = {
    "QuestionMutation": {"question", "status", "answer", "decision_id"},
    "DecisionMutation": {"summary", "status", "superseded_by"},
    "RequirementChangeMutation": {"type", "status", "summary"},
    "BlockerMutation": {"status", "summary"},
    "HandoffMutation": {"from", "to", "status", "summary"},
}


def schema_accepts_null(schema: dict[str, Any]) -> bool:
    schema_type = schema.get("type")
    if schema_type == "null":
        return True
    if isinstance(schema_type, list) and "null" in schema_type:
        return True
    if schema.get("const", object()) is None:
        return True
    if None in schema.get("enum", []):
        return True
    return any(
        schema_accepts_null(branch)
        for keyword in ("anyOf", "oneOf", "allOf")
        for branch in schema.get(keyword, [])
        if isinstance(branch, dict)
    )


class IncrementalMutationSchemaNullabilityTests(unittest.TestCase):
    def test_optional_incremental_fields_are_omittable_but_not_nullable_in_schema(self) -> None:
        definitions = WorkItemMutation.model_json_schema()["$defs"]

        for model_name, field_names in MUTATION_FIELDS.items():
            model_schema = definitions[model_name]
            properties = model_schema["properties"]
            required = set(model_schema.get("required", []))

            self.assertEqual(required, {"id"}, model_name)
            self.assertEqual(
                model_schema["additionalProperties"],
                {"not": {"type": "null"}},
                model_name,
            )
            for field_name in field_names:
                self.assertIn(field_name, properties, f"{model_name}.{field_name}")
                self.assertFalse(
                    schema_accepts_null(properties[field_name]),
                    f"{model_name}.{field_name} must not advertise explicit null",
                )
                self.assertNotIn(
                    "default",
                    properties[field_name],
                    f"{model_name}.{field_name} must not advertise a null default",
                )

    def test_runtime_still_rejects_explicit_null_and_accepts_omission(self) -> None:
        valid = WorkItemMutation.model_validate(
            {"operations": {"question_upsert": [{"id": "q1", "status": "open"}]}}
        ).to_core_mutation()
        self.assertNotIn("answer", valid["operations"]["question_upsert"][0])

        with self.assertRaisesRegex(
            PydanticValidationError,
            "answer cannot be null in an incremental semantic mutation; omit it instead",
        ):
            WorkItemMutation.model_validate(
                {"operations": {"question_upsert": [{"id": "q1", "answer": None}]}}
            )

        with self.assertRaisesRegex(
            PydanticValidationError,
            "source cannot be null in an incremental semantic mutation; omit it instead",
        ):
            WorkItemMutation.model_validate(
                {"operations": {"decision_upsert": [{"id": "d1", "source": None}]}}
            )


if __name__ == "__main__":
    unittest.main()
