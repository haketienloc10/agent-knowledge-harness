from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import MUTATION_OPERATION_MAX, WorkItemMutation, WorkItemStatePatch


class WorkItemMutationModelTests(unittest.TestCase):
    def test_state_patch_contains_only_current_effective_fields(self) -> None:
        state = WorkItemStatePatch.model_validate(
            {
                "phase": "implementation",
                "summary": "Current effective state",
                "current_requirements": ["Requirement A"],
                "repos": {"sg_mail": {"status": "done"}, "old_repo": None},
                "next_actions": [{"owner": "QiQi", "action": "Reconcile completion"}],
            }
        ).to_merge_patch()
        self.assertEqual(state["repos"]["sg_mail"], {"status": "done"})
        self.assertIsNone(state["repos"]["old_repo"])
        self.assertEqual(state["next_actions"][0]["owner"], "QiQi")

        for historical in ("questions", "decisions", "changes", "blockers", "handoffs", "checkpoints"):
            with self.assertRaises(PydanticValidationError):
                WorkItemStatePatch.model_validate({historical: []})

    def test_incremental_operation_union_is_typed_and_preserves_aliases_and_provenance(self) -> None:
        mutation = WorkItemMutation.model_validate(
            {
                "operations": [
                    {
                        "op": "question_upsert",
                        "value": {
                            "id": "q1",
                            "status": "open",
                            "question": "Which producer marks the batch?",
                            "source": "repo investigation",
                        },
                    },
                    {
                        "op": "decision_upsert",
                        "value": {
                            "id": "d1",
                            "status": "active",
                            "summary": "Keep bulk and primary mail isolated.",
                            "decided_by": "user",
                        },
                    },
                    {
                        "op": "change_upsert",
                        "value": {
                            "id": "c1",
                            "type": "requirement_added",
                            "status": "accepted",
                            "summary": "Evaluate a separate bulk-mail path.",
                            "caused_by_decision": "d1",
                        },
                    },
                    {
                        "op": "handoff_upsert",
                        "value": {
                            "id": "h1",
                            "from": "sg_mail",
                            "to": "mail-producer",
                            "status": "pending",
                            "summary": "Identify producer-side bulk signature.",
                            "evidence": ["producer is outside current repo"],
                        },
                    },
                    {
                        "op": "checkpoint_append",
                        "value": {
                            "repo": "sg_mail",
                            "kind": "investigation",
                            "summary": "Current source path verified.",
                        },
                    },
                ]
            }
        ).to_core_mutation()

        operations = mutation["operations"]
        self.assertEqual(operations[0]["value"]["source"], "repo investigation")
        self.assertEqual(operations[1]["value"]["decided_by"], "user")
        self.assertEqual(operations[2]["value"]["caused_by_decision"], "d1")
        self.assertEqual(operations[3]["value"]["from"], "sg_mail")
        self.assertNotIn("from_", operations[3]["value"])
        self.assertEqual(operations[4]["value"]["kind"], "investigation")

    def test_existing_record_transition_can_be_partial(self) -> None:
        mutation = WorkItemMutation.model_validate(
            {
                "operations": [
                    {
                        "op": "question_upsert",
                        "value": {"id": "q1", "status": "resolved", "decision_id": "d2"},
                    },
                    {
                        "op": "decision_upsert",
                        "value": {"id": "d1", "status": "superseded", "superseded_by": "d2"},
                    },
                ]
            }
        ).to_core_mutation()
        self.assertNotIn("question", mutation["operations"][0]["value"])
        self.assertNotIn("summary", mutation["operations"][1]["value"])

    def test_incremental_record_mutation_rejects_explicit_null_but_omission_is_allowed(self) -> None:
        valid = WorkItemMutation.model_validate(
            {"operations": [{"op": "question_upsert", "value": {"id": "q1", "status": "resolved"}}]}
        ).to_core_mutation()
        self.assertNotIn("answer", valid["operations"][0]["value"])

        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {"operations": [{"op": "question_upsert", "value": {"id": "q1", "answer": None}}]}
            )
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {"operations": [{"op": "decision_upsert", "value": {"id": "d1", "source": None}}]}
            )

    def test_current_state_preserves_explicit_null_merge_patch_semantics(self) -> None:
        mutation = WorkItemMutation.model_validate(
            {"state": {"repos": {"old": None}}}
        ).to_core_mutation()
        self.assertEqual(mutation, {"state": {"repos": {"old": None}}})

    def test_unknown_or_generic_semantic_operation_is_rejected(self) -> None:
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {"operations": [{"op": "upsert", "value": {"id": "q1"}}]}
            )
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {"operations": [{"op": "checkpoint_upsert", "value": {"summary": "rewrite"}}]}
            )

    def test_empty_and_oversized_mutation_are_rejected(self) -> None:
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate({})
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate({"state": {}})
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {
                    "operations": [
                        {"op": "checkpoint_append", "value": {"summary": f"checkpoint {i}"}}
                        for i in range(MUTATION_OPERATION_MAX + 1)
                    ]
                }
            )

    def test_next_actions_remain_bounded_current_array_replacement(self) -> None:
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate({"state": {"next_actions": ["do the next thing"]}})
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate({"state": {"next_actions": [{"action": "do it"}]}})

        valid = WorkItemMutation.model_validate(
            {"state": {"next_actions": [{"repo": "sg_mail", "action": "Verify behavior"}]}}
        ).to_core_mutation()
        self.assertEqual(valid["state"]["next_actions"][0]["repo"], "sg_mail")

    def test_schema_makes_full_history_replacement_unrepresentable(self) -> None:
        schema = WorkItemMutation.model_json_schema()
        state_schema = schema["$defs"]["WorkItemStatePatch"]
        state_properties = state_schema["properties"]
        for historical in ("questions", "decisions", "changes", "blockers", "handoffs", "checkpoints"):
            self.assertNotIn(historical, state_properties)
        self.assertIn("current_requirements", state_properties)
        self.assertIn("repos", state_properties)
        self.assertIn("next_actions", state_properties)
        self.assertEqual(schema["properties"]["operations"]["maxItems"], MUTATION_OPERATION_MAX)

    def test_schema_documents_checkpoint_and_repo_semantics(self) -> None:
        schema = WorkItemMutation.model_json_schema()
        definitions = schema["$defs"]
        checkpoint = definitions["CheckpointRecord"]["properties"]
        repo_summary = definitions["RepoPatch"]["properties"]["summary"]["description"].lower()
        self.assertIn("not an enum", checkpoint["kind"]["description"].lower())
        self.assertIn("omit when the phase has no artifact", checkpoint["artifact_id"]["description"].lower())
        self.assertIn("current effective repository", repo_summary)
        self.assertIn("narrative", repo_summary)
        self.assertIn("historical phase", repo_summary)


if __name__ == "__main__":
    unittest.main()
