from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from qiqi_eval.capture import runtime_evidence


class CaptureTests(unittest.TestCase):
    def test_runtime_collector_reads_known_tables_without_requiring_runtime_imports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
            db.parent.mkdir(parents=True)
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE graph_runs (graph_run_id TEXT, updated_at_ns INTEGER)"
            )
            conn.execute("INSERT INTO graph_runs VALUES ('g1', 1)")
            conn.execute("CREATE TABLE unrelated (value TEXT)")
            conn.commit()
            conn.close()
            evidence = runtime_evidence(root)
            self.assertEqual(evidence["tables"]["graph_runs"][0]["graph_run_id"], "g1")
            self.assertNotIn("unrelated", evidence["tables"])


if __name__ == "__main__":
    unittest.main()
