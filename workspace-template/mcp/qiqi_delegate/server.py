#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
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

from core import (
    SessionStore,
    TaskPacket,
    build_task_packet,
    load_capture_events,
    new_turn_id,
    render_task_prompt,
    select_capture_event,
)

_workspace_root_env = os.environ.get("QIQI_WORKSPACE_ROOT")
WORKSPACE_ROOT = (
    Path(_workspace_root_env).resolve()
    if _workspace_root_env
    else Path(__file__).resolve().parents[2]
)
ROUTING_PATH = WORKSPACE_ROOT / "instructions" / "agent-routing.yaml"
STATE_DB = WORKSPACE_ROOT / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
ACTIVE_CAPTURES_DIR = STATE_DB.parent / "active-captures"
LEGACY_RUNS_DIR = WORKSPACE_ROOT / ".qiqi" / "runs"
RESULT_HOOK_PATH = Path(__file__).with_name("result_hook.py").resolve()
HERDR_BIN = os.environ.get("QIQI_HERDR_BIN", "herdr")
HERDR_SESSION = (
    os.environ.get("QIQI_HERDR_SESSION", "qiqi-delegate").strip() or "qiqi-delegate"
)
HERDR_AGENT_START_TIMEOUT_MS = 60_000
HERDR_SHELL_READY_TIMEOUT_SECONDS = 10.0
NATIVE_SESSION_WAIT_SECONDS = 15.0
NATIVE_RESULT_WAIT_SECONDS = 5.0
CLAUDE_PROMPT_RETRY_EFFECT_SECONDS = 5.0
SUPPORTED_ADAPTERS = {"codex", "claude"}
PLACEHOLDER_RE = re.compile(r"\{[a-z_][a-z0-9_]*\}")
LEGACY_META_PREFIX = "<!-- qiqi-session: "
LEGACY_META_SUFFIX = " -->"

mcp = MCPServer(
    "QiQi Delegate",
    instructions=(
        "Synchronous Herdr-backed repository execution boundary for QiQi. "
        "delegate_repo_task accepts a structured task packet instead of an opaque "
        "prompt string. The packet must explicitly carry the original user request, "
        "repo-local objective, scope, required live context, constraints, acceptance "
        "criteria, verification requirements, and known unknowns. The child does not "
        "share QiQi's hidden context. The MCP launches/resumes the native Codex or "
        "Claude session through Herdr and captures the native final assistant message "
        "through a static result-hook command routed to MCP-owned active-capture state; "
        "it never scrapes terminal scrollback or parses agent transcripts. Codex trusts "
        "only the exact QiQi session hook by matching its computed trusted_hash; global "
        "hook-trust bypass is forbidden. Settled/failed native turns return session_id, "
        "turn_id, state, and the exact agent_response. If Herdr reports blocked before "
        "a native final response exists, the MCP persists session ownership and returns "
        "state blocked with agent_response null so QiQi can RESUME the exact session. "
        "Runtime session ownership is persisted in MCP-owned SQLite state, not in a "
        "Markdown result artifact."
    ),
)

_herdr_server_lock = asyncio.Lock()
_managed_herdr_server: asyncio.subprocess.Process | None = None
_state_lock = asyncio.Lock()
_active_repositories: set[Path] = set()
_active_sessions: set[str] = set()
_store = SessionStore(STATE_DB)


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
            raise RuntimeError(f"repos.yaml: repository {name!r} escapes workspace root") from exc
        result[name] = repo
    return result


def _resolve_repo(repository: str) -> Path:
    registry = _load_repo_registry()
    repo = registry.get(repository)
    if repo is None:
        available = ", ".join(sorted(registry)) or "<none>"
        raise RuntimeError(f"unknown repository {repository!r}; available repositories: {available}")
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
        raise RuntimeError(f"repos.yaml path must be exact Git root: configured={repo}, git={git_root}")
    return repo


def _require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"{label} must be a list of strings")
    return value


def _load_execution_config() -> tuple[dict[str, Any], dict[str, Any]]:
    if not ROUTING_PATH.is_file():
        raise RuntimeError(f"missing agent routing registry: {ROUTING_PATH}")
    data = yaml.safe_load(ROUTING_PATH.read_text(encoding="utf-8")) or {}
    if data.get("version") != 2:
        raise RuntimeError("agent-routing.yaml: version must be 2")
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
                f"agent {name}: unsupported adapter {adapter!r}; supported: "
                f"{', '.join(sorted(SUPPORTED_ADAPTERS))}"
            )
        start_args = _require_string_list(config.get("start_args"), f"agent {name}.start_args")
        resume_args = _require_string_list(config.get("resume_args"), f"agent {name}.resume_args")
        if any("{session_id}" in item for item in start_args):
            raise RuntimeError(f"agent {name}.start_args must not contain {{session_id}}")
        if not any("{session_id}" in item for item in resume_args):
            raise RuntimeError(f"agent {name}.resume_args must contain {{session_id}}")
        for key, template in (("start_args", start_args), ("resume_args", resume_args)):
            if template.count("{handoff_args}") != 1:
                raise RuntimeError(f"agent {name}.{key} must contain exactly one {{handoff_args}}")
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
        forbidden = {"--settings", "--dangerously-bypass-hook-trust", "--enable", "--disable"}
        if any(item in forbidden or item.startswith("hooks.") for item in route_args):
            raise RuntimeError(f"route {name}: result-handoff hook configuration is MCP-owned")
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
    handoff_args: list[str],
) -> list[str]:
    template_key = "resume_args" if session_id else "start_args"
    template = agent[template_key]
    route_args = route.get("args", [])
    if route_args and "{route_args}" not in template:
        raise RuntimeError(f"{template_key} does not contain {{route_args}}")
    values = {"model": route["model"]}
    if session_id:
        values["session_id"] = session_id
    argv: list[str] = []
    for item in template:
        if item == "{route_args}":
            argv.extend(_expand_scalar(arg, values) for arg in route_args)
        elif item == "{handoff_args}":
            argv.extend(handoff_args)
        else:
            argv.append(_expand_scalar(item, values))
    return argv


def _result_hook_command(adapter: str) -> str:
    return shlex.join(
        [
            sys.executable,
            str(RESULT_HOOK_PATH),
            "--adapter",
            adapter,
            "--state-root",
            str(STATE_DB.parent),
        ]
    )


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _codex_stop_hook_hash(command: str) -> str:
    # Mirrors Codex's NormalizedHookIdentity -> TOML -> canonical JSON fingerprint
    # for one Stop command hook with timeout=10 and default async=false.
    identity = {
        "event_name": "stop",
        "hooks": [
            {
                "async": False,
                "command": command,
                "timeout": 10,
                "type": "command",
            }
        ],
    }
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _codex_session_hook_key() -> str:
    if os.name == "nt":
        source = r"C:\<session-flags>\config.toml"
    else:
        source = "/<session-flags>/config.toml"
    return f"{source}:stop:0:0"


def _build_handoff_args(adapter: str) -> list[str]:
    command = _result_hook_command(adapter)
    if adapter == "claude":
        settings = {
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": command}]}],
                "StopFailure": [{"hooks": [{"type": "command", "command": command}]}],
            }
        }
        return ["--settings", json.dumps(settings, ensure_ascii=False, separators=(",", ":"))]
    if adapter == "codex":
        stop_value = (
            "[{hooks=[{type=\"command\",command="
            + _toml_string(command)
            + ",timeout=10}]}]"
        )
        hook_key = _codex_session_hook_key()
        trusted_hash = _codex_stop_hook_hash(command)
        state_value = (
            "{"
            + _toml_string(hook_key)
            + "={trusted_hash="
            + _toml_string(trusted_hash)
            + "}}"
        )
        return [
            "-c",
            "features.hooks=true",
            "-c",
            f"hooks.Stop={stop_value}",
            "-c",
            f"hooks.state={state_value}",
        ]
    raise RuntimeError(f"unsupported result handoff adapter: {adapter}")


def _active_capture_path(adapter: str, repo: Path) -> Path:
    key = hashlib.sha256(f"{adapter}\0{repo.resolve()}".encode("utf-8")).hexdigest()
    return ACTIVE_CAPTURES_DIR / f"{key}.json"


def _register_active_capture(
    *,
    adapter: str,
    repo: Path,
    sink: Path,
    nonce: str,
    expected_session_id: str | None,
    qiqi_turn_id: str,
) -> Path:
    ACTIVE_CAPTURES_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(ACTIVE_CAPTURES_DIR, 0o700)
    except OSError:
        pass
    path = _active_capture_path(adapter, repo)
    payload = {
        "version": 1,
        "adapter": adapter,
        "repo": str(repo.resolve()),
        "sink": str(sink.resolve()),
        "nonce": nonce,
        "expected_session_id": expected_session_id,
        "qiqi_turn_id": qiqi_turn_id,
        "created_at_ns": time.time_ns(),
    }
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with temp.open("x", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, 0o600)
    os.replace(temp, path)
    os.chmod(path, 0o600)
    return path


def _remove_active_capture(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _legacy_artifact_metadata(path: Path) -> dict[str, Any] | None:
    try:
        first_line = path.open("r", encoding="utf-8").readline().rstrip("\n")
    except OSError:
        return None
    if not first_line.startswith(LEGACY_META_PREFIX) or not first_line.endswith(LEGACY_META_SUFFIX):
        return None
    raw = first_line[len(LEGACY_META_PREFIX) : -len(LEGACY_META_SUFFIX)]
    try:
        metadata = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return metadata if isinstance(metadata, dict) else None


def _import_legacy_resume_if_present(repository: str, agent_name: str, session_id: str) -> bool:
    """Import only legacy session ownership; new turns never use Markdown handoff content."""
    if not LEGACY_RUNS_DIR.is_dir():
        return False
    matches: list[Path] = []
    for path in LEGACY_RUNS_DIR.glob("*.md"):
        metadata = _legacy_artifact_metadata(path)
        if not metadata:
            continue
        if (
            metadata.get("repository") == repository
            and metadata.get("agent") == agent_name
            and metadata.get("session_id") == session_id
        ):
            matches.append(path)
    if len(matches) != 1:
        return False
    _store.import_legacy_session(session_id, repository, agent_name)
    return True


async def _claim_resources(repo: Path, session_id: str | None) -> None:
    async with _state_lock:
        if repo in _active_repositories:
            raise RuntimeError(f"repository already has an active delegation: {repo}")
        if session_id and session_id in _active_sessions:
            raise RuntimeError(f"native session already has an active delegation: {session_id}")
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


async def _communicate(
    proc: asyncio.subprocess.Process, input_data: bytes | None = None
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
            f"Herdr command failed (exit={proc.returncode}): {' '.join(args)}"
            f"{f'; {detail}' if detail else ''}"
        )
    return proc.returncode or 0, out_text, err_text


async def _run_herdr_json(*args: str) -> dict[str, Any]:
    _, stdout, _ = await _run_herdr(*args)
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Herdr command returned invalid JSON: {' '.join(args)}") from exc
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
        "workspace", "create", "--cwd", str(repo), "--label", label, "--no-focus"
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
    pane_id: str, adapter: str, agent_args: list[str]
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
                raise RuntimeError(f"Herdr agent start returned invalid JSON: {' '.join(command)}")
            return name, _agent_from_payload(payload, "agent start")
        if _herdr_error_code(payload) != "agent_pane_busy":
            if len(detail) > 3000:
                detail = detail[-3000:]
            raise RuntimeError(
                f"Herdr command failed (exit={returncode}): {' '.join(command)}"
                f"{f'; {detail}' if detail else ''}"
            )
        if time.monotonic() >= deadline:
            if len(last_detail) > 2000:
                last_detail = last_detail[-2000:]
            raise RuntimeError(
                f"Herdr root pane {pane_id} did not become an available shell within "
                f"{HERDR_SHELL_READY_TIMEOUT_SECONDS:g}s"
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
            "Herdr returned unsupported native session reference kind: "
            f"{session.get('kind')!r}"
        )
    value = session.get("value")
    if not isinstance(value, str) or not value:
        raise RuntimeError("Herdr native session identity has no value")
    return value


def _validate_reported_session_if_present(
    agent: dict[str, Any], adapter: str, expected_session_id: str | None
) -> str | None:
    native_session_id = _extract_native_session(agent, adapter)
    if (
        native_session_id is not None
        and expected_session_id is not None
        and native_session_id != expected_session_id
    ):
        raise RuntimeError(
            f"resume identity mismatch: interactive agent reported {native_session_id!r}, "
            f"requested {expected_session_id!r}"
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
            agent, adapter, expected_session_id
        )
        if native_session_id:
            return native_session_id
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Herdr did not receive native {adapter} session identity after the "
                "interactive turn started; verify the current Herdr integration is "
                "loaded by the agent process"
            )
        await asyncio.sleep(0.1)
        agent = await _get_agent(name)


async def _wait_for_claude_enter_recovery(
    name: str, baseline_agent: dict[str, Any]
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
            saw_activity = status == "working" or status != baseline_status or seq_advanced
            if not saw_activity and time.monotonic() >= activity_deadline:
                raise RuntimeError(
                    "Claude prompt remained stalled after one Enter recovery; "
                    "the prompt was not submitted"
                )
        if saw_activity and status in {"idle", "done", "blocked"}:
            return status, agent
        await asyncio.sleep(0.1)


async def _wait_for_agent_settled(
    name: str, initial_agent: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    agent = initial_agent
    while True:
        status = agent.get("agent_status")
        if status in {"idle", "done", "blocked"}:
            return status, agent
        await asyncio.sleep(0.1)
        agent = await _get_agent(name)


async def _prompt_and_wait(
    name: str, prompt: str, adapter: str
) -> tuple[str, dict[str, Any]]:
    command = ["agent", "prompt", name, prompt, "--wait"]
    returncode, stdout, stderr = await _run_herdr(*command, check=False)
    payload = _herdr_json_payload(stdout, stderr)
    if returncode != 0:
        error_code = _herdr_error_code(payload)
        if adapter == "claude" and error_code == "agent_prompt_stalled":
            stalled_agent = await _get_agent(name)
            stalled_status = stalled_agent.get("agent_status")
            if stalled_status == "working":
                return await _wait_for_agent_settled(name, stalled_agent)
            if stalled_status in {"done", "blocked"}:
                return stalled_status, stalled_agent
            if stalled_status != "idle":
                raise RuntimeError(
                    f"Claude prompt stalled in an unexpected agent state: {stalled_status!r}"
                )
            await _run_herdr("agent", "send-keys", name, "enter")
            return await _wait_for_claude_enter_recovery(name, stalled_agent)
        detail = (stderr or stdout).strip()
        if len(detail) > 3000:
            detail = detail[-3000:]
        raise RuntimeError(
            f"Herdr command failed (exit={returncode}): {' '.join(command)}"
            f"{f'; {detail}' if detail else ''}"
        )
    if payload is None:
        raise RuntimeError(f"Herdr agent prompt returned invalid JSON: {' '.join(command)}")
    agent = _agent_from_payload(payload, "agent prompt")
    status = agent.get("agent_status")
    if status not in {"idle", "done", "blocked"}:
        raise RuntimeError(f"Herdr agent prompt settled with unexpected status: {status!r}")
    return status, agent


async def _wait_for_result_capture(
    sink: Path, nonce: str, adapter: str, native_session_id: str
) -> dict[str, Any]:
    deadline = time.monotonic() + NATIVE_RESULT_WAIT_SECONDS
    last_error: Exception | None = None
    while True:
        events = load_capture_events(sink, nonce)
        try:
            return select_capture_event(
                events, adapter=adapter, session_id=native_session_id
            )
        except RuntimeError as exc:
            last_error = exc
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "native final response was not captured after the agent settled; "
                "refusing to fall back to terminal screen or transcript parsing"
            ) from last_error
        await asyncio.sleep(0.05)


def _prepare_resume(repository: str, agent_name: str, session_id: str) -> None:
    try:
        _store.require_resume(session_id, repository, agent_name)
        return
    except RuntimeError as first_error:
        if not _import_legacy_resume_if_present(repository, agent_name, session_id):
            raise first_error
    _store.require_resume(session_id, repository, agent_name)


@mcp.tool()
async def delegate_repo_task(
    repository: str,
    route: str,
    user_request: str,
    objective: str,
    scope: list[str],
    out_of_scope: list[str],
    required_context: list[dict[str, str]],
    constraints: list[str],
    acceptance_criteria: list[str],
    verification: list[str],
    known_unknowns: list[str],
    session_id: str | None = None,
) -> dict[str, Any]:
    """Execute one repo-local task and return the native final assistant message.

    QiQi must pass explicit structured fields. `user_request` preserves the relevant
    original user wording. Each `required_context` entry has exact keys `fact`,
    `source`, and `certainty`; certainty is `verified`, `user-provided`, or
    `authoritative-decision`. `scope` and `acceptance_criteria` must be non-empty.

    Omit `session_id` to START. Pass a returned `session_id` to RESUME that exact
    native conversation. Session ownership is stored in `.qiqi/state/qiqi_delegate.sqlite3`.

    Settled/failed native turns return `session_id`, QiQi-owned `turn_id`, `state`,
    and exact native `agent_response`. If Herdr reaches `blocked` before the agent
    emits a native final response, the MCP first persists native session ownership,
    then returns `state="blocked"`, `agent_response=None`, and
    `blocker_type="agent_blocked"`. No terminal-screen/transcript fallback is used.
    """
    repository = repository.strip()
    route = route.strip()
    session_id = session_id.strip() if isinstance(session_id, str) else None
    if not repository:
        raise ValueError("repository must not be empty")
    if not route:
        raise ValueError("route must not be empty")
    if session_id == "":
        session_id = None

    packet: TaskPacket = build_task_packet(
        user_request=user_request,
        objective=objective,
        scope=scope,
        out_of_scope=out_of_scope,
        required_context=required_context,
        constraints=constraints,
        acceptance_criteria=acceptance_criteria,
        verification=verification,
        known_unknowns=known_unknowns,
    )
    prompt = render_task_prompt(packet)
    repo = _resolve_repo(repository)
    agent_name, agent, route_config = _resolve_route(route)
    adapter = agent["adapter"]
    command_name = agent["command"]
    if shutil.which(command_name) is None:
        raise RuntimeError(f"missing execution agent CLI: {command_name}")
    if not RESULT_HOOK_PATH.is_file():
        raise RuntimeError(f"missing native result hook helper: {RESULT_HOOK_PATH}")
    if session_id:
        _prepare_resume(repository, agent_name, session_id)

    await _ensure_herdr_server()
    await _require_current_integration(adapter)
    await _claim_resources(repo, session_id)

    workspace_id: str | None = None
    capture_path: Path | None = None
    qiqi_turn_id = new_turn_id()
    try:
        with tempfile.TemporaryDirectory(prefix="qiqi-handoff-") as temp_dir:
            sink = Path(temp_dir).resolve()
            os.chmod(sink, 0o700)
            nonce = uuid.uuid4().hex
            capture_path = _register_active_capture(
                adapter=adapter,
                repo=repo,
                sink=sink,
                nonce=nonce,
                expected_session_id=session_id,
                qiqi_turn_id=qiqi_turn_id,
            )
            handoff_args = _build_handoff_args(adapter)
            label = f"qiqi:{repository}:{qiqi_turn_id[:8]}"
            workspace_id, pane_id = await _create_herdr_workspace(repo, label)
            interactive_args = _build_interactive_args(
                agent, route_config, session_id, handoff_args
            )
            managed_name, started_agent = await _start_interactive_agent(
                pane_id, adapter, interactive_args
            )
            _validate_reported_session_if_present(started_agent, adapter, session_id)
            status, prompted_agent = await _prompt_and_wait(
                managed_name, prompt, adapter
            )
            native_session_id = await _wait_for_native_session(
                managed_name, adapter, prompted_agent, session_id
            )

            # Persist ownership as soon as the native identity is known. This is
            # intentionally before result capture / blocked handling so a START that
            # reaches an interactive blocker never loses the only RESUME key.
            _store.register_session(native_session_id, repository, agent_name)

            if status == "blocked":
                return {
                    "session_id": native_session_id,
                    "turn_id": qiqi_turn_id,
                    "state": "blocked",
                    "agent_response": None,
                    "blocker_type": "agent_blocked",
                }

            try:
                event = await _wait_for_result_capture(
                    sink, nonce, adapter, native_session_id
                )
            except RuntimeError as exc:
                raise RuntimeError(
                    f"{exc}; native session ownership was preserved and can be resumed "
                    f"with session_id={native_session_id!r}"
                ) from exc

            state = event["state"]
            response = event["agent_response"]
            native_turn_id = event.get("native_turn_id")
            _store.record_turn(
                turn_id=qiqi_turn_id,
                session_id=native_session_id,
                repository=repository,
                agent=agent_name,
                route=route,
                state=state,
                native_turn_id=native_turn_id,
                packet=packet,
                agent_response=response,
            )
            return {
                "session_id": native_session_id,
                "turn_id": qiqi_turn_id,
                "state": state,
                "agent_response": response,
            }
    finally:
        _remove_active_capture(capture_path)
        if workspace_id:
            await _close_herdr_workspace(workspace_id)
        await _release_resources(repo, session_id)


if __name__ == "__main__":
    mcp.run()
