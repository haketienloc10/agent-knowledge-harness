#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from mcp.server import MCPServer

WORKSPACE_ROOT = Path(
    os.environ.get("QIQI_WORKSPACE_ROOT", Path(__file__).resolve().parents[2])
).resolve()
ROUTING_PATH = WORKSPACE_ROOT / "instructions" / "agent-routing.yaml"
SUPPORTED_ADAPTERS = {"codex", "claude"}
PLACEHOLDER_RE = re.compile(r"\{(?:model|session_id|schema_path|result_path|route_args)\}")

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
        "repo-local investigation, edit, Git inspection, and verification. Select "
        "an execution route from instructions/agent-routing.yaml. Omit session_id "
        "to START; pass the native Codex/Claude session_id returned by a previous "
        "terminal result to RESUME. Independent repositories may execute "
        "concurrently; within this server process, concurrent calls targeting the "
        "same resolved Git root or native session are rejected. There are "
        "intentionally no status, wait, read, list-runs, transcript, or separate "
        "resume tools."
    ),
)

_state_lock = asyncio.Lock()
_active_repositories: set[Path] = set()
_active_sessions: set[str] = set()


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


def _require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"{label} must be a list of strings")
    return value


def _load_execution_config() -> tuple[dict[str, Any], dict[str, Any]]:
    if not ROUTING_PATH.is_file():
        raise RuntimeError(f"missing agent routing registry: {ROUTING_PATH}")

    data = yaml.safe_load(ROUTING_PATH.read_text(encoding="utf-8")) or {}
    if data.get("version") != 1:
        raise RuntimeError("agent-routing.yaml: version must be 1")

    agents = data.get("agents")
    routes = data.get("routes")
    if not isinstance(agents, dict) or not agents:
        raise RuntimeError("agent-routing.yaml: agents must be a non-empty map")
    if not isinstance(routes, dict) or not routes:
        raise RuntimeError("agent-routing.yaml: routes must be a non-empty map")

    for name, config in agents.items():
        if not isinstance(name, str) or not isinstance(config, dict):
            raise RuntimeError("agent-routing.yaml: invalid agent entry")
        command = config.get("command")
        adapter = config.get("adapter")
        prompt_transport = config.get("prompt_transport")
        if not isinstance(command, str) or not command.strip():
            raise RuntimeError(f"agent {name}: command must be a non-empty string")
        if adapter not in SUPPORTED_ADAPTERS:
            raise RuntimeError(
                f"agent {name}: unsupported adapter {adapter!r}; "
                f"supported: {', '.join(sorted(SUPPORTED_ADAPTERS))}"
            )
        if prompt_transport not in {"stdin", "argument"}:
            raise RuntimeError(
                f"agent {name}: prompt_transport must be stdin or argument"
            )
        _require_string_list(config.get("start_args"), f"agent {name}.start_args")
        resume_args = config.get("resume_args")
        if resume_args is not None:
            _require_string_list(resume_args, f"agent {name}.resume_args")
            if not any("{session_id}" in item for item in resume_args):
                raise RuntimeError(
                    f"agent {name}.resume_args must contain {{session_id}}"
                )
        if prompt_transport == "stdin":
            prompt_arg = config.get("prompt_arg")
            if not isinstance(prompt_arg, str) or not prompt_arg:
                raise RuntimeError(
                    f"agent {name}: stdin prompt_transport requires prompt_arg"
                )

    for name, config in routes.items():
        if not isinstance(name, str) or not isinstance(config, dict):
            raise RuntimeError("agent-routing.yaml: invalid route entry")
        agent_name = config.get("agent")
        model = config.get("model")
        if agent_name not in agents:
            raise RuntimeError(f"route {name}: unknown agent {agent_name!r}")
        if not isinstance(model, str) or not model.strip() or "{{" in model:
            raise RuntimeError(f"route {name}: model is unresolved or empty")
        route_args = _require_string_list(config.get("args", []), f"route {name}.args")
        if any("{{" in item for item in route_args):
            raise RuntimeError(f"route {name}: args contain unresolved placeholder")

    return agents, routes


def _resolve_route(route: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    agents, routes = _load_execution_config()
    route_config = routes.get(route)
    if route_config is None:
        available = ", ".join(sorted(routes))
        raise RuntimeError(f"unknown route {route!r}; available routes: {available}")
    agent_name = route_config["agent"]
    return agent_name, agents[agent_name], route_config


def _expand_scalar(raw: str, values: dict[str, str]) -> str:
    expanded = raw
    for key, value in values.items():
        expanded = expanded.replace(f"{{{key}}}", value)
    if PLACEHOLDER_RE.search(expanded):
        raise RuntimeError(f"unresolved execution placeholder in argument: {raw!r}")
    return expanded


def _build_command(
    agent: dict[str, Any],
    route: dict[str, Any],
    session_id: str | None,
    schema_path: Path,
    result_path: Path,
) -> list[str]:
    template_key = "resume_args" if session_id else "start_args"
    template = agent.get(template_key)
    if template is None:
        raise RuntimeError("selected agent does not support native resume")

    route_args = route.get("args", [])
    if route_args and "{route_args}" not in template:
        raise RuntimeError(f"{template_key} does not contain {{route_args}}")

    values = {
        "model": route["model"],
        "schema_path": str(schema_path),
        "result_path": str(result_path),
    }
    if session_id:
        values["session_id"] = session_id

    argv: list[str] = [agent["command"]]
    for item in template:
        if item == "{route_args}":
            argv.extend(_expand_scalar(arg, values) for arg in route_args)
        else:
            argv.append(_expand_scalar(item, values))
    return argv


def _build_prompt(task: str) -> str:
    schema = json.dumps(RESULT_SCHEMA, ensure_ascii=False)
    return f"""You are the execution agent for exactly one Git repository.

Operating contract:
- Work only inside the current Git repository.
- Read and follow the repository's AGENTS.md and repo-local instructions.
- Do not inspect, edit, or operate on sibling repositories or workspace control files.
- Do not spawn or delegate to another coding agent.
- Complete the task independently, including appropriate verification.
- Keep intermediate reasoning and progress inside this child run.
- Final task result must be exactly one JSON object matching this schema: {schema}
- Do not wrap the final JSON object in Markdown fences or add prose around it.
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


def _parse_codex_result(stdout_path: Path, result_path: Path) -> tuple[str, dict[str, Any]]:
    session_id: str | None = None
    for line in stdout_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") in {"thread.started", "thread_started"}:
            candidate = event.get("thread_id") or event.get("threadId")
            if isinstance(candidate, str) and candidate:
                session_id = candidate
                break

    if not session_id:
        raise RuntimeError("Codex run produced no native thread/session id")
    if not result_path.is_file():
        raise RuntimeError("Codex run produced no final result file")

    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Codex final result is invalid JSON") from exc
    return session_id, _validate_result(payload)


def _parse_claude_result(stdout_path: Path) -> tuple[str, dict[str, Any]]:
    try:
        envelope = json.loads(stdout_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Claude output-format json result is invalid JSON") from exc

    if not isinstance(envelope, dict):
        raise RuntimeError("Claude result envelope is not a JSON object")
    if envelope.get("is_error") is True or envelope.get("subtype") not in {None, "success"}:
        raise RuntimeError(
            f"Claude run returned error result: {envelope.get('subtype', 'unknown')}"
        )

    session_id = envelope.get("session_id")
    result_text = envelope.get("result")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("Claude run produced no native session_id")
    if not isinstance(result_text, str):
        raise RuntimeError("Claude run produced no final result text")

    try:
        payload = json.loads(result_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Claude final result text is not the required JSON object") from exc
    return session_id, _validate_result(payload)


def _safe_runner_diagnostic(*paths: Path) -> str | None:
    startup_markers = (
        "unexpected argument",
        "unknown argument",
        "unknown option",
        "unrecognized option",
        "invalid value",
        "permission mode",
        "error loading config",
        "error parsing",
        "usage:",
    )

    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lowered = text.lower()
        if not any(marker in lowered for marker in startup_markers):
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            return " | ".join(lines[-8:])[:2000]
    return None


async def _claim_resources(repo: Path, session_id: str | None) -> None:
    async with _state_lock:
        if repo in _active_repositories:
            raise RuntimeError(
                f"repository already has an active delegation: {repo}"
            )
        if session_id and session_id in _active_sessions:
            raise RuntimeError(
                f"native session already has an active delegation: {session_id}"
            )

        _active_repositories.add(repo)
        if session_id:
            _active_sessions.add(session_id)


async def _release_resources(repo: Path, session_id: str | None) -> None:
    async with _state_lock:
        _active_repositories.discard(repo)
        if session_id:
            _active_sessions.discard(session_id)


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
    route: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Execute one repo-local task synchronously using a configured route.

    `repository` is the exact name from repos.yaml. `route` is the exact route
    name from instructions/agent-routing.yaml. Omit `session_id` to START a new
    native session. Pass a native session id previously returned by this tool to
    RESUME through the selected route. Independent Git roots may execute
    concurrently; within this server process, concurrent calls targeting the same
    Git root or native session are rejected. There is no progress/status API.
    """
    repository = repository.strip()
    task = task.strip()
    route = route.strip()
    session_id = session_id.strip() if isinstance(session_id, str) else None

    if not repository:
        raise ValueError("repository must not be empty")
    if not task:
        raise ValueError("task must not be empty")
    if not route:
        raise ValueError("route must not be empty")
    if session_id == "":
        session_id = None
    if len(task) > 100_000:
        raise ValueError("task is too large")

    repo = _resolve_repo(repository)
    agent_name, agent, route_config = _resolve_route(route)
    command_name = agent["command"]
    if shutil.which(command_name) is None:
        raise RuntimeError(f"missing execution agent CLI: {command_name}")

    await _claim_resources(repo, session_id)
    try:
        run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        started = time.monotonic()

        with tempfile.TemporaryDirectory(prefix="qiqi-delegate-") as temp_dir:
            temp = Path(temp_dir)
            schema_path = temp / "result.schema.json"
            result_path = temp / "result.json"
            stdout_path = temp / "stdout.log"
            stderr_path = temp / "stderr.log"
            schema_path.write_text(
                json.dumps(RESULT_SCHEMA, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            command = _build_command(
                agent, route_config, session_id, schema_path, result_path
            )
            prompt = _build_prompt(task)
            prompt_transport = agent["prompt_transport"]
            if prompt_transport == "stdin":
                command.append(agent["prompt_arg"])
                stdin_mode = asyncio.subprocess.PIPE
                stdin_payload: bytes | None = prompt.encode("utf-8")
            else:
                command.append(prompt)
                stdin_mode = asyncio.subprocess.DEVNULL
                stdin_payload = None

            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(repo),
                    stdin=stdin_mode,
                    stdout=stdout,
                    stderr=stderr,
                )
                try:
                    if stdin_payload is None:
                        await proc.wait()
                    else:
                        await proc.communicate(stdin_payload)
                except asyncio.CancelledError:
                    await _terminate(proc)
                    raise

            if proc.returncode != 0:
                diagnostic = _safe_runner_diagnostic(stderr_path, stdout_path)
                detail = (
                    f"; runner diagnostic: {diagnostic}"
                    if diagnostic
                    else "; child output is intentionally not exposed to QiQi"
                )
                raise RuntimeError(
                    f"child {agent_name} run failed (run_id={run_id}, "
                    f"exit={proc.returncode}){detail}"
                )

            adapter = agent["adapter"]
            if adapter == "codex":
                native_session_id, result = _parse_codex_result(
                    stdout_path, result_path
                )
            elif adapter == "claude":
                native_session_id, result = _parse_claude_result(stdout_path)
            else:  # guarded by config validation
                raise RuntimeError(f"unsupported adapter: {adapter}")

            if session_id and native_session_id != session_id:
                raise RuntimeError(
                    "resume identity mismatch: runner did not return the requested "
                    f"native session id {session_id!r}"
                )

        duration = round(time.monotonic() - started, 2)
        return {
            "run_id": run_id,
            "repository": repository,
            "agent": agent_name,
            "route": route,
            "model": route_config["model"],
            "session_id": native_session_id,
            "duration_seconds": duration,
            **result,
        }
    finally:
        await _release_resources(repo, session_id)


if __name__ == "__main__":
    mcp.run()
