from __future__ import annotations

import multiprocessing
import tempfile
import unittest
from pathlib import Path

from core import KnowledgeError, KnowledgeStore, knowledge_id, render_detail


def entry(*, name: str = "retry-after-commit", title: str = "Retry sau commit") -> dict:
    return {
        "canonical_name": name,
        "title": title,
        "scope": {"kind": "domain", "id": "checkout.payment"},
        "routing": {
            "summary": "Payment must not be retried after a successful transaction commit.",
            "when_to_read": [
                "modifying payment retry behavior",
                "changing transaction commit handling",
            ],
            "keywords": ["payment", "retry", "transaction", "commit", "idempotency"],
            "aliases": ["retry thanh toán", "không retry sau commit"],
        },
        "content": "Nội dung có thể dùng tiếng Việt.",
        "sources": [
            {
                "type": "repo",
                "repo": "checkout",
                "path": "src/payment/retry.ts",
                "ref": "abc123",
            }
        ],
    }


def _write_process(root: str, name: str, title: str) -> None:
    store = KnowledgeStore(Path(root))
    store.write([entry(name=name, title=title)])


class KnowledgeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = KnowledgeStore(self.root)
        self.store.initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_create_read_update_and_empty_review(self) -> None:
        created = self.store.write([entry()])
        update = created["updates"][0]
        self.assertEqual(
            update["path"],
            "domains/checkout/payment/retry-after-commit.md",
        )

        found = self.store.read(
            ["payment retry", "idempotency", "retry thanh toán"],
            context={"repo": "checkout"},
        )
        self.assertEqual(found["documents"][0]["id"], update["id"])
        self.assertEqual(
            found["documents"][0]["content"],
            "Nội dung có thể dùng tiếng Việt.",
        )

        current = found["documents"][0]
        changed = entry()
        changed.update(
            {
                "id": current["id"],
                "expected_revision": current["revision"],
            }
        )
        changed["content"] = "Nội dung mới."
        updated = self.store.write([changed])
        self.assertEqual(updated["updates"][0]["action"], "updated")
        self.assertEqual(
            self.store.read(["payment retry"])["documents"][0]["content"],
            "Nội dung mới.",
        )

        reviewed = self.store.write([])
        self.assertTrue(reviewed["reviewed"])
        self.assertEqual(reviewed["updates"], [])

    def test_revision_conflict_rejected(self) -> None:
        self.store.write([entry()])
        current = self.store.read(["payment retry"])["documents"][0]

        path = self.root / current["path"]
        path.write_text(
            path.read_text(encoding="utf-8") + "\nmanual edit\n",
            encoding="utf-8",
        )

        changed = entry()
        changed.update(
            {
                "id": current["id"],
                "expected_revision": current["revision"],
            }
        )
        with self.assertRaisesRegex(KnowledgeError, "revision conflict"):
            self.store.write([changed])

    def test_manual_document_requires_reindex(self) -> None:
        first = self.store.write([entry()])["updates"][0]

        other = entry(name="duplicate-delivery", title="Duplicate delivery")
        other["routing"]["summary"] = "Handle duplicate payment delivery idempotently."
        other["content"] = "Manual content."
        item_id = knowledge_id(other["scope"], other["canonical_name"])
        relative = Path("domains/checkout/payment/duplicate-delivery.md")
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_detail(other, item_id), encoding="utf-8")

        with self.assertRaisesRegex(KnowledgeError, "stale"):
            self.store.check()
        self.store.reindex()
        self.assertEqual(self.store.check()["documents"], 2)
        ids = {
            document["id"]
            for document in self.store.read(["duplicate payment"], limit=5)["documents"]
        }
        self.assertIn(item_id, ids)
        self.assertNotEqual(first["id"], item_id)

    def test_noncanonical_manual_path_rejected(self) -> None:
        item = entry()
        item_id = knowledge_id(item["scope"], item["canonical_name"])
        wrong = self.root / "repos/checkout/wrong.md"
        wrong.parent.mkdir(parents=True, exist_ok=True)
        wrong.write_text(render_detail(item, item_id), encoding="utf-8")
        with self.assertRaisesRegex(KnowledgeError, "canonical path"):
            self.store.reindex()

    def test_document_without_aliases_is_canonical(self) -> None:
        item = entry()
        item["routing"].pop("aliases")
        self.store.write([item])
        self.assertEqual(self.store.check()["documents"], 1)
        found = self.store.read(["payment retry"])
        self.assertEqual(found["documents"][0]["routing"]["aliases"], [])

    def test_unknown_storage_field_rejected(self) -> None:
        bad = entry()
        bad["path"] = "domains/checkout/payment/custom.md"
        with self.assertRaisesRegex(KnowledgeError, "unsupported field"):
            self.store.write([bad])

    def test_concurrent_process_writes_preserve_index(self) -> None:
        first = multiprocessing.Process(
            target=_write_process,
            args=(str(self.root), "first-rule", "First rule"),
        )
        second = multiprocessing.Process(
            target=_write_process,
            args=(str(self.root), "second-rule", "Second rule"),
        )
        first.start()
        second.start()
        first.join(10)
        second.join(10)
        self.assertEqual(first.exitcode, 0)
        self.assertEqual(second.exitcode, 0)
        self.assertEqual(self.store.check()["documents"], 2)

    def test_relative_store_root_rejected(self) -> None:
        with self.assertRaisesRegex(KnowledgeError, "absolute path"):
            KnowledgeStore(Path("relative-knowledge"))

    def test_bad_scope_rejected(self) -> None:
        bad = entry()
        bad["scope"] = {"kind": "domain", "id": "../../checkout"}
        with self.assertRaisesRegex(KnowledgeError, "scope.id"):
            self.store.write([bad])


if __name__ == "__main__":
    unittest.main()
