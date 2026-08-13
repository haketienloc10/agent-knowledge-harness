#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
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
HERDR_BIN = os.environ.get("QIQI_HERDR_BIN", "herdr")
HERDR_SESSION = os.environ.get("QIQI_HERDR_SESSION", "qiqi-delegate").strip() or "qiqi-delegate"
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
        "Synchronous Herdr-backed execution boundary for QiQi. Use "
        "delegate_repo_task for repo-local work. QiQi selects a route and may "
        "optionally pass the native Codex/Claude session_id to RESUME; omitting "
        "session_id always STARTs a new native session. The MCP server owns "
        "Herdr workspace lifecycle, CLI construction, waiting, native session-id "
        "extraction, result normalization, and cleanup. There are intentionally "
        "no status, wait, read, list-runs, transcript, or separate resume tools."
    ),
)

_herdr_server_lock = asyncio.Lock()
_managed_herdr_server: asyncio.subprocess.Process | None = None
_repo_locks: dict[str, asyncio.Lock] = {}


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
- If a user/product decision or unavailable dependency prevents completion, set outcome to "blocked" and explain it in blockers.

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


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


async def _communicate(
    proc: asyncio.subprocess.Process,
    input_data: bytes | None = None,
) -> tuple[bytes, bytes]:
    try:
        return await proc.communicate(input_data)
    except asyncio.CancelledError:
        await _terminate(proc)
        raise


def _herdr_argv(*args: str) -> list[str]:
    return [HERDR_BIN, "--session", HERDR_SESSION, *args]


async def _run_herdr(*args: str, check: bool = True) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *_herdr_argv(*args),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await _communicate(proc)
    out_text = stdout.decode("utf-8", errors="replace")
    err_text = stderr.decode("utf-8", errors="replace")
    if check and proc.returncode != 0:
        detail = (err_text or out_text).strip()
        if len(detail) > 2000:
            detail = detail[-2000:]
        raise RuntimeError(
            f"Herdr command failed (exit={proc.returncode}): "
            f"{' '.join(args)}{f'; {detail}' if detail else ''}"
        )
    return proc.returncode or 0, out_text, err_text


async def _run_herdr_json(*args: str) -> dict[str, Any]:
    _, stdout, _ = await _run_herdr(*args)
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Herdr command returned invalid JSON: {' '.join(args)}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Herdr command returned non-object JSON: {' '.join(args)}")
    return payload


async def _herdr_server_running() -> bool:
    returncode, _, _ = await _run_herdr("status", "server", check=False)
    return returncode == 0


async def _ensure_herdr_server() -> None:
    global _managed_herdr_server

    if shutil.which(HERDR_BIN) is None:
        raise RuntimeError(f"missing Herdr CLI: {HERDR_BIN}")

    if await _herdr_server_running():
        return

    async with _herdr_server_lock:
        if await _herdr_server_running():
            return

        _managed_herdr_server = await asyncio.create_subprocess_exec(
            *_herdr_argv("server"),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if await _herdr_server_running():
                return
            if _managed_herdr_server.returncode is not None:
                break
            await asyncio.sleep(0.1)

        if _managed_herdr_server.returncode is None:
            await _terminate(_managed_herdr_server)
        raise RuntimeError(
            f"failed to start Herdr named session {HERDR_SESSION!r}"
        )


async def _create_herdr_workspace(repo: Path, label: str) -> tuple[str, str]:
    payload = await _run_herdr_json(
        "workspace",
        "create",
        "--cwd",
        str(repo),
        "--label",
        label,
        "--no-focus",
    )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Herdr workspace create returned no result")
    workspace = result.get("workspace")
    root_pane = result.get("root_pane")
    if not isinstance(workspace, dict) or not isinstance(root_pane, dict):
        raise RuntimeError("Herdr workspace create returned incomplete topology")

    workspace_id = workspace.get("workspace_id")
    pane_id = root_pane.get("pane_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise RuntimeError("Herdr workspace create returned no workspace_id")
    if not isinstance(pane_id, str) or not pane_id:
        raise RuntimeError("Herdr workspace create returned no root pane_id")
    return workspace_id, pane_id


async def _close_herdr_workspace(workspace_id: str) -> None:
    try:
        await _run_herdr("workspace", "close", workspace_id)
    except Exception:
        # Cleanup must not replace the delegation result/error.
        pass


def _write_runner(
    run_dir: Path,
    command: list[str],
    prompt: str,
    prompt_transport: str,
    repo: Path,
    stdout_path: Path,
    stderr_path: Path,
    exit_path: Path,
    sentinel: str,
) -> Path:
    command_path = run_dir / "command.json"
    prompt_path = run_dir / "prompt.txt"
    spec_path = run_dir / "runner-spec.json"
    runner_path = run_dir / "runner.py"

    command_path.write_text(
        json.dumps(command, ensure_ascii=False),
        encoding="utf-8",
    )
    prompt_path.write_text(prompt, encoding="utf-8")
    spec_path.write_text(
        json.dumps(
            {
                "command_path": str(command_path),
                "prompt_path": str(prompt_path),
                "prompt_transport": prompt_transport,
                "cwd": str(repo),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "exit_path": str(exit_path),
                "sentinel": sentinel,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runner_path.write_text(
        """#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
spec = json.loads((root / "runner-spec.json").read_text(encoding="utf-8"))
argv = json.loads(Path(spec["command_path"]).read_text(encoding="utf-8"))
prompt = Path(spec["prompt_path"]).read_bytes()

returncode = 127
runner_error = None
try:
    with open(spec["stdout_path"], "wb") as stdout, open(spec["stderr_path"], "wb") as stderr:
        if spec["prompt_transport"] == "stdin":
            completed = subprocess.run(
                argv,
                cwd=spec["cwd"],
                input=prompt,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        else:
            completed = subprocess.run(
                argv,
                cwd=spec["cwd"],
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
    returncode = completed.returncode
except BaseException as exc:
    runner_error = f"{type(exc).__name__}: {exc}"
finally:
    Path(spec["exit_path"]).write_text(
        json.dumps({"returncode": returncode, "runner_error": runner_error}),
        encoding="utf-8",
    )
    print(spec["sentinel"], flush=True)
""",
        encoding="utf-8",
    )
    return runner_path


async def _run_in_herdr(
    pane_id: str,
    runner_path: Path,
    sentinel: str,
) -> None:
    launcher = shlex.join([sys.executable, "-u", str(runner_path)])
    await _run_herdr("pane", "run", pane_id, launcher)
    await _run_herdr(
        "pane",
        "wait-output",
        pane_id,
        "--match",
        sentinel,
        "--source",
        "recent-unwrapped",
        "--lines",
        "80",
    )


def _read_runner_exit(exit_path: Path) -> tuple[int, str | None]:
    if not exit_path.is_file():
        raise RuntimeError("Herdr runner produced no exit metadata")
    try:
        payload = json.loads(exit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Herdr runner exit metadata is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Herdr runner exit metadata is invalid")
    returncode = payload.get("returncode")
    runner_error = payload.get("runner_error")
    if not isinstance(returncode, int):
        raise RuntimeError("Herdr runner exit metadata has no return code")
    if runner_error is not None and not isinstance(runner_error, str):
        runner_error = str(runner_error)
    return returncode, runner_error


def _repo_lock(repo: Path) -> asyncio.Lock:
    key = str(repo)
    lock = _repo_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _repo_locks[key] = lock
    return lock


@mcp.tool()
async def delegate_repo_task(
    repository: str,
    task: str,
    route: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Execute one repo-local task synchronously through Herdr.

    `repository` is the exact name from repos.yaml. `route` is the exact route
    name from instructions/agent-routing.yaml. Omit `session_id` to START a new
    native session. Pass a native session id previously returned by this tool to
    RESUME through the selected route. The call stays open until the child run
    completes or fails; there is no progress/status API.
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

    await _ensure_herdr_server()

    async with _repo_lock(repo):
        run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        run_dir = Path(tempfile.mkdtemp(prefix=f"qiqi-delegate-{run_id}-"))
        workspace_id: str | None = None

        try:
            schema_path = run_dir / "result.schema.json"
            result_path = run_dir / "result.json"
            stdout_path = run_dir / "stdout.log"
            stderr_path = run_dir / "stderr.log"
            exit_path = run_dir / "exit.json"
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
            else:
                command.append(prompt)

            label = f"qiqi:{repository}:{run_id[-8:]}"
            workspace_id, pane_id = await _create_herdr_workspace(repo, label)

            sentinel = f"__QIQI_DELEGATE_DONE_{uuid.uuid4().hex}__"
            runner_path = _write_runner(
                run_dir=run_dir,
                command=command,
                prompt=prompt,
                prompt_transport=prompt_transport,
                repo=repo,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                exit_path=exit_path,
                sentinel=sentinel,
            )

            await _run_in_herdr(pane_id, runner_path, sentinel)

            returncode, runner_error = _read_runner_exit(exit_path)
            if returncode != 0:
                diagnostic = _safe_runner_diagnostic(stderr_path, stdout_path)
                detail = (
                    f"; runner diagnostic: {diagnostic}"
                    if diagnostic
                    else "; child output is intentionally not exposed to QiQi"
                )
                if runner_error:
                    detail += f"; runner error: {runner_error[:1000]}"
                raise RuntimeError(
                    f"child {agent_name} run failed (exit={returncode}){detail}"
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

            return {
                "session_id": native_session_id,
                **result,
            }
        finally:
            if workspace_id:
                await _close_herdr_workspace(workspace_id)
            shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    mcp.run()
