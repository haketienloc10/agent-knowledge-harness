from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import _build_filesystem_args, _build_interactive_args, _load_execution_config


class ClaudeFilesystemRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace_root = Path(__file__).resolve().parents[3]
        config_path = cls.workspace_root / "instructions" / "agent-routing.yaml"
        cls.config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    def test_config_declares_optional_generic_directory_for_claude_only(self) -> None:
        claude = self.config["agents"]["claude"]
        codex = self.config["agents"]["codex"]

        self.assertEqual(
            claude["filesystem"]["additional_dirs"],
            [{"env": "QIQI_CLAUDE_ADDITIONAL_DIR", "required": False}],
        )
        self.assertNotIn("filesystem", codex)

    def test_missing_optional_directory_does_not_add_claude_flag(self) -> None:
        agents, routes = _load_execution_config()
        with patch.dict(os.environ, {"QIQI_CLAUDE_ADDITIONAL_DIR": ""}):
            args = _build_interactive_args(
                agents["claude"],
                routes["claude-balanced"],
                None,
                ["--settings", "{}"],
            )

        self.assertNotIn("--add-dir", args)

    def test_absolute_directory_is_added_to_start_and_resume(self) -> None:
        agents, routes = _load_execution_config()
        with tempfile.TemporaryDirectory() as temp_dir:
            expected = str(Path(temp_dir).resolve())
            with patch.dict(os.environ, {"QIQI_CLAUDE_ADDITIONAL_DIR": temp_dir}):
                start_args = _build_interactive_args(
                    agents["claude"],
                    routes["claude-balanced"],
                    None,
                    ["--settings", "{}"],
                )
                resume_args = _build_interactive_args(
                    agents["claude"],
                    routes["claude-balanced"],
                    "session-123",
                    ["--settings", "{}"],
                )

        self.assertEqual(start_args[:2], ["--add-dir", expected])
        self.assertEqual(resume_args[:2], ["--add-dir", expected])
        self.assertIn("--resume", resume_args)
        self.assertIn("session-123", resume_args)

    def test_relative_directory_is_rejected(self) -> None:
        agents, routes = _load_execution_config()
        with patch.dict(os.environ, {"QIQI_CLAUDE_ADDITIONAL_DIR": "relative/evidence"}):
            with self.assertRaisesRegex(RuntimeError, "must be absolute"):
                _build_interactive_args(
                    agents["claude"],
                    routes["claude-balanced"],
                    None,
                    ["--settings", "{}"],
                )

    def test_codex_routing_remains_unchanged(self) -> None:
        agents, routes = _load_execution_config()
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"QIQI_CLAUDE_ADDITIONAL_DIR": temp_dir}):
                args = _build_interactive_args(
                    agents["codex"],
                    routes["codex-balanced"],
                    None,
                    ["-c", "hooks.Stop=[]"],
                )

        self.assertNotIn("--add-dir", args)

    def test_empty_filesystem_list_is_a_noop_for_non_claude_adapter(self) -> None:
        agent = {
            "adapter": "codex",
            "filesystem": {"additional_dirs": []},
        }
        self.assertEqual(_build_filesystem_args(agent), [])


if __name__ == "__main__":
    unittest.main()
