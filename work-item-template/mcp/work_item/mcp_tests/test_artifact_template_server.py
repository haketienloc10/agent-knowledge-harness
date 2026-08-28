from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ArtifactTemplateServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = Path(__file__).resolve().parents[1]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _subprocess_env(self, config_path: Path | None) -> dict[str, str]:
        env = os.environ.copy()
        if config_path is None:
            env.pop("WORK_ITEM_ARTIFACT_TEMPLATES_PATH", None)
        else:
            env["WORK_ITEM_ARTIFACT_TEMPLATES_PATH"] = str(config_path)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(self.project) + (os.pathsep + existing if existing else "")
        return env

    def _run(self, code: str, config_path: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", code],
            env=self._subprocess_env(config_path),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_default_create_response_attaches_detached_advisory_guidance(self) -> None:
        code = r'''
import server
result = server._with_template_guidance(
    {"artifact_id": "report:1", "type": "report", "revision": 1},
    "report",
)
assert result["artifact_id"] == "report:1"
sections = result["template_guidance"]["sections"]
assert [section["id"] for section in sections] == [
    "root-cause-requirement",
    "solution",
    "affected",
    "impact-module-analysis",
    "sql-report",
    "commits",
    "testcase-ut",
    "deploy",
]
assert sections[0]["title"] == "h3. +1. Root-cause/requirement:+"
assert sections[-1]["title"] == "h3. +8. Deploy:+"
result["template_guidance"]["sections"][0]["title"] = "Mutated"
assert server.ARTIFACT_TEMPLATES["report"]["sections"][0]["title"] == "h3. +1. Root-cause/requirement:+"
'''
        completed = self._run(code)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_missing_configured_template_returns_null_guidance(self) -> None:
        config = self.root / "empty.json"
        config.write_text("{}", encoding="utf-8")
        code = r'''
import server
result = server._with_template_guidance({"artifact_id": "report:1"}, "report")
assert result["template_guidance"] is None
'''
        completed = self._run(code, config)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_server_loads_custom_template_once_per_process(self) -> None:
        config = self.root / "templates.json"
        config.write_text(
            json.dumps(
                {
                    "report": {
                        "description": "Startup value",
                        "sections": [
                            {"id": "one", "title": "One", "purpose": "First"}
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        code = r'''
import json
import os
from pathlib import Path
import server

path = Path(os.environ["WORK_ITEM_ARTIFACT_TEMPLATES_PATH"])
path.write_text(json.dumps({
    "report": {
        "description": "Changed on disk",
        "sections": [{"id": "two", "title": "Two", "purpose": "Second"}],
    }
}), encoding="utf-8")
result = server._with_template_guidance({"artifact_id": "report:1"}, "report")
assert result["template_guidance"]["description"] == "Startup value"
assert result["template_guidance"]["sections"][0]["id"] == "one"
'''
        completed = self._run(code, config)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_invalid_custom_template_fails_server_startup(self) -> None:
        config = self.root / "invalid.json"
        config.write_text(
            json.dumps(
                {
                    "architecture": {
                        "description": "Unsupported dynamic artifact type",
                        "sections": [],
                    }
                }
            ),
            encoding="utf-8",
        )
        completed = self._run("import server", config)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unsupported types", completed.stderr)


if __name__ == "__main__":
    unittest.main()
