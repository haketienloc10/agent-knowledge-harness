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

    def test_grouped_operations_are_typed_and_preserve_aliases_and_provenance(self) -> None:
        mutation = WorkItemMutation.model_validate(
            {
                "operations": {
                    "question_upsert": [
                        {
                            "id": "q1",
                            "status": "open",
                            "question": "Which producer marks the batch?",
                            "source": "repo investigation",
                        }
                    ],
                    "decision_upsert": [
                        {
                            "id": "d1",
                            "status": "active",
                            "summary": "Keep bulk and primary mail isolated.",
                            "decided_by": "user",
                        }
                    ],
                    "change_upsert": [
                        {
                            "id": "c1",
                            "type": "requirement_added",
                            "status": "accepted",
                            "summary": "Evaluate a separate bulk-mail path.",
                            "caused_by_decision": "d1",
                        }
                    ],
                    "handoff_upsert": [
                        {
                            "id": "h1",
                            "from": "sg_mail",
                            "to": "mail-producer",
                            "status": "pending",
                            "summary": "Identify producer-side bulk signature.",
                            "evidence": ["producer is outside current repo"],
                        }
                    ],
                    "checkpoint_append": [
                        {
                            "repo": "sg_mail",
                            "kind": "investigation",
                            "summary": "Current source path verified.",
                        }
                    ],
                }
            }
        ).to_core_mutation()

        operations = mutation["operations"]
        self.assertEqual(operations["question_upsert"][0]["source"], "repo investigation")
        self.assertEqual(operations["decision_upsert"][0]["decided_by"], "user")
        self.assertEqual(operations["change_upsert"][0]["caused_by_decision"], "d1")
        self.assertEqual(operations["handoff_upsert"][0]["from"], "sg_mail")
        self.assertNotIn("from_", operations["handoff_upsert"][0])
        self.assertEqual(operations["checkpoint_append"][0]["kind"], "investigation")

    def test_existing_record_transition_can_be_partial(self) -> None:
        mutation = WorkItemMutation.model_validate(
            {
                "operations": {
                    "question_upsert": [
                        {"id": "q1", "status": "resolved", "decision_id": "d2"}
                    ],
                    "decision_upsert": [
                        {"id": "d1", "status": "superseded", "superseded_by": "d2"}
                    ],
                }
            }
        ).to_core_mutation()
        self.assertNotIn("question", mutation["operations"]["question_upsert"][0])
        self.assertNotIn("summary", mutation["operations"]["decision_upsert"][0])

    def test_incremental_record_mutation_rejects_explicit_null_but_omission_is_allowed(self) -> None:
        valid = WorkItemMutation.model_validate(
            {"operations": {"question_upsert": [{"id": "q1", "status": "resolved"}]}}
        ).to_core_mutation()
        self.assertNotIn("answer", valid["operations"]["question_upsert"][0])

        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {"operations": {"question_upsert": [{"id": "q1", "answer": None}]}}
            )
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {"operations": {"decision_upsert": [{"id": "d1", "source": None}]}}
            )

    def test_current_state_preserves_explicit_null_merge_patch_semantics(self) -> None:
        mutation = WorkItemMutation.model_validate(
            {"state": {"repos": {"old": None}}}
        ).to_core_mutation()
        self.assertEqual(mutation, {"state": {"repos": {"old": None}}})

    def test_group_names_are_the_operation_contract_and_old_op_value_shape_is_rejected(self) -> None:
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {"operations": {"upsert": [{"id": "q1"}]}}
            )
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {"operations": {"checkpoint_upsert": [{"summary": "rewrite"}]}}
            )
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {"operations": [{"op": "checkpoint_append", "value": {"summary": "legacy"}}]}
            )

    def test_empty_and_total_operation_overflow_are_rejected(self) -> None:
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate({})
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate({"state": {}})
        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate({"operations": {}})

        with self.assertRaises(PydanticValidationError):
            WorkItemMutation.model_validate(
                {
                    "operations": {
                        "checkpoint_append": [
                            {"summary": f"checkpoint {i}"}
                            for i in range(30)
                        ],
                        "blocker_upsert": [
                            {"id": f"b{i}", "status": "open", "summary": f"blocker {i}"}
                            for i in range(MUTATION_OPERATION_MAX - 29)
                        ],
                    }
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

    def test_schema_makes_history_replacement_unrepresentable_and_groups_visible_directly(self) -> None:
        schema = WorkItemMutation.model_json_schema()
        definitions = schema["$defs"]
        state_properties = definitions["WorkItemStatePatch"]["properties"]
        for historical in ("questions", "decisions", "changes", "blockers", "handoffs", "checkpoints"):
            self.assertNotIn(historical, state_properties)
        self.assertIn("current_requirements", state_properties)
        self.assertIn("repos", state_properties)
        self.assertIn("next_actions", state_properties)

        operation_properties = definitions["WorkItemOperations"]["properties"]
        self.assertEqual(
            set(operation_properties),
            {
                "decision_upsert",
                "question_upsert",
                "change_upsert",
                "blocker_upsert",
                "handoff_upsert",
                "checkpoint_append",
            },
        )
        for operation in operation_properties.values():
            self.assertEqual(operation["maxItems"], MUTATION_OPERATION_MAX)
        self.assertNotIn("WorkItemOperation", definitions)
        self.assertNotIn("CheckpointAppendOperation", definitions)

    def test_schema_documents_checkpoint_and_repo_semantics(self) -> None:
        schema = WorkItemMutation.model_json_schema()
        definitions = schema["$defs"]
        checkpoint = definitions["CheckpointRecord"]["properties"]
        repo_summary = definitions["RepoPatch"]["properties"]["summary"]["description"].lower()
        operations_description = schema["properties"]["operations"]["description"].lower()
        self.assertIn("not an enum", checkpoint["kind"]["description"].lower())
        self.assertIn("omit when the phase has no artifact", checkpoint["artifact_id"]["description"].lower())
        self.assertIn("current effective repository", repo_summary)
        self.assertIn("narrative", repo_summary)
        self.assertIn("historical phase", repo_summary)
        self.assertIn("there is no op/value envelope", operations_description)
        self.assertIn("cross-group order is not part of the public contract", operations_description)


if __name__ == "__main__":
    unittest.main()
