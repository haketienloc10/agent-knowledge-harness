from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import ConflictError, ValidationError, create_work_item, load_work_item_document, new_document
from mutations import MUTATION_OPERATION_MAX, mutate_work_item


class IncrementalMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "work-items.sqlite3"
        self.item = create_work_item(
            self.db,
            new_document(
                item_id="redmine:32",
                title="Incremental mutations",
                summary="Initial state",
                repositories=["api", "web"],
            ),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _mutate(self, mutation: dict, revision: int | None = None) -> dict:
        return mutate_work_item(
            self.db,
            self.item["id"],
            revision if revision is not None else self.item["revision"],
            mutation,
        )

    def test_mixed_state_and_semantic_operations_commit_once_with_compact_receipt(self) -> None:
        receipt = self._mutate(
            {
                "state": {
                    "phase": "implementation",
                    "current_requirements": ["Expose paymentStatus on list and detail"],
                    "repos": {
                        "api": {
                            "status": "done",
                            "summary": "paymentStatus is implemented",
                            "verification": ["unit tests passed"],
                        }
                    },
                    "next_actions": [{"repo": "web", "action": "Consume paymentStatus"}],
                },
                "operations": [
                    {
                        "op": "decision_upsert",
                        "value": {
                            "id": "d1",
                            "status": "active",
                            "summary": "Unknown paymentStatus is represented as null",
                            "decided_by": "customer",
                        },
                    },
                    {
                        "op": "question_upsert",
                        "value": {
                            "id": "q1",
                            "status": "resolved",
                            "question": "How is an unknown value represented?",
                            "decision_id": "d1",
                            "source": "customer Q&A",
                        },
                    },
                    {
                        "op": "change_upsert",
                        "value": {
                            "id": "c1",
                            "type": "requirement_added",
                            "status": "accepted",
                            "summary": "Expose paymentStatus on list API",
                        },
                    },
                    {
                        "op": "handoff_upsert",
                        "value": {
                            "id": "h1",
                            "from": "api",
                            "to": "web",
                            "status": "pending",
                            "summary": "Consume paymentStatus",
                        },
                    },
                    {
                        "op": "checkpoint_append",
                        "value": {
                            "repo": "api",
                            "kind": "verification",
                            "summary": "API implementation verified",
                        },
                    },
                ],
            }
        )

        self.assertEqual(
            receipt,
            {
                "updated": True,
                "id": "redmine:32",
                "revision": 2,
                "changed": [
                    "phase",
                    "current_requirements",
                    "repos.api",
                    "next_actions",
                    "decisions:d1",
                    "questions:q1",
                    "changes:c1",
                    "handoffs:h1",
                    "checkpoints",
                ],
            },
        )
        self.assertNotIn("questions", receipt)
        self.assertNotIn("checkpoints", receipt)

        stored = load_work_item_document(self.db, self.item["id"])
        self.assertEqual(stored["revision"], 2)
        self.assertEqual(stored["questions"][0]["decision_id"], "d1")
        self.assertEqual(stored["decisions"][0]["status"], "active")
        self.assertEqual(stored["repos"]["api"]["status"], "done")

    def test_append_one_checkpoint_does_not_require_or_return_existing_history(self) -> None:
        operations = [
            {
                "op": "checkpoint_append",
                "value": {"repo": "api", "summary": f"Checkpoint {index}"},
            }
            for index in range(MUTATION_OPERATION_MAX)
        ]
        revision = self.item["revision"]
        for batch_start in range(0, 200, MUTATION_OPERATION_MAX):
            receipt = mutate_work_item(
                self.db,
                self.item["id"],
                revision,
                {"operations": operations},
            )
            revision = receipt["revision"]

        before = load_work_item_document(self.db, self.item["id"])
        self.assertEqual(len(before["checkpoints"]), 200)
        request = {
            "operations": [
                {
                    "op": "checkpoint_append",
                    "value": {"repo": "api", "summary": "Checkpoint 200"},
                }
            ]
        }
        receipt = mutate_work_item(self.db, self.item["id"], revision, request)
        self.assertEqual(receipt["changed"], ["checkpoints"])
        self.assertLess(len(json.dumps(request)), 250)
        self.assertLess(len(json.dumps(receipt)), 200)
        after = load_work_item_document(self.db, self.item["id"])
        self.assertEqual(len(after["checkpoints"]), 201)
        self.assertEqual(after["checkpoints"][-1]["summary"], "Checkpoint 200")

    def test_question_resolution_is_partial_monotonic_and_write_once(self) -> None:
        created = self._mutate(
            {
                "operations": [
                    {
                        "op": "question_upsert",
                        "value": {
                            "id": "q1",
                            "question": "Which behavior is required?",
                            "status": "open",
                        },
                    }
                ]
            }
        )
        resolved = mutate_work_item(
            self.db,
            self.item["id"],
            created["revision"],
            {
                "operations": [
                    {
                        "op": "question_upsert",
                        "value": {"id": "q1", "status": "resolved", "answer": "Behavior A"},
                    }
                ]
            },
        )
        question = load_work_item_document(self.db, self.item["id"])["questions"][0]
        self.assertEqual(question["question"], "Which behavior is required?")
        self.assertEqual(question["answer"], "Behavior A")

        with self.assertRaisesRegex(ValidationError, "cannot transition"):
            mutate_work_item(
                self.db,
                self.item["id"],
                resolved["revision"],
                {"operations": [{"op": "question_upsert", "value": {"id": "q1", "status": "open"}}]},
            )
        with self.assertRaisesRegex(ValidationError, "write-once"):
            mutate_work_item(
                self.db,
                self.item["id"],
                resolved["revision"],
                {
                    "operations": [
                        {"op": "question_upsert", "value": {"id": "q1", "answer": "Behavior B"}}
                    ]
                },
            )
        self.assertEqual(load_work_item_document(self.db, self.item["id"])["revision"], resolved["revision"])

    def test_existing_semantic_identity_and_provenance_cannot_be_rewritten(self) -> None:
        created = self._mutate(
            {
                "operations": [
                    {
                        "op": "decision_upsert",
                        "value": {
                            "id": "d1",
                            "status": "active",
                            "summary": "Original decision",
                            "source": "customer",
                        },
                    }
                ]
            }
        )
        with self.assertRaisesRegex(ValidationError, "immutable"):
            mutate_work_item(
                self.db,
                self.item["id"],
                created["revision"],
                {
                    "operations": [
                        {"op": "decision_upsert", "value": {"id": "d1", "summary": "Rewritten"}}
                    ]
                },
            )
        with self.assertRaisesRegex(ValidationError, "provenance"):
            mutate_work_item(
                self.db,
                self.item["id"],
                created["revision"],
                {
                    "operations": [
                        {"op": "decision_upsert", "value": {"id": "d1", "source": "different"}}
                    ]
                },
            )

    def test_cross_record_references_validate_after_entire_operation_batch(self) -> None:
        first = self._mutate(
            {
                "operations": [
                    {
                        "op": "decision_upsert",
                        "value": {"id": "d1", "status": "active", "summary": "Old decision"},
                    }
                ]
            }
        )
        receipt = mutate_work_item(
            self.db,
            self.item["id"],
            first["revision"],
            {
                "operations": [
                    {
                        "op": "decision_upsert",
                        "value": {"id": "d1", "status": "superseded", "superseded_by": "d2"},
                    },
                    {
                        "op": "decision_upsert",
                        "value": {"id": "d2", "status": "active", "summary": "New decision"},
                    },
                    {
                        "op": "question_upsert",
                        "value": {
                            "id": "q1",
                            "question": "Which decision applies?",
                            "status": "resolved",
                            "decision_id": "d2",
                        },
                    },
                ]
            },
        )
        stored = load_work_item_document(self.db, self.item["id"])
        self.assertEqual(receipt["revision"], 3)
        self.assertEqual(stored["decisions"][0]["superseded_by"], "d2")

        with self.assertRaisesRegex(ValidationError, "missing decision_id"):
            mutate_work_item(
                self.db,
                self.item["id"],
                receipt["revision"],
                {
                    "state": {"summary": "must roll back"},
                    "operations": [
                        {
                            "op": "question_upsert",
                            "value": {
                                "id": "q2",
                                "question": "Missing decision?",
                                "status": "resolved",
                                "decision_id": "d404",
                            },
                        }
                    ],
                },
            )
        stored_after = load_work_item_document(self.db, self.item["id"])
        self.assertEqual(stored_after["revision"], receipt["revision"])
        self.assertNotEqual(stored_after["summary"], "must roll back")
        self.assertEqual([q["id"] for q in stored_after["questions"]], ["q1"])

    def test_blocker_handoff_and_change_lifecycles_do_not_reopen(self) -> None:
        first = self._mutate(
            {
                "operations": [
                    {"op": "blocker_upsert", "value": {"id": "b1", "status": "open", "summary": "Blocked"}},
                    {
                        "op": "handoff_upsert",
                        "value": {"id": "h1", "from": "api", "to": "web", "status": "pending", "summary": "Handoff"},
                    },
                    {
                        "op": "change_upsert",
                        "value": {"id": "c1", "type": "scope_changed", "status": "proposed", "summary": "Change"},
                    },
                ]
            }
        )
        second = mutate_work_item(
            self.db,
            self.item["id"],
            first["revision"],
            {
                "operations": [
                    {"op": "blocker_upsert", "value": {"id": "b1", "status": "resolved"}},
                    {"op": "handoff_upsert", "value": {"id": "h1", "status": "resolved"}},
                    {"op": "change_upsert", "value": {"id": "c1", "status": "accepted"}},
                ]
            },
        )
        for op, value in (
            ("blocker_upsert", {"id": "b1", "status": "open"}),
            ("handoff_upsert", {"id": "h1", "status": "pending"}),
            ("change_upsert", {"id": "c1", "status": "proposed"}),
        ):
            with self.assertRaisesRegex(ValidationError, "cannot transition"):
                mutate_work_item(
                    self.db,
                    self.item["id"],
                    second["revision"],
                    {"operations": [{"op": op, "value": value}]},
                )

    def test_duplicate_target_and_operation_overflow_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate target"):
            self._mutate(
                {
                    "operations": [
                        {"op": "blocker_upsert", "value": {"id": "b1", "status": "open", "summary": "A"}},
                        {"op": "blocker_upsert", "value": {"id": "b1", "status": "resolved"}},
                    ]
                }
            )
        self.assertEqual(load_work_item_document(self.db, self.item["id"])["revision"], 1)

        with self.assertRaisesRegex(ValidationError, "at most 50"):
            self._mutate(
                {
                    "operations": [
                        {"op": "checkpoint_append", "value": {"summary": f"Checkpoint {i}"}}
                        for i in range(MUTATION_OPERATION_MAX + 1)
                    ]
                }
            )

    def test_checkpoint_history_has_append_only_public_operation(self) -> None:
        with self.assertRaisesRegex(ValidationError, "unsupported semantic operation"):
            self._mutate(
                {
                    "operations": [
                        {"op": "checkpoint_upsert", "value": {"id": "cp1", "summary": "rewrite"}}
                    ]
                }
            )
        with self.assertRaisesRegex(ValidationError, "does not use stable checkpoint ids"):
            self._mutate(
                {
                    "operations": [
                        {"op": "checkpoint_append", "value": {"id": "cp1", "summary": "append"}}
                    ]
                }
            )

    def test_stale_writer_conflicts_even_when_touching_different_semantics(self) -> None:
        first = self._mutate(
            {
                "operations": [
                    {"op": "checkpoint_append", "value": {"summary": "Writer A checkpoint"}}
                ]
            }
        )
        self.assertEqual(first["revision"], 2)
        with self.assertRaises(ConflictError):
            mutate_work_item(
                self.db,
                self.item["id"],
                1,
                {
                    "operations": [
                        {"op": "blocker_upsert", "value": {"id": "b1", "status": "open", "summary": "Writer B blocker"}}
                    ]
                },
            )

    def test_two_concurrent_writers_from_same_revision_cannot_both_commit(self) -> None:
        outcomes: list[str] = []
        barrier = threading.Barrier(2)

        def writer(index: int) -> None:
            barrier.wait()
            try:
                mutate_work_item(
                    self.db,
                    self.item["id"],
                    self.item["revision"],
                    {
                        "operations": [
                            {"op": "checkpoint_append", "value": {"summary": f"writer-{index}"}}
                        ]
                    },
                )
                outcomes.append("ok")
            except ConflictError:
                outcomes.append("conflict")

        threads = [threading.Thread(target=writer, args=(1,)), threading.Thread(target=writer, args=(2,))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertCountEqual(outcomes, ["ok", "conflict"])
        stored = load_work_item_document(self.db, self.item["id"])
        self.assertEqual(stored["revision"], 2)
        self.assertEqual(len(stored["checkpoints"]), 1)


if __name__ == "__main__":
    unittest.main()
