from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import WorkItemPatch


class WorkItemPatchModelTests(unittest.TestCase):
    def test_valid_mixed_patch_preserves_canonical_shape_and_provenance(self) -> None:
        patch = WorkItemPatch.model_validate(
            {
                "phase": "design-investigation",
                "questions": [
                    {
                        "id": "q1",
                        "status": "open",
                        "question": "Which producer marks the bulk-mail batch?",
                        "source": "repo investigation",
                    }
                ],
                "decisions": [
                    {
                        "id": "d1",
                        "status": "active",
                        "summary": "Keep bulk and primary mail isolated.",
                        "decided_by": "user",
                    }
                ],
                "changes": [
                    {
                        "id": "c1",
                        "type": "requirement_added",
                        "status": "accepted",
                        "summary": "Evaluate a separate bulk-mail path.",
                        "caused_by_decision": "d1",
                    }
                ],
                "repos": {"sg_mail": {"status": "pending"}},
                "blockers": [
                    {"id": "b1", "status": "open", "summary": "Bulk classifier is unknown."}
                ],
                "handoffs": [
                    {
                        "id": "h1",
                        "from": "sg_mail",
                        "to": "mail-producer",
                        "status": "pending",
                        "summary": "Identify producer-side bulk signature.",
                        "evidence": ["producer is outside current repo"],
                    }
                ],
                "next_actions": [
                    {"repo": "sg_mail", "action": "Confirm the classification boundary."}
                ],
                "checkpoints": [
                    {
                        "repo": "sg_mail",
                        "summary": "Current source path verified.",
                        "kind": "investigation",
                    }
                ],
            }
        ).to_merge_patch()

        self.assertEqual(patch["handoffs"][0]["from"], "sg_mail")
        self.assertNotIn("from_", patch["handoffs"][0])
        self.assertEqual(patch["questions"][0]["source"], "repo investigation")
        self.assertEqual(patch["decisions"][0]["decided_by"], "user")
        self.assertEqual(patch["changes"][0]["caused_by_decision"], "d1")
        self.assertEqual(patch["checkpoints"][0]["kind"], "investigation")
        self.assertEqual(patch["repos"]["sg_mail"], {"status": "pending"})

    def test_checkpoint_phase_metadata_is_optional_and_free_form(self) -> None:
        patch = WorkItemPatch.model_validate(
            {
                "checkpoints": [
                    {
                        "repo": "sg_mail",
                        "kind": "implementation-rework",
                        "artifact_id": "review:2",
                        "summary": "Review finding was fixed and reverified.",
                    },
                    {
                        "repo": "sg_mail",
                        "summary": "Implementation completed without an artifact.",
                    },
                ]
            }
        ).to_merge_patch()

        self.assertEqual(patch["checkpoints"][0]["kind"], "implementation-rework")
        self.assertEqual(patch["checkpoints"][0]["artifact_id"], "review:2")
        self.assertNotIn("kind", patch["checkpoints"][1])
        self.assertNotIn("artifact_id", patch["checkpoints"][1])

    def test_questions_must_be_canonical_objects_not_strings_or_text_records(self) -> None:
        with self.assertRaises(PydanticValidationError):
            WorkItemPatch.model_validate({"questions": ["[open] unresolved question"]})

        with self.assertRaises(PydanticValidationError):
            WorkItemPatch.model_validate(
                {"questions": [{"text": "wrong field", "status": "open"}]}
            )

        valid = WorkItemPatch.model_validate(
            {"questions": [{"id": "q1", "status": "open", "question": "Canonical question"}]}
        )
        self.assertEqual(valid.to_merge_patch()["questions"][0]["question"], "Canonical question")

    def test_blockers_must_be_objects(self) -> None:
        with self.assertRaises(PydanticValidationError):
            WorkItemPatch.model_validate({"blockers": ["test blocker string"]})

        valid = WorkItemPatch.model_validate(
            {"blockers": [{"id": "b1", "status": "open", "summary": "SMTP capacity unknown"}]}
        )
        self.assertEqual(valid.to_merge_patch()["blockers"][0]["id"], "b1")

    def test_requirement_change_enums_are_explicit(self) -> None:
        with self.assertRaises(PydanticValidationError):
            WorkItemPatch.model_validate(
                {
                    "changes": [
                        {
                            "id": "c1",
                            "type": "requirement",
                            "status": "accepted",
                            "summary": "wrong type",
                        }
                    ]
                }
            )
        with self.assertRaises(PydanticValidationError):
            WorkItemPatch.model_validate(
                {
                    "changes": [
                        {
                            "id": "c1",
                            "type": "requirement_added",
                            "status": "active",
                            "summary": "wrong status",
                        }
                    ]
                }
            )

    def test_next_actions_require_object_shape_and_target(self) -> None:
        with self.assertRaises(PydanticValidationError):
            WorkItemPatch.model_validate({"next_actions": ["do the next thing"]})
        with self.assertRaises(PydanticValidationError):
            WorkItemPatch.model_validate({"next_actions": [{"action": "do the next thing"}]})

        valid = WorkItemPatch.model_validate(
            {"next_actions": [{"owner": "QiQi", "action": "Reconcile the task"}]}
        )
        self.assertEqual(valid.to_merge_patch()["next_actions"][0]["owner"], "QiQi")

    def test_repo_partial_merge_and_null_deletion_are_preserved(self) -> None:
        patch = WorkItemPatch.model_validate(
            {"repos": {"sg_mail": {"status": "done"}, "old_repo": None}}
        ).to_merge_patch()
        self.assertEqual(patch["repos"]["sg_mail"], {"status": "done"})
        self.assertIsNone(patch["repos"]["old_repo"])

    def test_omitted_fields_are_not_emitted_but_explicit_null_is_preserved(self) -> None:
        self.assertEqual(WorkItemPatch.model_validate({}).to_merge_patch(), {})
        self.assertEqual(
            WorkItemPatch.model_validate({"summary": None}).to_merge_patch(),
            {"summary": None},
        )

    def test_unknown_top_level_patch_field_is_rejected(self) -> None:
        with self.assertRaises(PydanticValidationError):
            WorkItemPatch.model_validate({"question": "typo singular field"})
        with self.assertRaises(PydanticValidationError):
            WorkItemPatch.model_validate({"artifacts": []})

    def test_schema_describes_semantic_meanings_and_array_replacement(self) -> None:
        schema = WorkItemPatch.model_json_schema()
        properties = schema["properties"]
        definitions = schema["$defs"]
        self.assertIn("not free-form notes", properties["questions"]["description"].lower())
        self.assertIn("requirement/scope", properties["changes"]["description"].lower())
        self.assertIn("not generic risks", properties["blockers"]["description"].lower())
        self.assertIn("do not send plain strings", properties["next_actions"]["description"].lower())
        self.assertIn("accumulated material", properties["checkpoints"]["description"].lower())
        self.assertIn("current effective repo truth", properties["repos"]["description"].lower())
        self.assertIn("not a narrative", definitions["RepoPatch"]["properties"]["summary"]["description"].lower())
        self.assertIn("not an enum", definitions["CheckpointPatch"]["properties"]["kind"]["description"].lower())
        self.assertIn("omit when the phase has no artifact", definitions["CheckpointPatch"]["properties"]["artifact_id"]["description"].lower())
        self.assertIn("arrays replace atomically", properties["current_requirements"]["description"].lower())


if __name__ == "__main__":
    unittest.main()
