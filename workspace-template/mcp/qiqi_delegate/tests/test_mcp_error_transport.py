from __future__ import annotations

import importlib.metadata
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import Client  # noqa: E402
from server import mcp  # noqa: E402


def error_text(result) -> str:
    return "\n".join(
        block.text
        for block in result.content
        if getattr(block, "type", None) == "text"
    )


def valid_args() -> dict:
    return {
        "repository": "repo-a",
        "route": "codex-balanced",
        "user_request": "Fix the repository-local behavior.",
        "objective": "Fix the repository-local behavior.",
        "scope": ["current repository"],
        "out_of_scope": [],
        "required_context": [],
        "constraints": [],
        "acceptance_criteria": ["Focused repository verification passes."],
        "verification": [],
        "known_unknowns": [],
    }


class QiQiDelegateMcpErrorTransportTest(unittest.IsolatedAsyncioTestCase):
    def test_sdk_version_is_reviewed(self) -> None:
        self.assertEqual(importlib.metadata.version("mcp"), "2.1.1")

    async def test_unknown_repository_is_model_visible(self) -> None:
        with patch(
            "server._resolve_repo",
            side_effect=RuntimeError(
                "unknown repository 'repo-a'; available repositories: repo-b"
            ),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool("delegate_repo_task", valid_args())

        self.assertTrue(result.is_error)
        text = error_text(result)
        self.assertIn("code=unknown_repository", text)
        self.assertIn("repos.yaml", text)
        self.assertNotEqual(text, "Error executing tool delegate_repo_task")

    async def test_herdr_integration_failure_names_recovery(self) -> None:
        agent = {"adapter": "codex", "command": "codex"}
        route = {"model": "gpt-5", "args": []}
        with (
            patch("server._resolve_repo", return_value=Path("/tmp/repo")),
            patch("server._resolve_route", return_value=("codex", agent, route)),
            patch("server.shutil.which", return_value="/usr/bin/codex"),
            patch("server._ensure_herdr_server", new=AsyncMock(return_value=None)),
            patch(
                "server._require_current_integration",
                new=AsyncMock(
                    side_effect=RuntimeError(
                        "Herdr codex integration is not current; run `herdr integration install codex` before using interactive delegation"
                    )
                ),
            ),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool("delegate_repo_task", valid_args())

        self.assertTrue(result.is_error)
        text = error_text(result)
        self.assertIn("code=herdr_integration_not_current", text)
        self.assertIn("herdr integration install codex", text)

    async def test_unexpected_programming_error_remains_masked(self) -> None:
        with patch(
            "server._resolve_repo",
            side_effect=TypeError("secret internal implementation detail"),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool("delegate_repo_task", valid_args())

        self.assertTrue(result.is_error)
        text = error_text(result)
        self.assertIn("Error executing tool delegate_repo_task", text)
        self.assertNotIn("secret internal implementation detail", text)


if __name__ == "__main__":
    unittest.main()
