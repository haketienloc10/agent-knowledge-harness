from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts import (  # noqa: E402
    KnowledgeReadContext,
    KnowledgeWriteEntry,
    KnowledgeWriteResult,
)


def create_payload() -> dict:
    return {
        "canonical_name": "smoke-retry-rule",
        "title": "Smoke retry rule",
        "scope": {"kind": "domain", "id": "smoke.payment"},
        "routing": {
            "summary": "Smoke payments must not retry after confirmed commit.",
            "when_to_read": [
                "testing knowledge retrieval",
                "testing payment retry rules",
            ],
            "keywords": ["smoke", "payment", "retry", "commit"],
            "aliases": ["test retry thanh toán"],
        },
        "content": "Đây là dữ liệu smoke test.",
        "sources": [{"kind": "manual", "locator": "knowledge MCP smoke test"}],
    }


class KnowledgeContractsTest(unittest.TestCase):
    def test_write_schema_exposes_nested_routing(self):
        schema = KnowledgeWriteEntry.model_json_schema()
        properties = schema["properties"]
        self.assertIn("routing", properties)
        for misplaced in ("summary", "when_to_read", "keywords", "aliases"):
            self.assertNotIn(misplaced, properties)
        self.assertFalse(schema.get("additionalProperties", True))

    def test_flat_routing_fields_fail_with_actionable_hint(self):
        payload = create_payload()
        payload["summary"] = payload["routing"].pop("summary")
        payload["when_to_read"] = payload["routing"].pop("when_to_read")
        payload["keywords"] = payload["routing"].pop("keywords")
        payload["aliases"] = payload["routing"].pop("aliases")
        with self.assertRaises(ValidationError) as raised:
            KnowledgeWriteEntry.model_validate(payload)
        self.assertIn(
            "must be nested under the 'routing' object",
            str(raised.exception),
        )

    def test_filesystem_fields_fail_with_actionable_hint(self):
        payload = create_payload()
        payload["path"] = "domains/smoke/payment/smoke-retry-rule.md"
        with self.assertRaises(ValidationError) as raised:
            KnowledgeWriteEntry.model_validate(payload)
        self.assertIn(
            "filesystem fields are owned by Knowledge MCP",
            str(raised.exception),
        )

    def test_language_field_is_rejected_with_guidance(self):
        payload = create_payload()
        payload["language"] = "vi"
        with self.assertRaises(ValidationError) as raised:
            KnowledgeWriteEntry.model_validate(payload)
        self.assertIn("language is not part of the knowledge schema", str(raised.exception))

    def test_scope_id_underscore_fails_with_actionable_hint(self):
        payload = create_payload()
        payload["scope"]["id"] = "search_air"
        with self.assertRaises(ValidationError) as raised:
            KnowledgeWriteEntry.model_validate(payload)
        self.assertIn("not '_'", str(raised.exception))
        self.assertIn("'search-air'", str(raised.exception))

    def test_summary_over_budget_fails_with_actionable_hint(self):
        payload = create_payload()
        payload["routing"]["summary"] = "x" * 501
        with self.assertRaises(ValidationError) as raised:
            KnowledgeWriteEntry.model_validate(payload)
        self.assertIn("exceeds 500 characters", str(raised.exception))
        self.assertIn("Summary budget gate", str(raised.exception))

    def test_create_omits_id_and_revision(self):
        entry = KnowledgeWriteEntry.model_validate(create_payload())
        self.assertIsNone(entry.id)
        self.assertIsNone(entry.expected_revision)

    def test_update_requires_revision(self):
        payload = create_payload()
        payload["id"] = "domain:smoke.payment:smoke-retry-rule"
        with self.assertRaises(ValidationError) as raised:
            KnowledgeWriteEntry.model_validate(payload)
        self.assertIn("update entries require expected_revision", str(raised.exception))

    def test_revision_must_be_sha256(self):
        payload = create_payload()
        payload["id"] = "domain:smoke.payment:smoke-retry-rule"
        payload["expected_revision"] = "abc123"
        with self.assertRaises(ValidationError):
            KnowledgeWriteEntry.model_validate(payload)

    def test_scope_and_source_kind_are_closed_enums(self):
        payload = create_payload()
        payload["scope"]["kind"] = "folder"
        with self.assertRaises(ValidationError):
            KnowledgeWriteEntry.model_validate(payload)

        payload = create_payload()
        payload["sources"][0]["kind"] = "filesystem"
        with self.assertRaises(ValidationError):
            KnowledgeWriteEntry.model_validate(payload)

    def test_read_context_rejects_unknown_fields(self):
        with self.assertRaises(ValidationError):
            KnowledgeReadContext.model_validate({"repo": "checkout", "path": "/tmp"})

    def test_write_result_is_typed(self):
        result = KnowledgeWriteResult.model_validate(
            {
                "reviewed": True,
                "changes": [
                    {
                        "operation": "created",
                        "id": "domain:smoke.payment:smoke-retry-rule",
                        "path": "domains/smoke/payment/smoke-retry-rule.md",
                        "revision": "a" * 64,
                    }
                ],
            }
        )
        self.assertEqual(result.changes[0].operation, "created")
        self.assertEqual(result.changes[0].revision, "a" * 64)


if __name__ == "__main__":
    unittest.main()
