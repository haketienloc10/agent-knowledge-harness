from __future__ import annotations

import unittest
from pathlib import Path

from pydantic import TypeAdapter, ValidationError as PydanticValidationError

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from partial_contracts import (  # noqa: E402
    ExactReadRevision,
    KnowledgePatch,
    KnowledgeSectionReadResult,
)


class KnowledgePartialContractTest(unittest.TestCase):
    def test_metadata_patch_serializes_only_supplied_fields(self):
        patch = KnowledgePatch.model_validate(
            {
                "metadata": {
                    "routing": {
                        "summary": "Updated summary only."
                    }
                }
            }
        )
        self.assertEqual(
            patch.to_patch(),
            {"metadata": {"routing": {"summary": "Updated summary only."}}},
        )

    def test_metadata_can_combine_with_one_section_atomically(self):
        patch = KnowledgePatch.model_validate(
            {
                "metadata": {"title": "Updated title"},
                "section": {"id": "verification", "content": "Updated body."},
            }
        )
        self.assertEqual(patch.to_patch()["metadata"], {"title": "Updated title"})
        self.assertEqual(patch.to_patch()["section"]["id"], "verification")

    def test_section_body_whitespace_survives_typed_input_and_output_models(self):
        body = "    indented_code()\nline with hard break  "
        patch = KnowledgePatch.model_validate(
            {"section": {"id": "verification", "content": body}}
        )
        self.assertEqual(patch.to_patch()["section"]["content"], body)

        result = KnowledgeSectionReadResult.model_validate(
            {
                "id": "domain:knowledge.partial:partial-update-rule",
                "revision": "a" * 64,
                "section_id": "verification",
                "heading": "## Verification",
                "content": body,
            }
        )
        self.assertEqual(result.content, body)

    def test_scoped_revision_schema_names_all_valid_exact_read_sources(self):
        description = TypeAdapter(ExactReadRevision).json_schema()["description"]
        for tool in (
            "knowledge_read",
            "knowledge_read_metadata",
            "knowledge_read_section",
        ):
            self.assertIn(tool, description)
        self.assertIn("knowledge_update.expected_revision", description)

    def test_content_and_section_replacement_are_mutually_exclusive(self):
        with self.assertRaises(PydanticValidationError):
            KnowledgePatch.model_validate(
                {
                    "content": "whole replacement",
                    "section": {"id": "verification", "content": "section body"},
                }
            )

    def test_explicit_null_and_empty_patch_are_rejected(self):
        for payload in (
            {},
            {"content": None},
            {"metadata": None},
            {"metadata": {}},
            {"metadata": {"routing": {}}},
            {"metadata": {"routing": {"summary": None}}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(PydanticValidationError):
                    KnowledgePatch.model_validate(payload)

    def test_identity_and_unknown_fields_are_not_patchable(self):
        for payload in (
            {"scope": {"kind": "repo", "id": "other"}},
            {"canonical_name": "renamed"},
            {"metadata": {"scope": {"kind": "repo", "id": "other"}}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(PydanticValidationError):
                    KnowledgePatch.model_validate(payload)

    def test_section_id_must_match_parser_bound_and_lowercase_kebab_case(self):
        for section_id in ("Bad_Id", "Bad", "bad/id", "bad id", "a" * 101):
            with self.subTest(section_id=section_id):
                with self.assertRaises(PydanticValidationError):
                    KnowledgePatch.model_validate(
                        {"section": {"id": section_id, "content": "body"}}
                    )


if __name__ == "__main__":
    unittest.main()
