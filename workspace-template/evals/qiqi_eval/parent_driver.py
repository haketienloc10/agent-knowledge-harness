from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
from typing import Any, Iterator


@dataclass(frozen=True)
class ParentRunResult:
    state: str
    session_id: str | None
    response: str | None
    adapter: str
    route: str
    blocker_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@contextmanager
def _workspace_environment(workspace_root: Path) -> Iterator[None]:
    keys = {
        "QIQI_WORKSPACE_ROOT": str(workspace_root),
        "QIQI_WORK_ITEMS_DIR": str(workspace_root / "work-items"),
    }
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update(keys)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _load_delegate_server(workspace_root: Path):
    module_dir = workspace_root / "mcp" / "qiqi_delegate"
    server_path = module_dir / "server.py"
    if not server_path.is_file():
        raise RuntimeError(f"missing qiqi_delegate server: {server_path}")
    sys.path.insert(0, str(module_dir))
    try:
        name = f"qiqi_eval_delegate_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, server_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load qiqi_delegate server: {server_path}")
        module = importlib.util.module_from_spec(spec)
        # Pydantic/FastMCP resolves postponed annotations through the defining
        # module namespace. importlib does not insert modules created with
        # module_from_spec() into sys.modules automatically, so register the
        # unique eval module before executing server.py and keep it registered
        # for the lifetime of the native parent turn.
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
        return module
    finally:
        try:
            sys.path.remove(str(module_dir))
        except ValueError:
            pass


class ParentAgentDriver:
    """Drive a fresh QiQi parent through the same Herdr/native hook path as delegation."""

    def __init__(self, *, route: str = "codex-balanced"):
        self.route = route

    async def run(self, workspace_root: Path, prompt: str) -> ParentRunResult:
        workspace_root = workspace_root.resolve()
        with _workspace_environment(workspace_root):
            server = _load_delegate_server(workspace_root)
            agent_name, agent, route_config = server._resolve_route(self.route)
            adapter = agent["adapter"]
            command_name = agent["command"]
            if shutil.which(command_name) is None:
                raise RuntimeError(f"missing parent agent CLI: {command_name}")
            if not server.RESULT_HOOK_PATH.is_file():
                raise RuntimeError(
                    f"missing native result hook helper: {server.RESULT_HOOK_PATH}"
                )

            await server._ensure_herdr_server()
            await server._require_current_integration(adapter)

            workspace_id: str | None = None
            capture_path: Path | None = None
            try:
                with tempfile.TemporaryDirectory(prefix="qiqi-eval-parent-") as temp_dir:
                    sink = Path(temp_dir).resolve()
                    nonce = uuid.uuid4().hex
                    turn_id = f"eval-{uuid.uuid4()}"
                    capture_path = server._register_active_capture(
                        adapter=adapter,
                        repo=workspace_root,
                        sink=sink,
                        nonce=nonce,
                        expected_session_id=None,
                        qiqi_turn_id=turn_id,
                    )
                    handoff_args = server._build_handoff_args(adapter)
                    label = f"qiqi-eval:{turn_id[-8:]}"
                    workspace_id, pane_id = await server._create_herdr_workspace(
                        workspace_root, label
                    )
                    interactive_args = server._build_interactive_args(
                        agent, route_config, None, handoff_args
                    )
                    managed_name, started_agent = await server._start_interactive_agent(
                        pane_id, adapter, interactive_args
                    )
                    status, prompted_agent = await server._prompt_and_wait(
                        managed_name, prompt, adapter
                    )
                    native_session_id = await server._wait_for_native_session(
                        managed_name, adapter, prompted_agent, None
                    )
                    if status == "blocked":
                        return ParentRunResult(
                            state="blocked",
                            session_id=native_session_id,
                            response=None,
                            adapter=adapter,
                            route=self.route,
                            blocker_type="agent_blocked",
                        )
                    event = await server._wait_for_result_capture(
                        sink, nonce, adapter, native_session_id
                    )
                    response = event.get("agent_response")
                    if response is not None and not isinstance(response, str):
                        raise RuntimeError("parent native result has non-string agent_response")
                    return ParentRunResult(
                        state=str(event["state"]),
                        session_id=native_session_id,
                        response=response,
                        adapter=adapter,
                        route=self.route,
                    )
            finally:
                server._remove_active_capture(capture_path)
                if workspace_id:
                    await server._close_herdr_workspace(workspace_id)
