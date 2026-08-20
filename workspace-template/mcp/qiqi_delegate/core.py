from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

TASK_PACKET_MAX_CHARS = 120_000
TASK_TEXT_MAX_CHARS = 60_000
TASK_LIST_MAX_ITEMS = 100
TASK_ITEM_MAX_CHARS = 20_000
AGENT_RESPONSE_MAX_CHARS = 2_000_000
CONTEXT_CERTAINTIES = {"verified", "user-provided", "authoritative-decision"}


@dataclass(frozen=True)
class ContextFact:
    fact: str
    source: str
    certainty: str

    def as_dict(self) -> dict[str, str]:
        return {
            "fact": self.fact,
            "source": self.source,
            "certainty": self.certainty,
        }


@dataclass(frozen=True)
class TaskPacket:
    user_request: str
    objective: str
    scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    required_context: tuple[ContextFact, ...]
    constraints: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    verification: tuple[str, ...]
    known_unknowns: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_request": self.user_request,
            "objective": self.objective,
            "scope": list(self.scope),
            "out_of_scope": list(self.out_of_scope),
            "required_context": [item.as_dict() for item in self.required_context],
            "constraints": list(self.constraints),
            "acceptance_criteria": list(self.acceptance_criteria),
            "verification": list(self.verification),
            "known_unknowns": list(self.known_unknowns),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"))


def _clean_required_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) > TASK_TEXT_MAX_CHARS:
        raise ValueError(f"{label} is too large")
    return result


def _clean_string_list(
    value: Any,
    label: str,
    *,
    require_non_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of strings")
    if len(value) > TASK_LIST_MAX_ITEMS:
        raise ValueError(f"{label} has too many items")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{label}[{index}] must be a string")
        cleaned = item.strip()
        if not cleaned:
            raise ValueError(f"{label}[{index}] must not be empty")
        if len(cleaned) > TASK_ITEM_MAX_CHARS:
            raise ValueError(f"{label}[{index}] is too large")
        result.append(cleaned)
    if require_non_empty and not result:
        raise ValueError(f"{label} must contain at least one item")
    return tuple(result)


def _clean_context(value: Any) -> tuple[ContextFact, ...]:
    if not isinstance(value, list):
        raise ValueError("required_context must be a list of objects")
    if len(value) > TASK_LIST_MAX_ITEMS:
        raise ValueError("required_context has too many items")
    result: list[ContextFact] = []
    required_keys = {"fact", "source", "certainty"}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"required_context[{index}] must be an object")
        keys = set(item)
        if keys != required_keys:
            missing = sorted(required_keys - keys)
            extra = sorted(keys - required_keys)
            detail: list[str] = []
            if missing:
                detail.append("missing " + ", ".join(missing))
            if extra:
                detail.append("unsupported " + ", ".join(extra))
            raise ValueError(f"required_context[{index}] has invalid fields: {'; '.join(detail)}")
        fact = _clean_required_text(item["fact"], f"required_context[{index}].fact")
        source = _clean_required_text(item["source"], f"required_context[{index}].source")
        certainty = _clean_required_text(
            item["certainty"], f"required_context[{index}].certainty"
        )
        if certainty not in CONTEXT_CERTAINTIES:
            allowed = ", ".join(sorted(CONTEXT_CERTAINTIES))
            raise ValueError(
                f"required_context[{index}].certainty must be one of: {allowed}"
            )
        result.append(ContextFact(fact=fact, source=source, certainty=certainty))
    return tuple(result)


def build_task_packet(
    *,
    user_request: Any,
    objective: Any,
    scope: Any,
    out_of_scope: Any,
    required_context: Any,
    constraints: Any,
    acceptance_criteria: Any,
    verification: Any,
    known_unknowns: Any,
) -> TaskPacket:
    packet = TaskPacket(
        user_request=_clean_required_text(user_request, "user_request"),
        objective=_clean_required_text(objective, "objective"),
        scope=_clean_string_list(scope, "scope", require_non_empty=True),
        out_of_scope=_clean_string_list(out_of_scope, "out_of_scope"),
        required_context=_clean_context(required_context),
        constraints=_clean_string_list(constraints, "constraints"),
        acceptance_criteria=_clean_string_list(
            acceptance_criteria, "acceptance_criteria", require_non_empty=True
        ),
        verification=_clean_string_list(verification, "verification"),
        known_unknowns=_clean_string_list(known_unknowns, "known_unknowns"),
    )
    if len(packet.to_json()) > TASK_PACKET_MAX_CHARS:
        raise ValueError("task packet is too large")
    return packet


def _bullet_lines(items: Iterable[str], empty_text: str) -> str:
    values = list(items)
    if not values:
        return f"- {empty_text}"
    return "\n".join(f"- {item}" for item in values)


def render_task_prompt(packet: TaskPacket) -> str:
    context_lines: list[str] = []
    if packet.required_context:
        for item in packet.required_context:
            context_lines.append(
                f"- [{item.certainty}] {item.fact}\n  Provenance: {item.source}"
            )
    else:
        context_lines.append("- No workspace/upstream facts are required for this turn.")

    return f"""Repository task delegated by QiQi

## Original user request

{packet.user_request}

## Repository objective

{packet.objective}

## Scope

{_bullet_lines(packet.scope, 'No scope was provided.')}

## Out of scope

{_bullet_lines(packet.out_of_scope, 'Nothing additional was explicitly excluded.')}

## Required workspace / upstream context

{chr(10).join(context_lines)}

## Constraints

{_bullet_lines(packet.constraints, 'No additional constraints beyond repository policy.')}

## Acceptance criteria

{_bullet_lines(packet.acceptance_criteria, 'No acceptance criteria were provided.')}

## Required verification

{_bullet_lines(packet.verification, 'No specific verification command was mandated; choose evidence appropriate to the task and repository policy.')}

## Known unknowns

{_bullet_lines(packet.known_unknowns, 'None explicitly identified.')}

## Context boundary

You do not share QiQi's hidden conversation, hidden reasoning, workspace control context, or sibling-repository state. For user, workspace, upstream, and cross-repository facts, assume only the information explicitly present in this task packet is available to you. You may inspect the current repository and use tools that repository policy permits, including Shared Knowledge MCP when its decision rule calls for it.

Do not invent an omitted external fact. If an external fact is required and cannot be established from the current repository or an allowed knowledge source, state the exact missing input in your final response and stop rather than guessing. Do not inspect sibling repository source, sibling result history, or QiQi workspace control files to fill the gap.

## Handoff contract

Your final assistant response is the authoritative semantic handoff to QiQi and may be forwarded to the user with little or no rewriting. Use the structure that best fits this task; there are no required result headings. Preserve material findings, evidence, caveats, uncertainty, verification details, blockers, and cross-repository implications that could change QiQi's or the user's next decision.

Do not create or update a QiQi result Markdown artifact. Do not rely on terminal scrollback as the handoff. The delegation runtime captures your native final assistant message directly.
""".strip()


def normalize_hook_payload(
    *,
    adapter: str,
    nonce: str,
    payload: Any,
    captured_at_ns: int | None = None,
) -> dict[str, Any]:
    if adapter not in {"claude", "codex"}:
        raise ValueError(f"unsupported adapter: {adapter}")
    if not isinstance(payload, dict):
        raise ValueError("hook input must be a JSON object")

    event = payload.get("hook_event_name")
    if event not in {"Stop", "StopFailure"}:
        raise ValueError(f"unsupported hook event: {event!r}")
    if adapter == "codex" and event != "Stop":
        raise ValueError("Codex result capture only supports Stop")

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("hook payload is missing session_id")

    response = payload.get("last_assistant_message")
    if response is not None and not isinstance(response, str):
        raise ValueError("last_assistant_message must be a string or null")

    if event == "Stop":
        if not isinstance(response, str) or not response.strip():
            raise ValueError("Stop hook is missing the native final assistant message")
        state = "settled"
        error = None
    else:
        state = "failed"
        error_value = payload.get("error")
        error = error_value if isinstance(error_value, str) and error_value else "unknown"
        if not response:
            details = payload.get("error_details")
            response = details if isinstance(details, str) and details else f"Claude turn failed: {error}"

    if len(response) > AGENT_RESPONSE_MAX_CHARS:
        raise ValueError("native final assistant message exceeds configured safety bound")

    native_turn_id = payload.get("turn_id")
    if native_turn_id is not None and not isinstance(native_turn_id, str):
        raise ValueError("turn_id must be a string when present")

    cwd = payload.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise ValueError("cwd must be a string when present")

    return {
        "version": 1,
        "adapter": adapter,
        "nonce": nonce,
        "hook_event": event,
        "state": state,
        "session_id": session_id,
        "native_turn_id": native_turn_id,
        "agent_response": response,
        "error": error,
        "cwd": cwd,
        "captured_at_ns": captured_at_ns if captured_at_ns is not None else time.time_ns(),
    }


def load_capture_events(sink_dir: Path, nonce: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not sink_dir.is_dir():
        return events
    for path in sorted(sink_dir.glob("event-*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict) or raw.get("nonce") != nonce:
            continue
        events.append(raw)
    return events


def select_capture_event(
    events: Iterable[dict[str, Any]],
    *,
    adapter: str,
    session_id: str,
) -> dict[str, Any]:
    matching = [
        event
        for event in events
        if event.get("version") == 1
        and event.get("adapter") == adapter
        and event.get("session_id") == session_id
        and event.get("state") in {"settled", "failed"}
        and isinstance(event.get("agent_response"), str)
        and event.get("agent_response")
    ]
    if not matching:
        raise RuntimeError(
            "native result hook produced no valid final message for the Herdr session"
        )
    matching.sort(key=lambda item: int(item.get("captured_at_ns") or 0))
    return matching[-1]


class SessionStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        self._ensure_schema(conn)
        return conn

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                repository TEXT NOT NULL,
                agent TEXT NOT NULL,
                created_at_ns INTEGER NOT NULL,
                updated_at_ns INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS turns (
                turn_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                repository TEXT NOT NULL,
                route TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('settled', 'failed')),
                native_turn_id TEXT,
                task_packet_json TEXT NOT NULL,
                agent_response TEXT NOT NULL,
                created_at_ns INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS turns_session_idx
                ON turns(session_id, created_at_ns);
            """
        )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id, repository, agent, created_at_ns, updated_at_ns "
                "FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def require_resume(self, session_id: str, repository: str, agent: str) -> None:
        session = self.get_session(session_id)
        if session is None:
            raise RuntimeError(
                "resume requires a session previously recorded by the native handoff "
                f"state store; unknown session_id={session_id!r}"
            )
        if session["repository"] != repository:
            raise RuntimeError(
                "resume repository mismatch: session belongs to "
                f"{session['repository']!r}, requested {repository!r}"
            )
        if session["agent"] != agent:
            raise RuntimeError(
                "cross-agent resume is not allowed: session belongs to "
                f"{session['agent']!r}, selected route uses {agent!r}"
            )

    def import_legacy_session(self, session_id: str, repository: str, agent: str) -> bool:
        now = time.time_ns()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if existing is not None:
                return False
            conn.execute(
                "INSERT INTO sessions(session_id, repository, agent, created_at_ns, updated_at_ns) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, repository, agent, now, now),
            )
        return True

    def record_turn(
        self,
        *,
        turn_id: str,
        session_id: str,
        repository: str,
        agent: str,
        route: str,
        state: str,
        native_turn_id: str | None,
        packet: TaskPacket,
        agent_response: str,
    ) -> None:
        if state not in {"settled", "failed"}:
            raise ValueError(f"unsupported turn state: {state}")
        if not agent_response:
            raise ValueError("agent_response must not be empty")
        now = time.time_ns()
        packet_json = packet.to_json()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT repository, agent FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO sessions(session_id, repository, agent, created_at_ns, updated_at_ns) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (session_id, repository, agent, now, now),
                )
            else:
                if row["repository"] != repository or row["agent"] != agent:
                    raise RuntimeError("session identity changed while recording turn")
                conn.execute(
                    "UPDATE sessions SET updated_at_ns = ? WHERE session_id = ?",
                    (now, session_id),
                )
            conn.execute(
                "INSERT INTO turns(" 
                "turn_id, session_id, repository, route, state, native_turn_id, "
                "task_packet_json, agent_response, created_at_ns" 
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    turn_id,
                    session_id,
                    repository,
                    route,
                    state,
                    native_turn_id,
                    packet_json,
                    agent_response,
                    now,
                ),
            )

    def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM turns WHERE turn_id = ?", (turn_id,)
            ).fetchone()
        return dict(row) if row is not None else None


def new_turn_id() -> str:
    return str(uuid.uuid4())
