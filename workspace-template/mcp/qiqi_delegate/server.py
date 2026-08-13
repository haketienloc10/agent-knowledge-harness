#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any

import yaml
from mcp.server import MCPServer

_workspace_root_env = os.environ.get("QIQI_WORKSPACE_ROOT")
WORKSPACE_ROOT = (
    Path(_workspace_root_env).resolve()
    if _workspace_root_env
    else Path(__file__).resolve().parents[2]
)
ROUTING_PATH = WORKSPACE_ROOT / "instructions" / "agent-routing.yaml"
RUNS_DIR = WORKSPACE_ROOT / ".qiqi" / "runs"
HERDR_BIN = os.environ.get("QIQI_HERDR_BIN", "herdr")
HERDR_SESSION = (
    os.environ.get("QIQI_HERDR_SESSION", "qiqi-delegate").strip() or "qiqi-delegate"
)
HERDR_AGENT_START_TIMEOUT_MS = 60_000
HERDR_SHELL_READY_TIMEOUT_SECONDS = 10.0
NATIVE_SESSION_WAIT_SECONDS = 15.0
CLAUDE_PROMPT_RETRY_EFFECT_SECONDS = 5.0
SUPPORTED_ADAPTERS = {"codex", "claude"}
PLACEHOLDER_RE = re.compile(r"\{[a-z_][a-z0-9_]*\}")
TURN_MARKER_RE = re.compile(r"<!-- qiqi-turn:(\d+) -->")
REQUIRED_RESULT_HEADINGS = (
    "Outcome",
    "Changes",
    "Verification",
    "Git State",
    "Blockers",
    "Repo-local Knowledge",
    "Cross-repo Impact",
)
META_PREFIX = "<!-- qiqi-session: "
META_SUFFIX = " -->"

mcp = MCPServer(
    "QiQi Delegate",
    instructions=(
        "Synchronous Herdr-backed interactive execution boundary for QiQi. Use "
        "delegate_repo_task for repo-local work. QiQi selects a route and may "
        "optionally pass the native Codex/Claude session_id to RESUME; omitting "
        "session_id always STARTs a new native session. The MCP server owns the "
        "Herdr workspace and interactive agent lifecycle, route argument "
        "construction, prompt/wait, native session identity, and the durable "
        ".qiqi/runs Markdown result artifact. START creates one result artifact; "
        "RESUME appends to the exact artifact for that native session. The call "
        "returns only after the interactive turn settles. There are intentionally "
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
        if not isinstance(command, str) or not command.strip():
            raise RuntimeError(f"agent {name}: command must be a non-empty string")
        if adapter not in SUPPORTED_ADAPTERS:
            raise RuntimeError(
                f"agent {name}: unsupported adapter {adapter!r}; "
                f"supported: {', '.join(sorted(SUPPORTED_ADAPTERS))}"
            )

        start_args = _require_string_list(
            config.get("start_args"), f"agent {name}.start_args"
        )
        resume_args = _require_string_list(
            config.get("resume_args"), f"agent {name}.resume_args"
        )
        if any("{session_id}" in item for item in start_args):
            raise RuntimeError(
                f"agent {name}.start_args must not contain {{session_id}}"
            )
        if not any("{session_id}" in item for item in resume_args):
            raise RuntimeError(
                f"agent {name}.resume_args must contain {{session_id}}"
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
        route_args = _require_string_list(
            config.get("args", []), f"route {name}.args"
        )
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


def _build_interactive_args(
    agent: dict[str, Any],
    route: dict[str, Any],
    session_id: str | None,
) -> list[str]:
    template_key = "resume_args" if session_id else "start_args"
    template = agent[template_key]
    route_args = route.get("args", [])
    if route_args and "{route_args}" not in template:
        raise RuntimeError(f"{template_key} does not contain {{route_args}}")

    values = {
        "model": route["model"],
        "result_dir": str(RUNS_DIR),
    }
    if session_id:
        values["session_id"] = session_id

    argv: list[str] = []
    for item in template:
        if item == "{route_args}":
            argv.extend(_expand_scalar(arg, values) for arg in route_args)
        else:
            argv.append(_expand_scalar(item, values))
    return argv


def _ascii_slug(value: str, *, max_length: int, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if not slug:
        slug = fallback
    slug = slug[:max_length].rstrip("-")
    return slug or fallback


def _session_filename_component(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", session_id).strip(".-_")
    changed = safe != session_id
    if not safe:
        safe = "session"
        changed = True
    if len(safe) > 120:
        safe = safe[:120].rstrip(".-_")
        changed = True
    if changed:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8]
        base = safe[:111].rstrip(".-_") or "session"
        safe = f"{base}-{digest}"
    return safe


def _repo_filename_component(repository: str) -> str:
    return _ascii_slug(repository, max_length=40, fallback="repo")


def _task_slug(task: str) -> str:
    first_line = next((line.strip() for line in task.splitlines() if line.strip()), task)
    return _ascii_slug(first_line, max_length=48, fallback="task")


def _artifact_header(
    repository: str,
    agent_name: str,
    session_id: str | None,
    task: str,
) -> str:
    metadata = {
        "repository": repository,
        "agent": agent_name,
        "session_id": session_id,
    }
    title = next((line.strip() for line in task.splitlines() if line.strip()), "Task")[:120]
    session_display = session_id or "pending"
    return (
        f"{META_PREFIX}{json.dumps(metadata, ensure_ascii=False)}{META_SUFFIX}\n"
        f"# {title}\n\n"
        f"- Repository: `{repository}`\n"
        f"- Agent: `{agent_name}`\n"
        f"- Native session: `{session_display}`\n"
    )


def _create_pending_result_artifact(
    repository: str,
    agent_name: str,
    task: str,
) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / (
        f".pending-{_repo_filename_component(repository)}-{_task_slug(task)}-"
        f"{uuid.uuid4().hex[:12]}.md"
    )
    path.write_text(
        _artifact_header(repository, agent_name, None, task),
        encoding="utf-8",
    )
    return path


def _final_result_path(repository: str, task: str, session_id: str) -> Path:
    return RUNS_DIR / (
        f"{_repo_filename_component(repository)}-{_task_slug(task)}-"
        f"{_session_filename_component(session_id)}.md"
    )


def _promote_start_artifact(
    path: Path,
    repository: str,
    agent_name: str,
    task: str,
    session_id: str,
) -> Path:
    destination = _final_result_path(repository, task, session_id)
    if destination.exists():
        raise RuntimeError(
            f"new native session would overwrite existing result artifact: {destination}"
        )

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines:
        raise RuntimeError(f"pending result artifact is empty: {path}")
    lines[0] = (
        f"{META_PREFIX}"
        f"{json.dumps({'repository': repository, 'agent': agent_name, 'session_id': session_id}, ensure_ascii=False)}"
        f"{META_SUFFIX}\n"
    )

    native_line = None
    for index, line in enumerate(lines):
        if line.startswith("- Native session: "):
            native_line = index
            break
    if native_line is None:
        raise RuntimeError(f"pending result artifact lost native-session header: {path}")
    lines[native_line] = f"- Native session: `{session_id}`\n"
    path.write_text("".join(lines), encoding="utf-8")
    path.replace(destination)
    return destination


def _artifact_metadata(path: Path) -> dict[str, Any]:
    try:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError) as exc:
        raise RuntimeError(f"invalid result artifact: {path}") from exc
    if not first_line.startswith(META_PREFIX) or not first_line.endswith(META_SUFFIX):
        raise RuntimeError(f"result artifact is missing QiQi session metadata: {path}")
    raw = first_line[len(META_PREFIX) : -len(META_SUFFIX)]
    try:
        metadata = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"result artifact has invalid QiQi metadata: {path}") from exc
    if not isinstance(metadata, dict):
        raise RuntimeError(f"result artifact has invalid QiQi metadata: {path}")
    return metadata


def _find_resume_artifact(
    repository: str,
    agent_name: str,
    session_id: str,
) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    repo_part = _repo_filename_component(repository)
    session_part = _session_filename_component(session_id)
    prefix = f"{repo_part}-"
    suffix = f"-{session_part}.md"

    candidates = sorted(
        path
        for path in RUNS_DIR.iterdir()
        if path.is_file()
        and not path.name.startswith(".pending-")
        and path.name.startswith(prefix)
        and path.name.endswith(suffix)
    )
    exact: list[Path] = []
    for path in candidates:
        metadata = _artifact_metadata(path)
        if (
            metadata.get("repository") == repository
            and metadata.get("session_id") == session_id
        ):
            exact.append(path)

    if not exact:
        raise RuntimeError(
            "resume requires the existing Markdown result artifact for this "
            f"repository/session; none found under {RUNS_DIR}"
        )
    if len(exact) != 1:
        raise RuntimeError(
            "resume result artifact is ambiguous for "
            f"repository={repository!r}, session_id={session_id!r}: "
            + ", ".join(str(path) for path in exact)
        )

    metadata = _artifact_metadata(exact[0])
    previous_agent = metadata.get("agent")
    if previous_agent != agent_name:
        raise RuntimeError(
            "cross-agent resume is not allowed: session artifact belongs to "
            f"{previous_agent!r}, selected route uses {agent_name!r}"
        )
    return exact[0]


def _append_task_section(path: Path, task: str) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    numbers = [int(match) for match in TURN_MARKER_RE.findall(text)]
    turn = max(numbers, default=0) + 1
    marker = f"<!-- QIQI_RESULT_PENDING:{turn}:{uuid.uuid4().hex[:8]} -->"

    separator = "" if text.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"{separator}\n<!-- qiqi-turn:{turn} -->\n## Task {turn}\n\n"
            f"{task}\n\n"
            f"## Result {turn}\n\n"
            f"{marker}\n"
        )

    appended = path.read_text(encoding="utf-8")
    if appended.count(marker) != 1:
        raise RuntimeError("failed to create a unique pending result marker")
    expected_prefix, _ = appended.split(marker, 1)
    return marker, expected_prefix


def _build_prompt(task: str, result_path: Path, marker: str) -> str:
    return f"""You are the execution agent for exactly one Git repository.

Operating contract:
- Work only inside the current Git repository.
- Read and follow the repository's AGENTS.md and repo-local instructions.
- Do not inspect, edit, or operate on sibling repositories or workspace control files.
- The only path outside the repository that you may edit is the exact result artifact below.
- Do not spawn or delegate to another coding agent.
- Complete the task independently, including appropriate verification.
- Keep intermediate reasoning and progress in this interactive agent session; do not write chain-of-thought to the result artifact.
- Keep the interactive agent process alive and ready for another prompt after this turn.

Result artifact contract:
- Result artifact: {result_path}
- Preserve all existing content in that Markdown file.
- Find this exact pending marker under the newest Result section:
  {marker}
- Before this turn settles, replace that marker with concise Markdown containing:
  `### Outcome` with `completed` or `blocked`;
  `### Changes`;
  `### Verification`;
  `### Git State`;
  `### Blockers`;
  `### Repo-local Knowledge`;
  `### Cross-repo Impact`.
- Use `None.` for an empty prose section or a short bullet list when appropriate.
- If a user/product decision or unavailable dependency prevents completion, write the blocker to the artifact with Outcome `blocked` before presenting the interactive question/blocker.

Task:
{task}
"""


def _result_fallback_blocked(reason: str) -> str:
    return f"""### Outcome

blocked

### Changes

None.

### Verification

None.

### Git State

Not finalized.

### Blockers

- {reason}

### Repo-local Knowledge

None.

### Cross-repo Impact

None.
""".rstrip()


def _validate_result_section(text: str, expected_prefix: str, status: str) -> None:
    if not text.startswith(expected_prefix):
        raise RuntimeError(
            "interactive agent modified existing result history instead of only "
            "finalizing the newest Result section"
        )

    result_text = text[len(expected_prefix) :].strip()
    if not result_text:
        raise RuntimeError("interactive agent produced an empty Markdown result section")

    positions: list[int] = []
    for heading in REQUIRED_RESULT_HEADINGS:
        match = re.search(rf"(?m)^### {re.escape(heading)}\s*$", result_text)
        if match is None:
            raise RuntimeError(
                f"interactive agent result is missing required heading: ### {heading}"
            )
        positions.append(match.start())
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise RuntimeError("interactive agent result headings are out of required order")

    outcome_match = re.search(
        r"(?ms)^### Outcome\s*$\s*(.*?)(?=^### |\Z)",
        result_text,
    )
    if outcome_match is None:
        raise RuntimeError("interactive agent result has no Outcome value")
    outcome_lines = [
        line.strip() for line in outcome_match.group(1).splitlines() if line.strip()
    ]
    if not outcome_lines:
        raise RuntimeError("interactive agent result has an empty Outcome value")
    outcome = outcome_lines[0].strip("`").lower()
    if outcome not in {"completed", "blocked"}:
        raise RuntimeError(
            "interactive agent result Outcome must be exactly completed or blocked"
        )
    if status == "blocked" and outcome != "blocked":
        raise RuntimeError(
            "Herdr reported the agent as blocked but the Markdown result did not"
        )


def _finalize_artifact_after_wait(
    path: Path,
    marker: str,
    expected_prefix: str,
    status: str,
) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        if status != "blocked":
            raise RuntimeError(
                "interactive agent settled without finalizing its Markdown result artifact"
            )
        fallback = _result_fallback_blocked(
            "Herdr reported the interactive agent as blocked before it finalized "
            "this result section. Resume the same native session with the required "
            "answer or decision."
        )
        text = text.replace(marker, fallback, 1)
        path.write_text(text, encoding="utf-8")

    if marker in text:
        raise RuntimeError("pending result marker remains after finalization")
    _validate_result_section(text, expected_prefix, status)


def _mark_artifact_execution_error(
    path: Path | None,
    marker: str | None,
    expected_prefix: str | None,
    exc: BaseException,
) -> None:
    if path is None or marker is None or expected_prefix is None or not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
        if not text.startswith(expected_prefix) or marker not in text:
            return
        message = " ".join(str(exc).split())[:800] or type(exc).__name__
        fallback = _result_fallback_blocked(
            f"Delegation infrastructure failed before the agent finalized this turn: {message}"
        )
        path.write_text(text.replace(marker, fallback, 1), encoding="utf-8")
    except OSError:
        pass


def _result_relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"result artifact escaped workspace root: {path}") from exc


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
        if len(detail) > 3000:
            detail = detail[-3000:]
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
        raise RuntimeError(f"failed to start Herdr named session {HERDR_SESSION!r}")


async def _require_current_integration(adapter: str) -> None:
    _, stdout, _ = await _run_herdr("integration", "status")
    current = re.compile(rf"^{re.escape(adapter)}:\s+current\b")
    if any(current.search(line) for line in stdout.splitlines()):
        return
    raise RuntimeError(
        f"Herdr {adapter} integration is not current; run "
        f"`herdr integration install {adapter}` before using interactive delegation"
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
        pass


def _agent_from_payload(payload: dict[str, Any], context: str) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"Herdr {context} returned no result")
    agent = result.get("agent")
    if not isinstance(agent, dict):
        raise RuntimeError(f"Herdr {context} returned no agent")
    return agent


def _herdr_json_payload(stdout: str, stderr: str) -> dict[str, Any] | None:
    for text in (stdout, stderr):
        stripped = text.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _herdr_error_code(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


async def _start_interactive_agent(
    pane_id: str,
    adapter: str,
    agent_args: list[str],
) -> tuple[str, dict[str, Any]]:
    name = f"qiqi-{uuid.uuid4().hex[:12]}"
    command = [
        "agent",
        "start",
        name,
        "--kind",
        adapter,
        "--pane",
        pane_id,
        "--timeout",
        str(HERDR_AGENT_START_TIMEOUT_MS),
    ]
    if agent_args:
        command.extend(["--", *agent_args])

    deadline = time.monotonic() + HERDR_SHELL_READY_TIMEOUT_SECONDS
    last_detail = ""
    while True:
        returncode, stdout, stderr = await _run_herdr(*command, check=False)
        detail = (stderr or stdout).strip()
        last_detail = detail or last_detail
        payload = _herdr_json_payload(stdout, stderr)

        if returncode == 0:
            if payload is None:
                raise RuntimeError(
                    f"Herdr agent start returned invalid JSON: {' '.join(command)}"
                )
            return name, _agent_from_payload(payload, "agent start")

        if _herdr_error_code(payload) != "agent_pane_busy":
            if len(detail) > 3000:
                detail = detail[-3000:]
            raise RuntimeError(
                f"Herdr command failed (exit={returncode}): "
                f"{' '.join(command)}{f'; {detail}' if detail else ''}"
            )

        if time.monotonic() >= deadline:
            if len(last_detail) > 2000:
                last_detail = last_detail[-2000:]
            raise RuntimeError(
                f"Herdr root pane {pane_id} did not become an available shell "
                f"within {HERDR_SHELL_READY_TIMEOUT_SECONDS:g}s"
                f"{f'; last error: {last_detail}' if last_detail else ''}"
            )
        await asyncio.sleep(0.1)


async def _get_agent(name: str) -> dict[str, Any]:
    payload = await _run_herdr_json("agent", "get", name)
    return _agent_from_payload(payload, "agent get")


def _extract_native_session(agent: dict[str, Any], adapter: str) -> str | None:
    detected = agent.get("agent")
    if detected is not None and detected != adapter:
        raise RuntimeError(f"Herdr detected agent {detected!r}, expected {adapter!r}")

    session = agent.get("agent_session")
    if session is None:
        return None
    if not isinstance(session, dict):
        raise RuntimeError("Herdr agent_session is malformed")
    if session.get("agent") != adapter:
        raise RuntimeError(
            "Herdr native session identity belongs to a different agent: "
            f"{session.get('agent')!r}"
        )
    if session.get("kind") != "id":
        raise RuntimeError(
            f"Herdr returned unsupported native session reference kind: {session.get('kind')!r}"
        )
    value = session.get("value")
    if not isinstance(value, str) or not value:
        raise RuntimeError("Herdr native session identity has no value")
    return value


def _validate_reported_session_if_present(
    agent: dict[str, Any],
    adapter: str,
    expected_session_id: str | None,
) -> str | None:
    native_session_id = _extract_native_session(agent, adapter)
    if (
        native_session_id is not None
        and expected_session_id is not None
        and native_session_id != expected_session_id
    ):
        raise RuntimeError(
            "resume identity mismatch: interactive agent reported "
            f"{native_session_id!r}, requested {expected_session_id!r}"
        )
    return native_session_id


async def _wait_for_native_session(
    name: str,
    adapter: str,
    initial_agent: dict[str, Any],
    expected_session_id: str | None,
) -> str:
    agent = initial_agent
    deadline = time.monotonic() + NATIVE_SESSION_WAIT_SECONDS
    while True:
        native_session_id = _validate_reported_session_if_present(
            agent,
            adapter,
            expected_session_id,
        )
        if native_session_id:
            return native_session_id
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Herdr did not receive native {adapter} session identity after "
                "the interactive turn started; verify the current Herdr integration "
                "is loaded by the agent process"
            )
        await asyncio.sleep(0.1)
        agent = await _get_agent(name)


async def _wait_for_claude_enter_recovery(
    name: str,
    baseline_agent: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    baseline_status = baseline_agent.get("agent_status")
    baseline_seq = baseline_agent.get("state_change_seq")
    activity_deadline = time.monotonic() + CLAUDE_PROMPT_RETRY_EFFECT_SECONDS
    saw_activity = False

    while True:
        agent = await _get_agent(name)
        status = agent.get("agent_status")
        state_change_seq = agent.get("state_change_seq")

        if not saw_activity:
            seq_advanced = (
                isinstance(baseline_seq, int)
                and isinstance(state_change_seq, int)
                and state_change_seq > baseline_seq
            )
            saw_activity = (
                status == "working"
                or status != baseline_status
                or seq_advanced
            )
            if not saw_activity and time.monotonic() >= activity_deadline:
                raise RuntimeError(
                    "Claude prompt remained stalled after one Enter recovery; "
                    "the prompt was not submitted"
                )

        if saw_activity and status in {"idle", "done", "blocked"}:
            return status, agent
        await asyncio.sleep(0.1)


async def _wait_for_agent_settled(
    name: str,
    initial_agent: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    agent = initial_agent
    while True:
        status = agent.get("agent_status")
        if status in {"idle", "done", "blocked"}:
            return status, agent
        await asyncio.sleep(0.1)
        agent = await _get_agent(name)


async def _prompt_and_wait(
    name: str,
    prompt: str,
    adapter: str,
) -> tuple[str, dict[str, Any]]:
    command = ["agent", "prompt", name, prompt, "--wait"]
    returncode, stdout, stderr = await _run_herdr(*command, check=False)
    payload = _herdr_json_payload(stdout, stderr)

    if returncode != 0:
        error_code = _herdr_error_code(payload)
        if adapter == "claude" and error_code == "agent_prompt_stalled":
            stalled_agent = await _get_agent(name)
            stalled_status = stalled_agent.get("agent_status")

            # The 5-second Herdr activity gate can race with Claude beginning the
            # turn. Do not press Enter if the agent has already started or settled.
            if stalled_status == "working":
                return await _wait_for_agent_settled(name, stalled_agent)
            if stalled_status in {"done", "blocked"}:
                return stalled_status, stalled_agent
            if stalled_status != "idle":
                raise RuntimeError(
                    "Claude prompt stalled in an unexpected agent state: "
                    f"{stalled_status!r}"
                )

            # Claude can leave a large bracketed-paste prompt in its composer
            # without accepting the Enter that Herdr appended. Recover exactly
            # once by sending only Enter; never paste the prompt a second time.
            await _run_herdr("agent", "send-keys", name, "enter")
            return await _wait_for_claude_enter_recovery(name, stalled_agent)

        detail = (stderr or stdout).strip()
        if len(detail) > 3000:
            detail = detail[-3000:]
        raise RuntimeError(
            f"Herdr command failed (exit={returncode}): "
            f"{' '.join(command)}{f'; {detail}' if detail else ''}"
        )

    if payload is None:
        raise RuntimeError(
            f"Herdr agent prompt returned invalid JSON: {' '.join(command)}"
        )
    agent = _agent_from_payload(payload, "agent prompt")
    status = agent.get("agent_status")
    if status not in {"idle", "done", "blocked"}:
        raise RuntimeError(
            f"Herdr agent prompt settled with unexpected status: {status!r}"
        )
    return status, agent


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
    """Execute one repo-local task synchronously in a Herdr interactive agent.

    `repository` is the exact name from repos.yaml. `route` is the exact route
    name from instructions/agent-routing.yaml. Omit `session_id` to START a new
    native interactive session. Pass a native session id previously returned by
    this tool to RESUME exactly that session. Each native session owns one
    `.qiqi/runs/<repo>-<task-slug>-<session-id>.md` result artifact; RESUME
    appends the next task/result section to the same file. The call stays open
    until Herdr reports the interactive turn as idle, done, or blocked.
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
    adapter = agent["adapter"]

    command_name = agent["command"]
    if shutil.which(command_name) is None:
        raise RuntimeError(f"missing execution agent CLI: {command_name}")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    if not RUNS_DIR.is_dir():
        raise RuntimeError(f"could not create QiQi runs directory: {RUNS_DIR}")

    await _ensure_herdr_server()
    await _require_current_integration(adapter)

    async with _repo_lock(repo):
        starting_new = session_id is None
        result_path: Path | None = None
        if session_id:
            result_path = _find_resume_artifact(repository, agent_name, session_id)

        workspace_id: str | None = None
        marker: str | None = None
        expected_prefix: str | None = None
        pending_start_path: Path | None = None
        promoted_start = False
        try:
            label = f"qiqi:{repository}:{uuid.uuid4().hex[:8]}"
            workspace_id, pane_id = await _create_herdr_workspace(repo, label)

            interactive_args = _build_interactive_args(
                agent,
                route_config,
                session_id,
            )
            managed_name, started_agent = await _start_interactive_agent(
                pane_id,
                adapter,
                interactive_args,
            )
            _validate_reported_session_if_present(
                started_agent,
                adapter,
                session_id,
            )

            if starting_new:
                pending_start_path = _create_pending_result_artifact(
                    repository,
                    agent_name,
                    task,
                )
                result_path = pending_start_path

            if result_path is None:
                raise RuntimeError("delegation result artifact was not resolved")

            marker, expected_prefix = _append_task_section(result_path, task)
            prompt = _build_prompt(task, result_path, marker)

            # SessionStart hooks for interactive agents can be dispatched only once
            # a real turn begins. Therefore START must prompt first, then read the
            # native session identity. RESUME follows the same post-turn validation
            # while still launching the exact requested native session.
            status, prompted_agent = await _prompt_and_wait(
                managed_name,
                prompt,
                adapter,
            )
            native_session_id = await _wait_for_native_session(
                managed_name,
                adapter,
                prompted_agent,
                session_id,
            )

            _finalize_artifact_after_wait(
                result_path,
                marker,
                expected_prefix,
                status,
            )

            if starting_new:
                result_path = _promote_start_artifact(
                    result_path,
                    repository,
                    agent_name,
                    task,
                    native_session_id,
                )
                promoted_start = True

            return {
                "session_id": native_session_id,
                "result_path": _result_relative_path(result_path),
            }
        except BaseException as exc:
            _mark_artifact_execution_error(
                result_path,
                marker,
                expected_prefix,
                exc,
            )
            raise
        finally:
            if workspace_id:
                await _close_herdr_workspace(workspace_id)
            if (
                starting_new
                and not promoted_start
                and pending_start_path is not None
                and pending_start_path.exists()
            ):
                try:
                    pending_start_path.unlink()
                except OSError:
                    pass


if __name__ == "__main__":
    mcp.run()
