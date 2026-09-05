#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_exact(path: Path, old: str, new: str, *, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} occurrence(s), found {actual}: {old!r}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")


# Knowledge: keep actionable details but redact physical paths before they reach ToolError.
knowledge = ROOT / "knowledge-template/mcp/knowledge/server.py"
replace_exact(knowledge, "import os\nfrom pathlib import Path\n", "import os\nimport re\nfrom pathlib import Path\n")
replace_exact(
    knowledge,
    """def _raise_actionable_error(exc: KnowledgeError) -> None:\n    message = str(exc)\n""",
    """_ABSOLUTE_PATH_RE = re.compile(r\"(?<![\\w])(?:[A-Za-z]:[\\\\/]|/)[^\\s;,)\\]}]+\")\n\n\ndef _redact_physical_paths(message: str) -> str:\n    return _ABSOLUTE_PATH_RE.sub(\"<redacted-path>\", message)\n\n\ndef _raise_actionable_error(exc: KnowledgeError) -> None:\n    message = _redact_physical_paths(str(exc))\n""",
)
replace_exact(
    knowledge,
    '        raise ToolError(f"code=knowledge_conflict; {message}") from exc\n',
    '        raise ToolError(\n            f"code=knowledge_conflict; {message}; "\n            "action=read the exact knowledge target again, inspect the reported conflict, and retry only after reconciling current state"\n        ) from exc\n',
)

# Work Item: every anticipated ToolError follows code/detail/action.
work_item = ROOT / "work-item-template/mcp/work_item/server.py"
replace_exact(
    work_item,
    '        raise ToolError(f"code=artifact_conflict; {message}") from exc\n',
    '        raise ToolError(\n            f"code=artifact_conflict; {message}; "\n            "action=call work_item_artifact_get/list to inspect current artifact state before retrying"\n        ) from exc\n',
)
replace_exact(
    work_item,
    '        raise ToolError(f"code=work_item_conflict; {message}") from exc\n',
    '        raise ToolError(\n            f"code=work_item_conflict; {message}; "\n            "action=call work_item_get again, reconcile against current canonical state, then retry"\n        ) from exc\n',
)
replace_exact(
    work_item,
    '        raise ToolError(f"code=work_item_validation; {exc}") from exc\n',
    '        raise ToolError(\n            f"code=work_item_validation; {exc}; "\n            "action=correct the request to match the typed Work Item tool schema and retry"\n        ) from exc\n',
)

# QiQi Delegate: never embed TaskPacket text into a RuntimeError that is later classified.
qiqi = ROOT / "workspace-template/mcp/qiqi_delegate/server.py"
text = qiqi.read_text(encoding="utf-8")
start = text.index("async def _prompt_and_wait(")
end = text.index("\n\nasync def _wait_for_result_capture", start)
block = text[start:end]
old_block = block
block = block.replace(
    '    command = ["agent", "prompt", name, prompt, "--wait"]\n',
    '    command = ["agent", "prompt", name, prompt, "--wait"]\n'
    '    display_command = ["agent", "prompt", name, "<task-packet>", "--wait"]\n',
    1,
)
block = block.replace(
    '        detail = (stderr or stdout).strip()\n',
    '        detail = (stderr or stdout).replace(prompt, "<task-packet>").strip()\n',
    1,
)
block = block.replace("{' '.join(command)}", "{' '.join(display_command)}")
if block == old_block:
    raise SystemExit("qiqi_delegate: _prompt_and_wait patch made no changes")
if "display_command" not in block or "replace(prompt" not in block:
    raise SystemExit("qiqi_delegate: prompt redaction patch incomplete")
qiqi.write_text(text[:start] + block + text[end:], encoding="utf-8")

# Workspace checker: dependency-bearing QiQi tests must run inside the uv project environment.
checker = ROOT / "workspace-template/scripts/workspace-check.sh"
replace_exact(
    checker,
    'python3 -m unittest discover -s "$mcp_project/tests" -v || \\\n  fail \'qiqi_delegate: unit tests failed\'\n',
    'uv run --project "$mcp_project" python -m unittest discover -s "$mcp_project/tests" -v || \\\n  fail \'qiqi_delegate: unit tests failed\'\n',
)

# Review regressions are intentionally separate from the existing suites.
(ROOT / "knowledge-template/mcp/knowledge/tests/test_review_5120952535.py").write_text(
    '''from __future__ import annotations\n\nimport os\nimport sys\nimport tempfile\nimport unittest\nfrom pathlib import Path\nfrom unittest.mock import patch\n\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n\nfrom core import ConflictError, ValidationError, init_store\nfrom mcp import Client\nfrom server import _raise_actionable_error, mcp\n\n\ndef valid_entry() -> dict:\n    return {\n        "canonical_name": "review-path-redaction",\n        "title": "Review path redaction",\n        "scope": {"kind": "domain", "id": "review.transport"},\n        "routing": {\n            "summary": "Review error transport path redaction.",\n            "when_to_read": ["reviewing MCP error transport"],\n            "keywords": ["review", "transport", "redaction"],\n            "aliases": [],\n        },\n        "content": "review",\n        "sources": [{"kind": "manual", "locator": "review regression"}],\n    }\n\n\ndef error_text(result) -> str:\n    return "\\n".join(\n        block.text for block in result.content if getattr(block, "type", None) == "text"\n    )\n\n\nclass KnowledgeReview5120952535Test(unittest.IsolatedAsyncioTestCase):\n    async def test_validation_tool_error_redacts_absolute_store_paths(self):\n        with tempfile.TemporaryDirectory() as temp_dir:\n            root = Path(temp_dir) / "store"\n            init_store(root)\n            leaked = str(root / "domain" / "review" / "secret.md")\n            with patch.dict(os.environ, {"KNOWLEDGE_STORE_ROOT": str(root)}):\n                with patch(\n                    "server.write_knowledge",\n                    side_effect=ValidationError(f"indexed document is invalid: {leaked}"),\n                ):\n                    async with Client(mcp) as client:\n                        result = await client.call_tool(\n                            "knowledge_write", {"entries": [valid_entry()]}\n                        )\n        text = error_text(result)\n        self.assertTrue(result.is_error)\n        self.assertIn("code=knowledge_validation", text)\n        self.assertIn("<redacted-path>", text)\n        self.assertNotIn(str(root), text)\n        self.assertIn("; action=", text)\n\n    def test_generic_knowledge_conflict_has_recovery_action(self):\n        with self.assertRaises(Exception) as raised:\n            _raise_actionable_error(ConflictError("generic knowledge conflict"))\n        text = str(raised.exception)\n        self.assertIn("code=knowledge_conflict", text)\n        self.assertIn("; action=", text)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

(ROOT / "work-item-template/mcp/work_item/tests/test_review_5120952535.py").write_text(
    '''from __future__ import annotations\n\nimport sys\nimport unittest\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n\nfrom mcp.server.mcpserver.exceptions import ToolError\nfrom artifacts import ArtifactConflictError\nfrom core import ConflictError, ValidationError\nfrom server import _raise_actionable_error\n\n\nclass WorkItemReview5120952535Test(unittest.TestCase):\n    def assert_actionable(self, exc, code: str) -> None:\n        with self.assertRaises(ToolError) as raised:\n            _raise_actionable_error(exc)\n        text = str(raised.exception)\n        self.assertIn(f"code={code}", text)\n        self.assertIn("; action=", text)\n\n    def test_generic_artifact_conflict_has_action(self):\n        self.assert_actionable(ArtifactConflictError("generic artifact conflict"), "artifact_conflict")\n\n    def test_generic_work_item_conflict_has_action(self):\n        self.assert_actionable(ConflictError("generic work item conflict"), "work_item_conflict")\n\n    def test_validation_error_has_action(self):\n        self.assert_actionable(ValidationError("invalid work item request"), "work_item_validation")\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

(ROOT / "workspace-template/mcp/qiqi_delegate/tests/test_review_5120952535.py").write_text(
    '''from __future__ import annotations\n\nimport sys\nimport unittest\nfrom pathlib import Path\nfrom unittest.mock import AsyncMock, patch\n\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n\nfrom server import _delegation_tool_error, _prompt_and_wait\n\n\nclass QiQiReview5120952535Test(unittest.IsolatedAsyncioTestCase):\n    async def test_task_packet_text_cannot_select_error_code(self):\n        prompt = "Investigate an unknown repository and unknown route report."\n        with patch(\n            "server._run_herdr",\n            AsyncMock(return_value=(1, "", f"failed command echoed: {prompt}")),\n        ):\n            with self.assertRaises(RuntimeError) as raised:\n                await _prompt_and_wait("agent-1", prompt, "codex")\n\n        internal = str(raised.exception)\n        self.assertNotIn(prompt, internal)\n        public = str(_delegation_tool_error(raised.exception))\n        self.assertIn("code=herdr_runtime_failed", public)\n        self.assertNotIn("code=unknown_repository", public)\n        self.assertNotIn("code=unknown_route", public)\n\n    def test_workspace_checker_runs_qiqi_tests_in_uv_project(self):\n        workspace_root = Path(__file__).resolve().parents[3]\n        checker = (workspace_root / "scripts/workspace-check.sh").read_text(encoding="utf-8")\n        self.assertIn(\n            'uv run --project "$mcp_project" python -m unittest discover -s "$mcp_project/tests" -v',\n            checker,\n        )\n        self.assertNotIn(\n            'python3 -m unittest discover -s "$mcp_project/tests" -v',\n            checker,\n        )\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

print("review fixes applied")
