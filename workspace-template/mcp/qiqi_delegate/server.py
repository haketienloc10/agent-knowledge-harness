#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import yaml
from mcp.server import MCPServer

WORKSPACE_ROOT = Path(
    os.environ.get("QIQI_WORKSPACE_ROOT", Path(__file__).resolve().parents[2])
).resolve()

RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string", "enum": ["completed", "blocked"]},
        "changes": {"type": "array", "items": {"type": "string"}},
        "verification": {"type": "array", "items": {"type": "string"}},
        "git_state": {"type": "string"},
        "blockers": {"type": "array", "items": {"type": "string"}},
        "repo_local_knowledge": {"type": "array", "items": {"type": "string"}},
        "cross_repo_impact": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "outcome",
        "changes",
        "verification",
        "git_state",
        "blockers",
        "repo_local_knowledge",
        "cross_repo_impact",
    ],
    "additionalProperties": False,
}

mcp = MCPServer(
    "QiQi Delegate",
    instructions=(
        "Synchronous execution boundary for QiQi. Use delegate_repo_task for every "
        "repo-local investigation, edit, Git inspection, and verification. A call "
        "owns the full child-agent turn and returns only at terminal completion. "
        "There are intentionally no status, wait, read, resume, list-runs, or "
        "transcript tools. Do not replace this tool with shell-based delegation."
    ),
)

_delegate_lock = asyncio.Lock()


def _load_repo_registry() -> dict[str, Path]:
    registry_path = WORKSPACE_ROOT / "repos.yaml"
    if not registry_path.is_file():
        raise RuntimeError(f"missing workspace registry: {registry_path}")

    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    repositories = data.get("repositories")
    if not isinstance(repositories, list):
        raise RuntimeError("repos.yaml: repositories must be a list")

    result: dict[str, Path] = {}
    for entry in repositories:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        relative_path = entry.get("path")
        if not isinstance(name, str) or not isinstance(relative_path, str):
            continue
        if "{{" in name or "{{" in relative_path:
            continue

        repo = (WORKSPACE_ROOT / relative_path).resolve()
        try:
            repo.relative_to(WORKSPACE_ROOT)
        except ValueError as exc:
            raise RuntimeError(
                f"repos.yaml: repository {name!r} escapes workspace root"
            ) from exc
        result[name] = repo

    return result


def _resolve_repo(repository: str) -> Path:
    registry = _load_repo_registry()
    repo = registry.get(repository)
    if repo is None:
        available = ", ".join(sorted(registry)) or "<none>"
        raise RuntimeError(
            f"unknown repository {repository!r}; available repositories: {available}"
        )
    if not repo.is_dir():
        raise RuntimeError(f"repository path does not exist: {repo}")

    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"not a Git repository: {repo}")

    git_root = Path(completed.stdout.strip()).resolve()
    if git_root != repo:
        raise RuntimeError(
            f"repos.yaml path must be exact Git root: configured={repo}, git={git_root}"
        )
    return repo


def _build_prompt(task: str) -> str:
    return f"""You are the execution agent for exactly one Git repository.

Operating contract:
- Work only inside the current Git repository.
- Read and follow the repository's AGENTS.md and repo-local instructions.
- Do not inspect, edit, or operate on sibling repositories or workspace control files.
- Do not spawn or delegate to another coding agent.
- Complete the task independently, including appropriate verification.
- Keep intermediate reasoning and progress inside this child run.
- Your final response must satisfy the JSON schema supplied by the runner.
- Use [] for empty list fields.
- If a user/product decision or unavailable dependency prevents completion, set outcome to \"blocked\" and explain it in blockers.

Task:
{task}
"""


def _validate_result(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("child final result is not a JSON object")

    expected = {
        "outcome": str,
        "changes": list,
        "verification": list,
        "git_state": str,
        "blockers": list,
        "repo_local_knowledge": list,
        "cross_repo_impact": list,
    }
    for key, expected_type in expected.items():
        if key not in payload:
            raise RuntimeError(f"child final result missing field: {key}")
        if not isinstance(payload[key], expected_type):
            raise RuntimeError(f"child final result has invalid field type: {key}")

    if payload["outcome"] not in {"completed", "blocked"}:
        raise RuntimeError("child final result has invalid outcome")
    return payload


def _safe_runner_diagnostic(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    startup_markers = (
        "unexpected argument",
        "usage: codex exec",
        "error loading config.toml",
        "error parsing -c overrides",
    )
    lowered = text.lower()
    if not any(marker in lowered for marker in startup_markers):
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    return " | ".join(lines[-8:])[:2000]


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


@mcp.tool()
async def delegate_repo_task(
    repository: str,
    task: str,
    model: str | None = None,
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] | None = None,
) -> dict[str, Any]:
    """Execute one repo-local Codex task synchronously and return its final result.

    `repository` must be the exact name from repos.yaml. Use this tool for all
    repo-local investigation, implementation, Git inspection, and verification.
    Optional model settings must come from instructions/model-routing.md.
    """
    repository = repository.strip()
    task = task.strip()
    if not repository:
        raise ValueError("repository must not be empty")
    if not task:
        raise ValueError("task must not be empty")
    if len(task) > 100_000:
        raise ValueError("task is too large")

    if _delegate_lock.locked():
        raise RuntimeError(
            "another delegation is active; do not poll, queue, or start another task"
        )

    async with _delegate_lock:
        repo = _resolve_repo(repository)
        codex_bin = os.environ.get("QIQI_CODEX_BIN", "codex")
        if shutil.which(codex_bin) is None:
            raise RuntimeError(f"missing Codex CLI executable: {codex_bin}")

        run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        started = time.monotonic()

        with tempfile.TemporaryDirectory(prefix="qiqi-delegate-") as temp_dir:
            temp = Path(temp_dir)
            schema_path = temp / "result.schema.json"
            result_path = temp / "result.json"
            transcript_path = temp / "transcript.log"
            schema_path.write_text(
                json.dumps(RESULT_SCHEMA, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            command = [
                codex_bin,
                "exec",
                "--ephemeral",
                "--sandbox",
                "workspace-write",
                "--ignore-user-config",
                "-c",
                "mcp_servers.qiqi_delegate.enabled=false",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(result_path),
            ]
            if model:
                command.extend(["--model", model.strip()])
            if reasoning_effort:
                command.extend(
                    ["-c", f'model_reasoning_effort="{reasoning_effort}"']
                )
            command.append("-")

            with transcript_path.open("wb") as transcript:
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(repo),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=transcript,
                    stderr=asyncio.subprocess.STDOUT,
                )
                try:
                    await proc.communicate(_build_prompt(task).encode("utf-8"))
                except asyncio.CancelledError:
                    await _terminate(proc)
                    raise

            if proc.returncode != 0:
                diagnostic = _safe_runner_diagnostic(transcript_path)
                detail = (
                    f"; runner diagnostic: {diagnostic}"
                    if diagnostic
                    else "; child output is intentionally not exposed to QiQi"
                )
                raise RuntimeError(
                    f"child Codex run failed (run_id={run_id}, exit={proc.returncode})"
                    f"{detail}"
                )
            if not result_path.is_file():
                raise RuntimeError(
                    f"child Codex run produced no final result (run_id={run_id})"
                )

            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"child Codex final result is invalid JSON (run_id={run_id})"
                ) from exc

            result = _validate_result(payload)

        duration = round(time.monotonic() - started, 2)
        return {
            "run_id": run_id,
            "repository": repository,
            "duration_seconds": duration,
            **result,
        }


if __name__ == "__main__":
    mcp.run()
