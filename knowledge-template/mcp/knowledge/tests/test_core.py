from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (  # noqa: E402
    ConflictError,
    KnowledgeError,
    ValidationError,
    check_store,
    read_knowledge,
    reindex_store,
    render_index,
    scan_documents,
    search_knowledge,
    write_knowledge,
)


def create_entry(*, name: str = "retry-after-commit", title: str = "Retry after commit"):
    return {
        "canonical_name": name,
        "title": title,
        "scope": {"kind": "domain", "id": "checkout.payment"},
        "routing": {
            "summary": "Payment must not be retried after a successful transaction commit.",
            "when_to_read": [
                "modifying payment retry behavior",
                "investigating duplicate payment",
            ],
            "keywords": ["payment", "retry", "idempotency", "transaction commit"],
            "aliases": ["retry thanh toán", "không retry sau commit"],
        },
        "content": "Sau khi transaction commit thành công, không retry payment.",
        "sources": [
            {
                "kind": "repo",
                "locator": "checkout:src/payment/retry.ts",
                "ref": "abc123",
            }
        ],
    }


class KnowledgeCoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ("global", "systems", "repos", "domains"):
            (self.root / name).mkdir()
        (self.root / "INDEX.md").write_text(render_index({}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_create_materializes_canonical_path_and_index(self):
        result = write_knowledge(self.root, [create_entry()])
        change = result["changes"][0]
        self.assertEqual(change["operation"], "created")
        self.assertEqual(change["id"], "domain:checkout.payment:retry-after-commit")
        expected = self.root / "domains/checkout/payment/retry-after-commit.md"
        self.assertTrue(expected.is_file())
        checked = check_store(self.root)
        self.assertTrue(checked["ok"], checked["errors"])

    def test_search_matches_english_and_vietnamese_aliases_without_hydrating_content(self):
        write_knowledge(self.root, [create_entry()])
        english = search_knowledge(
            self.root, ["payment retry", "idempotency", "transaction commit"]
        )
        self.assertEqual(len(english["results"]), 1)
        vietnamese = search_knowledge(self.root, ["retry thanh toán", "sau commit"])
        self.assertEqual(len(vietnamese["results"]), 1)
        hit = vietnamese["results"][0]
        self.assertEqual(hit["id"], "domain:checkout.payment:retry-after-commit")
        self.assertLessEqual(len(hit["when_to_read"]), 3)
        self.assertLessEqual(len(hit["matches"]), 3)
        for forbidden in ("content", "sources", "revision", "path", "canonical_name"):
            self.assertNotIn(forbidden, hit)

    def test_read_hydrates_exact_id_with_round_trip_semantic_payload(self):
        created = write_knowledge(self.root, [create_entry()])["changes"][0]
        result = read_knowledge(self.root, [created["id"]])
        self.assertEqual(len(result["results"]), 1)
        item = result["results"][0]
        self.assertEqual(item["revision"], created["revision"])
        self.assertEqual(item["canonical_name"], "retry-after-commit")
        self.assertEqual(item["routing"], create_entry()["routing"])
        self.assertEqual(item["sources"], create_entry()["sources"])
        self.assertEqual(item["content"], create_entry()["content"])
        self.assertFalse(item["content"].startswith("# Retry after commit"))
        self.assertNotIn("path", item)

    def test_read_limits_exact_hydration_to_two_unique_ids(self):
        entries = [
            create_entry(name="first-rule", title="First rule"),
            create_entry(name="second-rule", title="Second rule"),
            create_entry(name="third-rule", title="Third rule"),
        ]
        changes = write_knowledge(self.root, entries)["changes"]
        with self.assertRaises(ValidationError):
            read_knowledge(self.root, [change["id"] for change in changes])
        with self.assertRaises(ValidationError):
            read_knowledge(self.root, [changes[0]["id"], changes[0]["id"]])

    def test_missing_exact_read_target_fails_clearly(self):
        with self.assertRaises(KnowledgeError) as raised:
            read_knowledge(self.root, ["domain:checkout.payment:not-there"])
        self.assertIn("knowledge id does not exist", str(raised.exception))

    def test_repo_context_is_only_a_ranking_hint(self):
        write_knowledge(self.root, [create_entry()])
        result = search_knowledge(
            self.root,
            ["payment retry"],
            context={"repo": "another-repo"},
        )
        self.assertEqual(len(result["results"]), 1)

    def test_context_does_not_create_relevance_without_semantic_match(self):
        write_knowledge(self.root, [create_entry()])
        result = search_knowledge(
            self.root,
            ["unrelated mail delivery"],
            context={"domain": "checkout.payment"},
        )
        self.assertEqual(result["results"], [])

    def test_title_scope_and_path_do_not_create_relevance_by_themselves(self):
        entry = create_entry(name="generic-rule", title="Rare needle title")
        entry["scope"] = {"kind": "repo", "id": "rare-needle"}
        write_knowledge(self.root, [entry])
        result = search_knowledge(self.root, ["rare needle"])
        self.assertEqual(result["results"], [])

    def test_repo_context_boosts_existing_semantic_match(self):
        checkout = create_entry(name="checkout-retry", title="Checkout retry")
        checkout["scope"] = {"kind": "repo", "id": "checkout"}
        checkout["sources"][0]["locator"] = "checkout:src/payment/retry.ts"

        ledger = create_entry(name="ledger-retry", title="Ledger retry")
        ledger["scope"] = {"kind": "repo", "id": "ledger"}
        ledger["sources"][0]["locator"] = "ledger:src/payment/retry.ts"

        write_knowledge(self.root, [checkout, ledger])
        result = search_knowledge(
            self.root,
            ["payment retry"],
            context={"repo": "checkout"},
        )

        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["id"], "repo:checkout:checkout-retry")
        self.assertGreater(result["results"][0]["score"], result["results"][1]["score"])

    def test_domain_context_boosts_existing_semantic_match(self):
        payment = create_entry(name="payment-retry", title="Payment retry")
        payment["scope"] = {"kind": "domain", "id": "checkout.payment"}

        booking = create_entry(name="booking-retry", title="Booking retry")
        booking["scope"] = {"kind": "domain", "id": "checkout.booking"}
        booking["sources"][0]["locator"] = "checkout:src/booking/retry.ts"

        write_knowledge(self.root, [payment, booking])
        result = search_knowledge(
            self.root,
            ["payment retry"],
            context={"domain": "checkout.payment"},
        )

        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(
            result["results"][0]["id"],
            "domain:checkout.payment:payment-retry",
        )
        self.assertGreater(result["results"][0]["score"], result["results"][1]["score"])

    def test_search_response_stays_small_with_ten_large_documents(self):
        entries = []
        for index in range(10):
            entry = create_entry(name=f"large-rule-{index}", title=f"Large rule {index}")
            entry["routing"]["summary"] = f"Large payment retry rule number {index}."
            entry["content"] = (f"large content {index} " * 900).strip()
            entries.append(entry)
        write_knowledge(self.root, entries)
        result = search_knowledge(self.root, ["payment retry"], limit=10)
        self.assertEqual(len(result["results"]), 10)
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertLess(len(encoded), 12_000)
        self.assertNotIn("large content", encoded)

    def test_update_can_be_built_from_full_read_without_losing_routing(self):
        created = write_knowledge(self.root, [create_entry()])["changes"][0]
        current = read_knowledge(self.root, [created["id"]])["results"][0]
        update = {
            "id": current["id"],
            "expected_revision": current["revision"],
            "canonical_name": current["canonical_name"],
            "title": current["title"],
            "scope": current["scope"],
            "routing": current["routing"],
            "content": current["content"] + "\n\nBổ sung verified.",
            "sources": current["sources"],
        }
        updated = write_knowledge(self.root, [update])["changes"][0]
        reread = read_knowledge(self.root, [updated["id"]])["results"][0]
        self.assertIn("Bổ sung verified.", reread["content"])
        self.assertEqual(reread["routing"], current["routing"])

    def test_update_requires_revision_and_rejects_stale_write(self):
        created = write_knowledge(self.root, [create_entry()])["changes"][0]
        update = create_entry(title="Updated retry rule")
        update["id"] = created["id"]
        update["expected_revision"] = created["revision"]
        updated = write_knowledge(self.root, [update])["changes"][0]
        self.assertEqual(updated["operation"], "updated")

        stale = create_entry(title="Stale update")
        stale["id"] = created["id"]
        stale["expected_revision"] = created["revision"]
        with self.assertRaises(ConflictError):
            write_knowledge(self.root, [stale])

    def test_external_edit_makes_search_and_read_stale_until_reindex(self):
        created = write_knowledge(self.root, [create_entry()])["changes"][0]
        path = self.root / created["path"]
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("không retry payment", "không retry payment lần nữa"),
            encoding="utf-8",
        )
        with self.assertRaises(ConflictError):
            search_knowledge(self.root, ["payment retry"])
        with self.assertRaises(ConflictError):
            read_knowledge(self.root, [created["id"]])
        reindex_store(self.root)
        searched = search_knowledge(self.root, ["payment retry"])
        self.assertEqual(searched["results"][0]["id"], created["id"])
        result = read_knowledge(self.root, [created["id"]])
        self.assertIn("lần nữa", result["results"][0]["content"])

    def test_manual_wrong_path_is_rejected(self):
        entry = create_entry()
        data = {
            "version": 1,
            "id": "domain:checkout.payment:retry-after-commit",
            "canonical_name": entry["canonical_name"],
            "title": entry["title"],
            "scope": entry["scope"],
            "routing": entry["routing"],
            "sources": entry["sources"],
        }
        wrong = self.root / "repos/checkout/retry-after-commit.md"
        wrong.parent.mkdir(parents=True, exist_ok=True)
        wrong.write_text(
            "---\n"
            + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
            + "---\n\n# Retry after commit\n\nbody\n",
            encoding="utf-8",
        )
        checked = check_store(self.root)
        self.assertFalse(checked["ok"])
        self.assertTrue(any("canonical path" in error for error in checked["errors"]))

    def test_duplicate_create_is_rejected(self):
        write_knowledge(self.root, [create_entry()])
        with self.assertRaises(ConflictError):
            write_knowledge(self.root, [create_entry()])

    def test_empty_write_records_review_without_mutation(self):
        before = (self.root / "INDEX.md").read_bytes()
        result = write_knowledge(self.root, [])
        after = (self.root / "INDEX.md").read_bytes()
        self.assertEqual(result, {"reviewed": True, "changes": []})
        self.assertEqual(before, after)

    def test_content_size_and_scope_path_guards(self):
        oversized = create_entry()
        oversized["content"] = "x" * 24_001
        with self.assertRaises(ValidationError):
            write_knowledge(self.root, [oversized])

        traversal = create_entry()
        traversal["scope"] = {"kind": "domain", "id": "checkout/../../secret"}
        with self.assertRaises(ValidationError):
            write_knowledge(self.root, [traversal])

    def test_symlink_escape_is_rejected(self):
        outside_temp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_temp.cleanup)
        checkout = self.root / "domains/checkout"
        try:
            checkout.symlink_to(Path(outside_temp.name), target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")

        with self.assertRaises(ValidationError):
            write_knowledge(self.root, [create_entry()])
        self.assertEqual(list(Path(outside_temp.name).rglob("*.md")), [])

    def test_language_field_is_not_part_of_schema(self):
        entry = create_entry()
        entry["language"] = "vi"
        with self.assertRaises(ValidationError):
            write_knowledge(self.root, [entry])

    def test_batch_validation_prevents_partial_write(self):
        first = create_entry(name="first-rule", title="First rule")
        second = create_entry(name="second-rule", title="Second rule")
        second["scope"] = {"kind": "domain", "id": "bad/path"}
        with self.assertRaises(ValidationError):
            write_knowledge(self.root, [first, second])
        self.assertFalse((self.root / "domains/checkout/payment/first-rule.md").exists())
        self.assertTrue(check_store(self.root)["ok"])

    def test_reindex_and_check_detect_manual_document(self):
        created = write_knowledge(self.root, [create_entry()])["changes"][0]
        path = self.root / created["path"]
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("duplicate payment", "duplicate payment delivery"),
            encoding="utf-8",
        )
        self.assertFalse(check_store(self.root)["ok"])
        reindex_store(self.root)
        self.assertTrue(check_store(self.root)["ok"])
        docs = scan_documents(self.root)
        self.assertEqual(len(docs), 1)


if __name__ == "__main__":
    unittest.main()
