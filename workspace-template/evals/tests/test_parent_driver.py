from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from qiqi_eval.parent_driver import (
    CODEX_TRUST_CONFIRM,
    CODEX_TRUST_PROMPT,
    _ensure_parent_startup_ready,
    _load_delegate_server,
    _start_eval_parent_agent,
    _workspace_environment,
)


class _FakeHerdrServer:
    HERDR_AGENT_START_TIMEOUT_MS = 60_000
    HERDR_SHELL_READY_TIMEOUT_SECONDS = 1.0

    def __init__(self, surfaces: list[str], *, start_blocked: bool = False):
        self.surfaces = list(surfaces)
        self.sent_keys: list[tuple[str, ...]] = []
        self.start_blocked = start_blocked
        self.started_name: str | None = None

    async def _run_herdr(self, *args: str, check: bool = True):
        if args[:2] == ("agent", "start"):
            self.started_name = args[2]
            if self.start_blocked:
                return (
                    1,
                    '{"error":{"code":"agent_not_ready","message":"blocked during startup"}}',
                    "",
                )
            return (
                0,
                '{"result":{"agent":{"agent_status":"idle"}}}',
                "",
            )
        if args[:2] == ("agent", "read"):
            if len(self.surfaces) > 1:
                surface = self.surfaces.pop(0)
            else:
                surface = self.surfaces[0] if self.surfaces else ""
            return 0, surface, ""
        if args[:2] == ("agent", "send-keys"):
            self.sent_keys.append(args)
            return 0, "", ""
        raise AssertionError(f"unexpected Herdr call: {args}")

    @staticmethod
    def _herdr_json_payload(stdout: str, stderr: str):
        import json

        for raw in (stdout, stderr):
            if raw.strip():
                return json.loads(raw)
        return None

    @staticmethod
    def _herdr_error_code(payload):
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        return error.get("code") if isinstance(error, dict) else None

    @staticmethod
    def _agent_from_payload(payload, context: str):
        return payload["result"]["agent"]

    async def _get_agent(self, name: str):
        if name != self.started_name:
            raise AssertionError(f"unexpected agent lookup: {name}")
        return {"agent_status": "blocked"}


class ParentDriverTests(unittest.TestCase):
    def test_dynamic_delegate_server_registers_module_for_postponed_annotations(self) -> None:
        template_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            target = workspace / "mcp" / "qiqi_delegate"
            target.parent.mkdir(parents=True)
            shutil.copytree(template_root / "mcp" / "qiqi_delegate", target)

            module = None
            with _workspace_environment(workspace):
                module = _load_delegate_server(workspace)
                self.assertIs(sys.modules.get(module.__name__), module)
                self.assertTrue(hasattr(module, "delegate_repo_task"))
                self.assertTrue(hasattr(module, "TrustedFactInput"))
                self.assertTrue(hasattr(module, "TaskContextInput"))

            if module is not None:
                sys.modules.pop(module.__name__, None)

    def test_codex_startup_block_returns_created_agent_for_trust_recovery(self) -> None:
        server = _FakeHerdrServer([], start_blocked=True)

        name, agent = asyncio.run(
            _start_eval_parent_agent(server, "pane-1", "codex", ["--model", "gpt-5.6-luna"])
        )

        self.assertEqual(name, server.started_name)
        self.assertEqual(agent["agent_status"], "blocked")

    def test_codex_eval_parent_accepts_exact_directory_trust_gate_once(self) -> None:
        server = _FakeHerdrServer(
            [
                f"{CODEX_TRUST_PROMPT}\n1. Yes, continue\n{CODEX_TRUST_CONFIRM}\n",
                "Codex ready\n",
            ]
        )

        asyncio.run(_ensure_parent_startup_ready(server, "parent", "codex"))

        self.assertEqual(
            server.sent_keys,
            [("agent", "send-keys", "parent", "enter")],
        )

    def test_non_codex_parent_does_not_probe_or_send_keys(self) -> None:
        server = _FakeHerdrServer(["unused"])

        asyncio.run(_ensure_parent_startup_ready(server, "parent", "claude"))

        self.assertEqual(server.sent_keys, [])


if __name__ == "__main__":
    unittest.main()
