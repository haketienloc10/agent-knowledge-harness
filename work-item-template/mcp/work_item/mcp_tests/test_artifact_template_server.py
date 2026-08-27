from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class ArtifactTemplateServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = Path(__file__).resolve().parents[1]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _subprocess_env(self, config_path: Path) -> dict[str, str]:
        env = os.environ.copy()
        env["WORK_ITEM_ARTIFACT_TEMPLATES_PATH"] = str(config_path)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(self.project) + (os.pathsep + existing if existing else "")
        return env

    def test_create_response_helper_attaches_advisory_guidance(self) -> None:
        result = server._with_template_guidance(
            {"artifact_id": "report:1", "type": "report", "revision": 1},
            "report",
        )
        self.assertEqual(result["artifact_id"], "report:1")
        self.assertEqual(
            result["template_guidance"]["sections"][0]["id"], "original-request"
        )

    def test_missing_configured_template_returns_null_guidance(self) -> None:
        with patch.object(server, "ARTIFACT_TEMPLATES", {}):
            result = server._with_template_guidance(
                {"artifact_id": "report:1", "type": "report"}, "report"
            )
        self.assertIsNone(result["template_guidance"])

    def test_guidance_response_cannot_mutate_startup_config(self) -> None:
        result = server._with_template_guidance(
            {"artifact_id": "report:1", "type": "report"}, "report"
        )
        result["template_guidance"]["sections"][0]["title"] = "Mutated"
        self.assertEqual(
            server.ARTIFACT_TEMPLATES["report"]["sections"][0]["title"],
            "Original Request",
        )

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
        completed = subprocess.run(
            [sys.executable, "-c", code],
            env=self._subprocess_env(config),
            text=True,
            capture_output=True,
            check=False,
        )
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
        completed = subprocess.run(
            [sys.executable, "-c", "import server"],
            env=self._subprocess_env(config),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unsupported types", completed.stderr)


if __name__ == "__main__":
    unittest.main()
