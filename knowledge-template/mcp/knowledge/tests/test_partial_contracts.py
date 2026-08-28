from __future__ import annotations

import unittest
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from partial_contracts import KnowledgePatch  # noqa: E402


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

    def test_section_id_must_be_lowercase_kebab_case(self):
        for section_id in ("Bad_Id", "Bad", "bad/id", "bad id"):
            with self.subTest(section_id=section_id):
                with self.assertRaises(PydanticValidationError):
                    KnowledgePatch.model_validate(
                        {"section": {"id": section_id, "content": "body"}}
                    )


if __name__ == "__main__":
    unittest.main()
