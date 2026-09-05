from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Preserve the existing qiqi_delegate task-size safety boundary. The structured
# packet keeps the same aggregate ceiling while semantic completeness/minimality
# remain the design criteria for normal operation.
TASK_PACKET_MAX_CHARS = 100_000
SUPPORTED_HOOK_ADAPTERS = {"claude", "codex"}


def active_capture_filename(adapter: str, repo: Path) -> str:
    if adapter not in SUPPORTED_HOOK_ADAPTERS:
        raise ValueError(f"unsupported adapter: {adapter}")
    key = hashlib.sha256(f"{adapter}\0{repo.resolve()}".encode("utf-8")).hexdigest()
    return f"{key}.json"


def codex_stop_hook_hash(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Codex hook command must not be empty")
    # Mirrors Codex's NormalizedHookIdentity -> TOML -> canonical JSON
    # fingerprint for one Stop command hook with timeout=10 and default
    # async=false. Optional TOML fields with None are omitted before hashing.
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
    canonical = json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def codex_session_hook_key() -> str:
    # Current Codex hook discovery assigns SessionFlags a synthetic config path
    # and persists per-hook state as <source>:<event>:<group>:<handler>.
    if os.name == "nt":
        source = r"C:\<session-flags>\config.toml"
    else:
        source = "/<session-flags>/config.toml"
    return f"{source}:stop:0:0"


@dataclass(frozen=True)
class TrustedFact:
    fact: str
    source: str

    def as_dict(self) -> dict[str, str]:
        return {"fact": self.fact, "source": self.source}


@dataclass(frozen=True)
class ClaimToInvestigate:
    claim: str
    source: str

    def as_dict(self) -> dict[str, str]:
        return {"claim": self.claim, "source": self.source}


@dataclass(frozen=True)
class TaskContext:
    trusted_facts: tuple[TrustedFact, ...]
    claims_to_investigate: tuple[ClaimToInvestigate, ...]

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.trusted_facts:
            result["trusted_facts"] = [item.as_dict() for item in self.trusted_facts]
        if self.claims_to_investigate:
            result["claims_to_investigate"] = [
                item.as_dict() for item in self.claims_to_investigate
            ]
        return result


@dataclass(frozen=True)
class TaskPacket:
    objective: str
    scope: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    out_of_scope: tuple[str, ...] = ()
    context: TaskContext | None = None
    constraints: tuple[str, ...] = ()
    known_unknowns: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "objective": self.objective,
            "scope": list(self.scope),
            "acceptance_criteria": list(self.acceptance_criteria),
        }
        if self.out_of_scope:
            result["out_of_scope"] = list(self.out_of_scope)
        if self.context is not None:
            context = self.context.as_dict()
            if context:
                result["context"] = context
        if self.constraints:
            result["constraints"] = list(self.constraints)
        if self.known_unknowns:
            result["known_unknowns"] = list(self.known_unknowns)
        return result

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"))


def _clean_required_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    return result


def _clean_string_list(
    value: Any,
    label: str,
    *,
    require_non_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{label}[{index}] must be a string")
        cleaned = item.strip()
        if not cleaned:
            raise ValueError(f"{label}[{index}] must not be empty")
        result.append(cleaned)
    if require_non_empty and not result:
        raise ValueError(f"{label} must contain at least one item")
    return tuple(result)


def _clean_optional_string_list(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    return _clean_string_list(value, label)


def _clean_fact_list(value: Any, label: str) -> tuple[TrustedFact, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of objects")
    result: list[TrustedFact] = []
    required_keys = {"fact", "source"}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        keys = set(item)
        if keys != required_keys:
            missing = sorted(required_keys - keys)
            extra = sorted(keys - required_keys)
            detail: list[str] = []
            if missing:
                detail.append("missing " + ", ".join(missing))
            if extra:
                detail.append("unsupported " + ", ".join(extra))
            raise ValueError(f"{label}[{index}] has invalid fields: {'; '.join(detail)}")
        result.append(
            TrustedFact(
                fact=_clean_required_text(item["fact"], f"{label}[{index}].fact"),
                source=_clean_required_text(item["source"], f"{label}[{index}].source"),
            )
        )
    return tuple(result)


def _clean_claim_list(value: Any, label: str) -> tuple[ClaimToInvestigate, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of objects")
    result: list[ClaimToInvestigate] = []
    required_keys = {"claim", "source"}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        keys = set(item)
        if keys != required_keys:
            missing = sorted(required_keys - keys)
            extra = sorted(keys - required_keys)
            detail: list[str] = []
            if missing:
                detail.append("missing " + ", ".join(missing))
            if extra:
                detail.append("unsupported " + ", ".join(extra))
            raise ValueError(f"{label}[{index}] has invalid fields: {'; '.join(detail)}")
        result.append(
            ClaimToInvestigate(
                claim=_clean_required_text(item["claim"], f"{label}[{index}].claim"),
                source=_clean_required_text(item["source"], f"{label}[{index}].source"),
            )
        )
    return tuple(result)


def _clean_context(value: Any) -> TaskContext | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("context must be an object")
    supported_keys = {"trusted_facts", "claims_to_investigate"}
    extra = sorted(set(value) - supported_keys)
    if extra:
        raise ValueError("context has unsupported fields: " + ", ".join(extra))

    trusted_facts = _clean_fact_list(
        value.get("trusted_facts"), "context.trusted_facts"
    )
    claims = _clean_claim_list(
        value.get("claims_to_investigate"), "context.claims_to_investigate"
    )
    trusted_text = {item.fact.casefold() for item in trusted_facts}
    claim_text = {item.claim.casefold() for item in claims}
    overlap = sorted(trusted_text & claim_text)
    if overlap:
        raise ValueError(
            "the same proposition cannot be both trusted_fact and claim_to_investigate"
        )
    if not trusted_facts and not claims:
        return None
    return TaskContext(
        trusted_facts=trusted_facts,
        claims_to_investigate=claims,
    )


def build_task_packet(
    *,
    objective: Any,
    scope: Any,
    acceptance_criteria: Any,
    out_of_scope: Any = None,
    context: Any = None,
    constraints: Any = None,
    known_unknowns: Any = None,
) -> TaskPacket:
    packet = TaskPacket(
        objective=_clean_required_text(objective, "objective"),
        scope=_clean_string_list(scope, "scope", require_non_empty=True),
        acceptance_criteria=_clean_string_list(
            acceptance_criteria, "acceptance_criteria", require_non_empty=True
        ),
        out_of_scope=_clean_optional_string_list(out_of_scope, "out_of_scope"),
        context=_clean_context(context),
        constraints=_clean_optional_string_list(constraints, "constraints"),
        known_unknowns=_clean_optional_string_list(known_unknowns, "known_unknowns"),
    )
    if len(packet.to_json()) > TASK_PACKET_MAX_CHARS:
        raise ValueError("task packet is too large")
    return packet


def _bullet_lines(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_task_prompt(packet: TaskPacket) -> str:
    sections = [
        "Repository task delegated by QiQi",
        f"## Repository objective\n\n{packet.objective}",
        f"## Scope\n\n{_bullet_lines(packet.scope)}",
    ]

    if packet.out_of_scope:
        sections.append(f"## Out of scope\n\n{_bullet_lines(packet.out_of_scope)}")

    if packet.context is not None:
        if packet.context.trusted_facts:
            lines = [
                f"- {item.fact}\n  Provenance: {item.source}"
                for item in packet.context.trusted_facts
            ]
            sections.append("## Trusted facts\n\n" + "\n".join(lines))
        if packet.context.claims_to_investigate:
            lines = [
                f"- {item.claim}\n  Provenance: {item.source}"
                for item in packet.context.claims_to_investigate
            ]
            sections.append("## Claims to investigate\n\n" + "\n".join(lines))

    if packet.constraints:
        sections.append(f"## Constraints\n\n{_bullet_lines(packet.constraints)}")

    sections.append(
        f"## Acceptance criteria\n\n{_bullet_lines(packet.acceptance_criteria)}"
    )

    if packet.known_unknowns:
        sections.append(f"## Known unknowns\n\n{_bullet_lines(packet.known_unknowns)}")

    return "\n\n".join(sections).strip()


def normalize_hook_payload(
    *,
    adapter: str,
    nonce: str,
    payload: Any,
    captured_at_ns: int | None = None,
) -> dict[str, Any]:
    if adapter not in SUPPORTED_HOOK_ADAPTERS:
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
        error = (
            error_value
            if isinstance(error_value, str) and error_value
            else "unknown"
        )
        if not response:
            details = payload.get("error_details")
            response = (
                details
                if isinstance(details, str) and details
                else f"Claude turn failed: {error}"
            )

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
        "captured_at_ns": (
            captured_at_ns if captured_at_ns is not None else time.time_ns()
        ),
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

    def register_session(self, session_id: str, repository: str, agent: str) -> bool:
        now = time.time_ns()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT repository, agent FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is not None:
                if row["repository"] != repository or row["agent"] != agent:
                    raise RuntimeError(
                        "session identity conflicts with existing ownership"
                    )
                return False
            conn.execute(
                "INSERT INTO sessions(session_id, repository, agent, created_at_ns, updated_at_ns) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, repository, agent, now, now),
            )
        return True

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

    def import_legacy_session(
        self, session_id: str, repository: str, agent: str
    ) -> bool:
        return self.register_session(session_id, repository, agent)

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