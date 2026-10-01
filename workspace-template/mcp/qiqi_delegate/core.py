from __future__ import annotations

import hashlib
import json
import os
import re
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
CAPTURE_MAX_RESPONSES = 8
CAPTURE_MAX_RESPONSE_CHARS = 256_000
CAPTURE_LATEST_ACCEPT_RATIO = 0.35
CAPTURE_HOUSEKEEPING_REJECT_RATIO = 0.15
CAPTURE_MIN_SIGNIFICANT_DROP_CHARS = 600
SUPPORTED_HOOK_ADAPTERS = {"claude", "codex"}
SLP_EVENT_TYPES = frozenset(
    {
        "peer.dispatched",
        "peer.response",
        "peer.signal",
        "peer.signal_resolved",
        "peer.capture_ambiguous",
        "lead.disposition",
        "candidate.accepted",
        "candidate.reconciled",
        "dependency.consumed",
        "write_scope.claimed",
        "write_scope.released",
        "work_item.revision_changed",
    }
)
LEAD_DISPOSITION_ACTIONS = frozenset({"accept", "reject", "repair", "defer", "resolve"})
CANDIDATE_RECONCILIATION_ACTIONS = frozenset({"superseded", "abandoned", "revalidated"})
PEER_SIGNAL_TYPES = frozenset(
    {"REOPEN_REQUEST", "DEPENDENCY_REQUEST", "BLOCKED", "runtime_blocked"}
)
SUPERVISOR_CASE_STATUSES = frozenset(
    {"OPEN", "DELIVERED_TO_LEAD", "WAITING_FOR_EVIDENCE", "CLOSED", "ESCALATED_TO_HUMAN"}
)
_WORK_ITEM_REF_RE = re.compile(r"(?:^|;\s*)id=([^;]+);\s*revision=(\d+)(?:;|$)")


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


def _work_item_ref_from_payload(payload: dict[str, Any]) -> tuple[str | None, int | None]:
    context = payload.get("context")
    if not isinstance(context, dict):
        return None, None
    trusted_facts = context.get("trusted_facts")
    if not isinstance(trusted_facts, list):
        return None, None
    for item in trusted_facts:
        if not isinstance(item, dict):
            continue
        fact = item.get("fact")
        if not isinstance(fact, str) or "work_item_path=" not in fact:
            continue
        match = _WORK_ITEM_REF_RE.search(fact)
        if match is None:
            continue
        work_item_id = match.group(1).strip()
        if not work_item_id:
            continue
        return work_item_id, int(match.group(2))
    return None, None


def task_packet_work_item_ref(packet: TaskPacket) -> tuple[str | None, int | None]:
    return _work_item_ref_from_payload(packet.as_dict())


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

    sections.append(
        "## Repository execution boundary\n\n"
        "- Operate only inside the current Git root. Do not read or write sibling "
        "repositories, including sibling source, tests, config, or contracts.\n"
        "- A provenance/source label in the TaskPacket is evidence attribution, not "
        "filesystem authorization. Do not dereference a sibling-repository path merely "
        "because it is named as provenance.\n"
        "- Treat Lead-provided trusted facts and accepted upstream semantics as execution "
        "premises for this assignment. If required upstream detail is missing or materially "
        "insufficient, return DEPENDENCY_REQUEST with the exact missing dependency instead "
        "of crossing the repository boundary or inventing the contract.\n"
        "- The mounted Work Item is a read-only exception only when an explicit "
        "work_item_path locator is provided. Do not mutate it.\n"
        "- Do not read or modify .qiqi/state."
    )

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
    if not isinstance(event, str):
        raise ValueError("hook payload is missing hook_event_name")
    if adapter == "codex" and event != "Stop":
        raise ValueError("Codex result capture only supports Stop")
    if adapter == "claude" and event not in {"Stop", "StopFailure"}:
        raise ValueError(f"unsupported hook event: {event!r}")

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("hook payload is missing session_id")

    response = payload.get("last_assistant_message")
    if response is not None and not isinstance(response, str):
        raise ValueError("last_assistant_message must be a string or null")

    background_task_count = 0
    if event == "Stop":
        if not isinstance(response, str) or not response.strip():
            raise ValueError("Stop hook is missing the native final assistant message")
        if adapter == "claude":
            raw_background_tasks = payload.get("background_tasks")
            if not isinstance(raw_background_tasks, list):
                state = "capture_error"
                error = (
                    "Claude Stop hook is missing background_tasks; "
                    "upgrade Claude Code to a version that reports background task state"
                )
            else:
                background_task_count = len(raw_background_tasks)
                state = "pending_async" if raw_background_tasks else "settled"
                error = None
        else:
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
        "background_task_count": background_task_count,
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


def select_capture_events(
    events: Iterable[dict[str, Any]],
    *,
    adapter: str,
    session_id: str,
) -> list[dict[str, Any]]:
    matching = [
        event
        for event in events
        if event.get("version") == 1
        and event.get("adapter") == adapter
        and event.get("session_id") == session_id
        and event.get("state") in {"pending_async", "settled", "failed", "capture_error"}
        and isinstance(event.get("agent_response"), str)
        and event.get("agent_response")
    ]
    if not matching:
        raise RuntimeError(
            "native result hook produced no valid response capture for the Herdr session"
        )
    matching.sort(key=lambda item: int(item.get("captured_at_ns") or 0))
    if len(matching) > CAPTURE_MAX_RESPONSES:
        raise RuntimeError(
            "native result capture overflow: "
            f"{len(matching)} responses exceeds limit {CAPTURE_MAX_RESPONSES}"
        )
    total_response_chars = sum(len(str(item["agent_response"])) for item in matching)
    if total_response_chars > CAPTURE_MAX_RESPONSE_CHARS:
        raise RuntimeError(
            "native result capture overflow: "
            f"{total_response_chars} response characters exceeds limit "
            f"{CAPTURE_MAX_RESPONSE_CHARS}"
        )
    return matching


def select_capture_event(
    events: Iterable[dict[str, Any]],
    *,
    adapter: str,
    session_id: str,
) -> dict[str, Any]:
    return select_capture_events(
        events,
        adapter=adapter,
        session_id=session_id,
    )[-1]


def _capture_response_length(event: dict[str, Any]) -> int:
    return len(str(event["agent_response"]).strip())


def resolve_capture_events(
    events: Iterable[dict[str, Any]],
    *,
    adapter: str,
    session_id: str,
) -> dict[str, Any]:
    matching = select_capture_events(
        events,
        adapter=adapter,
        session_id=session_id,
    )
    latest = matching[-1]
    state = latest.get("state")
    if state in {"failed", "capture_error", "pending_async"}:
        return dict(latest)

    stops = [
        event
        for event in matching
        if event.get("hook_event") == "Stop"
        and event.get("state") in {"pending_async", "settled"}
    ]
    if len(stops) <= 1:
        return dict(latest)

    distinct_responses: list[str] = []
    for event in stops:
        response = str(event["agent_response"])
        if response not in distinct_responses:
            distinct_responses.append(response)
    if len(distinct_responses) == 1:
        return dict(latest)

    max_length = max(_capture_response_length(event) for event in stops)
    latest_length = _capture_response_length(stops[-1])

    if latest_length >= max_length * CAPTURE_LATEST_ACCEPT_RATIO:
        return dict(stops[-1])

    drop = max_length - latest_length
    if (
        latest_length <= max_length * CAPTURE_HOUSEKEEPING_REJECT_RATIO
        and drop >= CAPTURE_MIN_SIGNIFICANT_DROP_CHARS
    ):
        substantial = [
            event
            for event in stops
            if _capture_response_length(event)
            >= max_length * CAPTURE_LATEST_ACCEPT_RATIO
        ]
        selected = dict(substantial[-1])
        selected["capture_source_state"] = selected.get("state")
        selected["state"] = "settled"
        return selected

    return {
        "version": 1,
        "adapter": adapter,
        "session_id": session_id,
        "native_turn_id": latest.get("native_turn_id"),
        "state": "capture_ambiguous",
        "agent_response": None,
        "candidate_count": len(distinct_responses),
        "capture_events": stops,
        "captured_at_ns": latest.get("captured_at_ns"),
    }


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
            CREATE TABLE IF NOT EXISTS capture_reviews (
                capture_review_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                repository TEXT NOT NULL,
                route TEXT NOT NULL,
                candidate_count INTEGER NOT NULL,
                created_at_ns INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE TABLE IF NOT EXISTS capture_review_events (
                capture_review_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                hook_event TEXT NOT NULL,
                runtime_state TEXT NOT NULL,
                native_turn_id TEXT,
                agent_response TEXT NOT NULL,
                background_task_count INTEGER NOT NULL,
                captured_at_ns INTEGER NOT NULL,
                PRIMARY KEY (capture_review_id, sequence),
                FOREIGN KEY (capture_review_id) REFERENCES capture_reviews(capture_review_id)
            );
            CREATE TABLE IF NOT EXISTS slp_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                turn_id TEXT,
                capture_review_id TEXT,
                session_id TEXT,
                repository TEXT,
                route TEXT,
                graph_run_id TEXT,
                node_id TEXT,
                attempt_id TEXT,
                work_item_id TEXT,
                work_item_revision INTEGER
                    CHECK (work_item_revision IS NULL OR work_item_revision >= 0),
                candidate_id TEXT,
                payload_json TEXT NOT NULL,
                created_at_ns INTEGER NOT NULL,
                FOREIGN KEY (capture_review_id) REFERENCES capture_reviews(capture_review_id)
            );
            CREATE INDEX IF NOT EXISTS slp_events_type_seq_idx
                ON slp_events(event_type, seq);
            CREATE INDEX IF NOT EXISTS slp_events_turn_seq_idx
                ON slp_events(turn_id, seq);
            CREATE TABLE IF NOT EXISTS lead_dispositions (
                disposition_id TEXT PRIMARY KEY,
                event_seq INTEGER NOT NULL UNIQUE,
                turn_id TEXT NOT NULL UNIQUE,
                action TEXT NOT NULL
                    CHECK (action IN ('accept', 'reject', 'repair', 'defer', 'resolve')),
                work_item_id TEXT,
                work_item_revision INTEGER
                    CHECK (work_item_revision IS NULL OR work_item_revision >= 0),
                candidate_id TEXT,
                reason TEXT NOT NULL,
                graph_run_id TEXT,
                node_id TEXT,
                attempt_id TEXT,
                created_at_ns INTEGER NOT NULL,
                FOREIGN KEY (event_seq) REFERENCES slp_events(seq),
                FOREIGN KEY (turn_id) REFERENCES turns(turn_id)
            );
            CREATE TABLE IF NOT EXISTS supervisor_cases (
                case_id TEXT PRIMARY KEY,
                rule TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN (
                        'OPEN',
                        'DELIVERED_TO_LEAD',
                        'WAITING_FOR_EVIDENCE',
                        'CLOSED',
                        'ESCALATED_TO_HUMAN'
                    )),
                opened_event_seq INTEGER NOT NULL,
                closed_event_seq INTEGER,
                finding_fingerprint TEXT NOT NULL UNIQUE,
                subject_key TEXT NOT NULL DEFAULT '',
                turn_id TEXT,
                work_item_id TEXT,
                work_item_revision INTEGER
                    CHECK (work_item_revision IS NULL OR work_item_revision >= 0),
                candidate_id TEXT,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at_ns INTEGER NOT NULL,
                updated_at_ns INTEGER NOT NULL,
                FOREIGN KEY (opened_event_seq) REFERENCES slp_events(seq),
                FOREIGN KEY (closed_event_seq) REFERENCES slp_events(seq)
            );
            CREATE TABLE IF NOT EXISTS supervisor_broker_state (
                broker_id TEXT PRIMARY KEY,
                last_processed_seq INTEGER NOT NULL DEFAULT 0
                    CHECK (last_processed_seq >= 0),
                updated_at_ns INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS write_scope_claims (
                claim_id TEXT PRIMARY KEY,
                claimed_event_seq INTEGER NOT NULL UNIQUE,
                released_event_seq INTEGER,
                repository TEXT NOT NULL,
                owner TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at_ns INTEGER NOT NULL,
                updated_at_ns INTEGER NOT NULL,
                FOREIGN KEY (claimed_event_seq) REFERENCES slp_events(seq),
                FOREIGN KEY (released_event_seq) REFERENCES slp_events(seq)
            );
            CREATE INDEX IF NOT EXISTS write_scope_claims_active_repo_idx
                ON write_scope_claims(repository, active);
            CREATE TABLE IF NOT EXISTS supervisor_findings (
                case_id TEXT PRIMARY KEY,
                verdict TEXT NOT NULL CHECK (verdict IN ('issue', 'no_issue')),
                finding_json TEXT NOT NULL,
                delivered_to_lead_at_ns INTEGER,
                created_at_ns INTEGER NOT NULL,
                updated_at_ns INTEGER NOT NULL,
                FOREIGN KEY (case_id) REFERENCES supervisor_cases(case_id)
            );
            CREATE TABLE IF NOT EXISTS supervisor_control_plane (
                control_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                lead_pane_id TEXT NOT NULL,
                supervisor_pane_id TEXT NOT NULL,
                lead_agent_name TEXT NOT NULL,
                supervisor_agent_name TEXT NOT NULL,
                herdr_session TEXT NOT NULL DEFAULT '',
                lead_model TEXT NOT NULL DEFAULT '',
                supervisor_model TEXT NOT NULL DEFAULT '',
                supervisor_home TEXT NOT NULL,
                supervisor_capture_dir TEXT NOT NULL,
                supervisor_capture_nonce TEXT NOT NULL,
                created_at_ns INTEGER NOT NULL,
                updated_at_ns INTEGER NOT NULL
            );
            """
        )
        supervisor_case_columns = {
            row["name"] if isinstance(row, sqlite3.Row) else row[1]
            for row in conn.execute("PRAGMA table_info(supervisor_cases)").fetchall()
        }
        supervisor_case_additions = {
            "subject_key": "TEXT NOT NULL DEFAULT ''",
            "turn_id": "TEXT",
            "work_item_id": "TEXT",
            "work_item_revision": "INTEGER",
            "candidate_id": "TEXT",
            "details_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for column, definition in supervisor_case_additions.items():
            if column not in supervisor_case_columns:
                conn.execute(
                    f"ALTER TABLE supervisor_cases ADD COLUMN {column} {definition}"
                )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS supervisor_cases_status_rule_idx "
            "ON supervisor_cases(status, rule)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS supervisor_cases_turn_idx "
            "ON supervisor_cases(turn_id, status)"
        )
        supervisor_control_columns = {
            row["name"] if isinstance(row, sqlite3.Row) else row[1]
            for row in conn.execute("PRAGMA table_info(supervisor_control_plane)").fetchall()
        }
        supervisor_control_additions = {
            "herdr_session": "TEXT NOT NULL DEFAULT ''",
            "lead_model": "TEXT NOT NULL DEFAULT ''",
            "supervisor_model": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in supervisor_control_additions.items():
            if column not in supervisor_control_columns:
                conn.execute(
                    f"ALTER TABLE supervisor_control_plane ADD COLUMN {column} {definition}"
                )

    @staticmethod
    def _optional_runtime_text(value: str | None, label: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{label} must be a string when present")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError(f"{label} must not be empty when present")
        return cleaned

    @staticmethod
    def _optional_work_item_revision(value: int | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("work_item_revision must be a non-negative integer when present")
        return value

    @staticmethod
    def _slp_payload_json(payload: dict[str, Any] | None) -> str:
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError("SLP event payload must be an object")
        try:
            return json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("SLP event payload must be JSON-serializable") from exc

    @classmethod
    def _insert_slp_event(
        cls,
        conn: sqlite3.Connection,
        *,
        event_type: str,
        turn_id: str | None = None,
        capture_review_id: str | None = None,
        session_id: str | None = None,
        repository: str | None = None,
        route: str | None = None,
        graph_run_id: str | None = None,
        node_id: str | None = None,
        attempt_id: str | None = None,
        work_item_id: str | None = None,
        work_item_revision: int | None = None,
        candidate_id: str | None = None,
        payload: dict[str, Any] | None = None,
        created_at_ns: int | None = None,
    ) -> int:
        if not isinstance(event_type, str) or event_type not in SLP_EVENT_TYPES:
            raise ValueError(f"unsupported SLP event type: {event_type!r}")
        clean_turn_id = cls._optional_runtime_text(turn_id, "turn_id")
        clean_capture_review_id = cls._optional_runtime_text(
            capture_review_id, "capture_review_id"
        )
        clean_session_id = cls._optional_runtime_text(session_id, "session_id")
        clean_repository = cls._optional_runtime_text(repository, "repository")
        clean_route = cls._optional_runtime_text(route, "route")
        clean_graph_run_id = cls._optional_runtime_text(graph_run_id, "graph_run_id")
        clean_node_id = cls._optional_runtime_text(node_id, "node_id")
        clean_attempt_id = cls._optional_runtime_text(attempt_id, "attempt_id")
        clean_work_item_id = cls._optional_runtime_text(work_item_id, "work_item_id")
        clean_work_item_revision = cls._optional_work_item_revision(work_item_revision)
        if (clean_work_item_id is None) != (clean_work_item_revision is None):
            raise ValueError("work_item_id and work_item_revision must be provided together")
        clean_candidate_id = cls._optional_runtime_text(candidate_id, "candidate_id")
        payload_json = cls._slp_payload_json(payload)
        now = created_at_ns if created_at_ns is not None else time.time_ns()
        cursor = conn.execute(
            "INSERT INTO slp_events("
            "event_type, turn_id, capture_review_id, session_id, repository, route, "
            "graph_run_id, node_id, attempt_id, work_item_id, work_item_revision, "
            "candidate_id, payload_json, created_at_ns"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_type,
                clean_turn_id,
                clean_capture_review_id,
                clean_session_id,
                clean_repository,
                clean_route,
                clean_graph_run_id,
                clean_node_id,
                clean_attempt_id,
                clean_work_item_id,
                clean_work_item_revision,
                clean_candidate_id,
                payload_json,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def record_slp_event(
        self,
        *,
        event_type: str,
        turn_id: str | None = None,
        capture_review_id: str | None = None,
        session_id: str | None = None,
        repository: str | None = None,
        route: str | None = None,
        graph_run_id: str | None = None,
        node_id: str | None = None,
        attempt_id: str | None = None,
        work_item_id: str | None = None,
        work_item_revision: int | None = None,
        candidate_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        with self._connect() as conn:
            return self._insert_slp_event(
                conn,
                event_type=event_type,
                turn_id=turn_id,
                capture_review_id=capture_review_id,
                session_id=session_id,
                repository=repository,
                route=route,
                graph_run_id=graph_run_id,
                node_id=node_id,
                attempt_id=attempt_id,
                work_item_id=work_item_id,
                work_item_revision=work_item_revision,
                candidate_id=candidate_id,
                payload=payload,
            )

    def record_work_item_revision(
        self,
        *,
        work_item_id: str,
        work_item_revision: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        clean_id = self._optional_runtime_text(work_item_id, "work_item_id")
        if clean_id is None:
            raise ValueError("work_item_id must not be empty")
        clean_revision = self._optional_work_item_revision(work_item_revision)
        if clean_revision is None:
            raise ValueError("work_item_revision is required")
        clean_reason = self._optional_runtime_text(reason, "reason")
        with self._connect() as conn:
            latest = conn.execute(
                "SELECT seq, work_item_revision FROM slp_events "
                "WHERE event_type = 'work_item.revision_changed' AND work_item_id = ? "
                "ORDER BY seq DESC LIMIT 1",
                (clean_id,),
            ).fetchone()
            if latest is not None:
                previous = int(latest["work_item_revision"])
                if clean_revision < previous:
                    raise RuntimeError(
                        "Work Item revision must be monotonic: "
                        f"current={previous}, attempted={clean_revision}"
                    )
                if clean_revision == previous:
                    return {
                        "event_seq": int(latest["seq"]),
                        "work_item_id": clean_id,
                        "work_item_revision": clean_revision,
                        "idempotent": True,
                    }
            seq = self._insert_slp_event(
                conn,
                event_type="work_item.revision_changed",
                work_item_id=clean_id,
                work_item_revision=clean_revision,
                payload={"reason": clean_reason} if clean_reason is not None else {},
            )
        return {
            "event_seq": seq,
            "work_item_id": clean_id,
            "work_item_revision": clean_revision,
            "idempotent": False,
        }

    def record_dependency_consumed(
        self,
        *,
        source_turn_id: str,
        consumer_turn_id: str | None = None,
        repository: str | None = None,
        work_item_id: str | None = None,
        work_item_revision: int | None = None,
        candidate_id: str | None = None,
        graph_run_id: str | None = None,
        node_id: str | None = None,
        attempt_id: str | None = None,
    ) -> int:
        source_turn = self._optional_runtime_text(source_turn_id, "source_turn_id")
        if source_turn is None:
            raise ValueError("source_turn_id must not be empty")
        clean_consumer = self._optional_runtime_text(consumer_turn_id, "consumer_turn_id")
        clean_repository = self._optional_runtime_text(repository, "repository")
        clean_work_item_id = self._optional_runtime_text(work_item_id, "work_item_id")
        clean_work_item_revision = self._optional_work_item_revision(work_item_revision)
        if (clean_work_item_id is None) != (clean_work_item_revision is None):
            raise ValueError("work_item_id and work_item_revision must be provided together")
        clean_candidate = self._optional_runtime_text(candidate_id, "candidate_id")
        clean_graph_run = self._optional_runtime_text(graph_run_id, "graph_run_id")
        clean_node = self._optional_runtime_text(node_id, "node_id")
        clean_attempt = self._optional_runtime_text(attempt_id, "attempt_id")
        with self._connect() as conn:
            source = conn.execute(
                "SELECT turn_id FROM turns WHERE turn_id = ?",
                (source_turn,),
            ).fetchone()
            if source is None:
                raise RuntimeError(
                    "dependency consumption requires an existing captured source Peer turn: "
                    f"unknown source_turn_id={source_turn!r}"
                )
            return self._insert_slp_event(
                conn,
                event_type="dependency.consumed",
                turn_id=clean_consumer,
                repository=clean_repository,
                graph_run_id=clean_graph_run,
                node_id=clean_node,
                attempt_id=clean_attempt,
                work_item_id=clean_work_item_id,
                work_item_revision=clean_work_item_revision,
                candidate_id=clean_candidate,
                payload={"source_turn_id": source_turn},
            )

    def record_peer_signal(
        self,
        *,
        turn_id: str,
        signal: str,
        work_item_id: str | None = None,
        work_item_revision: int | None = None,
        details: str | None = None,
    ) -> int:
        clean_turn = self._optional_runtime_text(turn_id, "turn_id")
        if clean_turn is None:
            raise ValueError("turn_id must not be empty")
        if not isinstance(signal, str) or signal.strip() not in PEER_SIGNAL_TYPES:
            raise ValueError(f"unsupported Peer signal: {signal!r}")
        clean_signal = signal.strip()
        clean_work_item_id = self._optional_runtime_text(work_item_id, "work_item_id")
        clean_work_item_revision = self._optional_work_item_revision(work_item_revision)
        if (clean_work_item_id is None) != (clean_work_item_revision is None):
            raise ValueError("work_item_id and work_item_revision must be provided together")
        clean_details = self._optional_runtime_text(details, "details")
        with self._connect() as conn:
            turn = conn.execute(
                "SELECT session_id, repository, route, task_packet_json FROM turns WHERE turn_id = ?",
                (clean_turn,),
            ).fetchone()
            if turn is None:
                raise RuntimeError(
                    "Peer signal requires an existing captured Peer turn: "
                    f"unknown turn_id={clean_turn!r}"
                )
            if clean_work_item_id is None:
                packet_payload = json.loads(turn["task_packet_json"])
                clean_work_item_id, clean_work_item_revision = _work_item_ref_from_payload(
                    packet_payload
                )
            payload: dict[str, Any] = {"signal": clean_signal}
            if clean_details is not None:
                payload["details"] = clean_details
            return self._insert_slp_event(
                conn,
                event_type="peer.signal",
                turn_id=clean_turn,
                session_id=turn["session_id"],
                repository=turn["repository"],
                route=turn["route"],
                work_item_id=clean_work_item_id,
                work_item_revision=clean_work_item_revision,
                payload=payload,
            )

    def record_peer_signal_resolution(
        self,
        *,
        turn_id: str,
        signal: str,
        reason: str,
        work_item_id: str | None = None,
        work_item_revision: int | None = None,
    ) -> int:
        clean_turn = self._optional_runtime_text(turn_id, "turn_id")
        if clean_turn is None:
            raise ValueError("turn_id must not be empty")
        if not isinstance(signal, str):
            raise ValueError("signal must be a string")
        clean_signal = signal.strip()
        if clean_signal not in {"REOPEN_REQUEST", "DEPENDENCY_REQUEST", "BLOCKED"}:
            raise ValueError(f"unsupported Peer signal resolution: {signal!r}")
        clean_reason = self._optional_runtime_text(reason, "reason")
        if clean_reason is None:
            raise ValueError("reason must not be empty")
        clean_work_item_id = self._optional_runtime_text(work_item_id, "work_item_id")
        clean_work_item_revision = self._optional_work_item_revision(work_item_revision)
        if (clean_work_item_id is None) != (clean_work_item_revision is None):
            raise ValueError("work_item_id and work_item_revision must be provided together")

        with self._connect() as conn:
            turn = conn.execute(
                "SELECT session_id, repository, route, task_packet_json FROM turns "
                "WHERE turn_id = ?",
                (clean_turn,),
            ).fetchone()
            if turn is None:
                raise RuntimeError(
                    "Peer signal resolution requires an existing captured Peer turn: "
                    f"unknown turn_id={clean_turn!r}"
                )
            signal_rows = conn.execute(
                "SELECT payload_json FROM slp_events "
                "WHERE event_type = 'peer.signal' AND turn_id = ? ORDER BY seq",
                (clean_turn,),
            ).fetchall()
            if not any(
                json.loads(row["payload_json"]).get("signal") == clean_signal
                for row in signal_rows
            ):
                raise RuntimeError(
                    "Peer signal resolution requires a matching prior explicit Peer signal: "
                    f"turn_id={clean_turn!r}, signal={clean_signal!r}"
                )
            if clean_work_item_id is None:
                packet_payload = json.loads(turn["task_packet_json"])
                clean_work_item_id, clean_work_item_revision = _work_item_ref_from_payload(
                    packet_payload
                )
            return self._insert_slp_event(
                conn,
                event_type="peer.signal_resolved",
                turn_id=clean_turn,
                session_id=turn["session_id"],
                repository=turn["repository"],
                route=turn["route"],
                work_item_id=clean_work_item_id,
                work_item_revision=clean_work_item_revision,
                payload={"signal": clean_signal, "reason": clean_reason},
            )

    def record_candidate_reconciliation(
        self,
        *,
        stale_turn_id: str,
        resolution: str,
        reason: str,
        work_item_id: str,
        work_item_revision: int,
        replacement_turn_id: str | None = None,
    ) -> int:
        clean_stale = self._optional_runtime_text(stale_turn_id, "stale_turn_id")
        if clean_stale is None:
            raise ValueError("stale_turn_id must not be empty")
        if not isinstance(resolution, str):
            raise ValueError("resolution must be a string")
        clean_resolution = resolution.strip().lower()
        if clean_resolution not in CANDIDATE_RECONCILIATION_ACTIONS:
            raise ValueError(f"unsupported candidate reconciliation: {resolution!r}")
        clean_reason = self._optional_runtime_text(reason, "reason")
        if clean_reason is None:
            raise ValueError("reason must not be empty")
        clean_work_item_id = self._optional_runtime_text(work_item_id, "work_item_id")
        if clean_work_item_id is None:
            raise ValueError("work_item_id must not be empty")
        clean_revision = self._optional_work_item_revision(work_item_revision)
        if clean_revision is None:
            raise ValueError("work_item_revision is required")
        clean_replacement = self._optional_runtime_text(
            replacement_turn_id, "replacement_turn_id"
        )

        with self._connect() as conn:
            stale = conn.execute(
                "SELECT turn_id, session_id, repository, route, task_packet_json "
                "FROM turns WHERE turn_id = ?",
                (clean_stale,),
            ).fetchone()
            if stale is None:
                raise RuntimeError(
                    "candidate reconciliation requires an existing captured stale Peer turn: "
                    f"unknown stale_turn_id={clean_stale!r}"
                )
            stale_packet = json.loads(stale["task_packet_json"])
            stale_work_item_id, stale_revision = _work_item_ref_from_payload(stale_packet)
            if stale_work_item_id is not None and stale_work_item_id != clean_work_item_id:
                raise RuntimeError(
                    "candidate reconciliation Work Item does not match stale Peer turn"
                )
            if stale_revision is not None and clean_revision <= stale_revision:
                raise RuntimeError(
                    "candidate reconciliation requires a newer material Work Item revision"
                )

            if clean_replacement is not None:
                replacement = conn.execute(
                    "SELECT task_packet_json FROM turns WHERE turn_id = ?",
                    (clean_replacement,),
                ).fetchone()
                if replacement is None:
                    raise RuntimeError(
                        "candidate reconciliation replacement_turn_id must reference "
                        "an existing captured Peer turn"
                    )
                replacement_packet = json.loads(replacement["task_packet_json"])
                replacement_work_item_id, replacement_revision = _work_item_ref_from_payload(
                    replacement_packet
                )
                if (
                    replacement_work_item_id is not None
                    and replacement_work_item_id != clean_work_item_id
                ):
                    raise RuntimeError(
                        "replacement Peer turn belongs to a different Work Item"
                    )
                if (
                    replacement_revision is not None
                    and replacement_revision < clean_revision
                ):
                    raise RuntimeError(
                        "replacement Peer turn predates the reconciled Work Item revision"
                    )

            payload: dict[str, Any] = {
                "stale_turn_id": clean_stale,
                "resolution": clean_resolution,
                "reason": clean_reason,
            }
            if clean_replacement is not None:
                payload["replacement_turn_id"] = clean_replacement
            return self._insert_slp_event(
                conn,
                event_type="candidate.reconciled",
                turn_id=clean_stale,
                session_id=stale["session_id"],
                repository=stale["repository"],
                route=stale["route"],
                work_item_id=clean_work_item_id,
                work_item_revision=clean_revision,
                payload=payload,
            )

    def record_write_scope_claim(
        self,
        *,
        claim_id: str,
        repository: str,
        owner: str,
        scope: list[str],
        turn_id: str | None = None,
        work_item_id: str | None = None,
        work_item_revision: int | None = None,
    ) -> int:
        clean_claim = self._optional_runtime_text(claim_id, "claim_id")
        clean_repository = self._optional_runtime_text(repository, "repository")
        clean_owner = self._optional_runtime_text(owner, "owner")
        clean_turn = self._optional_runtime_text(turn_id, "turn_id")
        clean_work_item_id = self._optional_runtime_text(work_item_id, "work_item_id")
        clean_work_item_revision = self._optional_work_item_revision(work_item_revision)
        if clean_claim is None or clean_repository is None or clean_owner is None:
            raise ValueError("claim_id, repository and owner are required")
        if (clean_work_item_id is None) != (clean_work_item_revision is None):
            raise ValueError("work_item_id and work_item_revision must be provided together")
        if not isinstance(scope, list) or not scope:
            raise ValueError("scope must contain at least one path/scope entry")
        clean_scope: list[str] = []
        for item in scope:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("scope entries must be non-empty strings")
            clean_scope.append(item.strip())
        return self.record_slp_event(
            event_type="write_scope.claimed",
            turn_id=clean_turn,
            repository=clean_repository,
            work_item_id=clean_work_item_id,
            work_item_revision=clean_work_item_revision,
            payload={
                "claim_id": clean_claim,
                "owner": clean_owner,
                "scope": clean_scope,
            },
        )

    def record_write_scope_release(
        self,
        *,
        claim_id: str,
        repository: str,
        turn_id: str | None = None,
        work_item_id: str | None = None,
        work_item_revision: int | None = None,
    ) -> int:
        clean_claim = self._optional_runtime_text(claim_id, "claim_id")
        clean_repository = self._optional_runtime_text(repository, "repository")
        clean_turn = self._optional_runtime_text(turn_id, "turn_id")
        clean_work_item_id = self._optional_runtime_text(work_item_id, "work_item_id")
        clean_work_item_revision = self._optional_work_item_revision(work_item_revision)
        if clean_claim is None or clean_repository is None:
            raise ValueError("claim_id and repository are required")
        if (clean_work_item_id is None) != (clean_work_item_revision is None):
            raise ValueError("work_item_id and work_item_revision must be provided together")
        return self.record_slp_event(
            event_type="write_scope.released",
            turn_id=clean_turn,
            repository=clean_repository,
            work_item_id=clean_work_item_id,
            work_item_revision=clean_work_item_revision,
            payload={"claim_id": clean_claim},
        )

    def list_slp_events(
        self, *, after_seq: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        if isinstance(after_seq, bool) or not isinstance(after_seq, int) or after_seq < 0:
            raise ValueError("after_seq must be a non-negative integer")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer between 1 and 1000")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM slp_events WHERE seq > ? ORDER BY seq ASC LIMIT ?",
                (after_seq, limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def record_lead_disposition_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        turn_id: str,
        action: str,
        reason: str,
        work_item_id: str | None = None,
        work_item_revision: int | None = None,
        candidate_id: str | None = None,
        graph_run_id: str | None = None,
        node_id: str | None = None,
        attempt_id: str | None = None,
    ) -> dict[str, Any]:
        """Record one exact Lead disposition using the caller's active SQLite transaction."""
        clean_turn_id = self._optional_runtime_text(turn_id, "turn_id")
        if clean_turn_id is None:
            raise ValueError("turn_id must not be empty")
        if not isinstance(action, str):
            raise ValueError("action must be a string")
        clean_action = action.strip().lower()
        if clean_action not in LEAD_DISPOSITION_ACTIONS:
            raise ValueError(f"unsupported Lead disposition action: {action!r}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must not be empty")
        clean_reason = reason.strip()
        clean_work_item_id = self._optional_runtime_text(work_item_id, "work_item_id")
        clean_work_item_revision = self._optional_work_item_revision(work_item_revision)
        if (clean_work_item_id is None) != (clean_work_item_revision is None):
            raise ValueError("work_item_id and work_item_revision must be provided together")
        clean_candidate_id = self._optional_runtime_text(candidate_id, "candidate_id")
        clean_graph_run_id = self._optional_runtime_text(graph_run_id, "graph_run_id")
        clean_node_id = self._optional_runtime_text(node_id, "node_id")
        clean_attempt_id = self._optional_runtime_text(attempt_id, "attempt_id")

        turn = conn.execute(
            "SELECT turn_id, session_id, repository, route, task_packet_json "
            "FROM turns WHERE turn_id = ?",
            (clean_turn_id,),
        ).fetchone()
        if turn is None:
            raise RuntimeError(
                "Lead disposition requires an existing captured Peer turn: "
                f"unknown turn_id={clean_turn_id!r}"
            )
        if clean_work_item_id is None:
            packet_payload = json.loads(turn["task_packet_json"])
            inferred_id, inferred_revision = _work_item_ref_from_payload(packet_payload)
            clean_work_item_id = inferred_id
            clean_work_item_revision = inferred_revision

        existing = conn.execute(
            "SELECT * FROM lead_dispositions WHERE turn_id = ?",
            (clean_turn_id,),
        ).fetchone()
        if existing is not None:
            same = (
                existing["action"] == clean_action
                and existing["reason"] == clean_reason
                and existing["work_item_id"] == clean_work_item_id
                and existing["work_item_revision"] == clean_work_item_revision
                and existing["candidate_id"] == clean_candidate_id
                and existing["graph_run_id"] == clean_graph_run_id
                and existing["node_id"] == clean_node_id
                and existing["attempt_id"] == clean_attempt_id
            )
            if not same:
                raise RuntimeError(
                    "Peer turn already has a different Lead disposition; "
                    "a single actionable Peer response may not be dispositioned twice"
                )
            result = dict(existing)
            result["idempotent"] = True
            return result

        disposition_id = str(uuid.uuid4())
        now = time.time_ns()
        event_seq = self._insert_slp_event(
            conn,
            event_type="lead.disposition",
            turn_id=clean_turn_id,
            session_id=turn["session_id"],
            repository=turn["repository"],
            route=turn["route"],
            graph_run_id=clean_graph_run_id,
            node_id=clean_node_id,
            attempt_id=clean_attempt_id,
            work_item_id=clean_work_item_id,
            work_item_revision=clean_work_item_revision,
            candidate_id=clean_candidate_id,
            payload={
                "disposition_id": disposition_id,
                "action": clean_action,
            },
            created_at_ns=now,
        )
        conn.execute(
            "INSERT INTO lead_dispositions("
            "disposition_id, event_seq, turn_id, action, work_item_id, "
            "work_item_revision, candidate_id, reason, graph_run_id, node_id, "
            "attempt_id, created_at_ns"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                disposition_id,
                event_seq,
                clean_turn_id,
                clean_action,
                clean_work_item_id,
                clean_work_item_revision,
                clean_candidate_id,
                clean_reason,
                clean_graph_run_id,
                clean_node_id,
                clean_attempt_id,
                now,
            ),
        )
        if clean_action == "accept":
            self._insert_slp_event(
                conn,
                event_type="candidate.accepted",
                turn_id=clean_turn_id,
                session_id=turn["session_id"],
                repository=turn["repository"],
                route=turn["route"],
                graph_run_id=clean_graph_run_id,
                node_id=clean_node_id,
                attempt_id=clean_attempt_id,
                work_item_id=clean_work_item_id,
                work_item_revision=clean_work_item_revision,
                candidate_id=clean_candidate_id,
                payload={"disposition_id": disposition_id},
                created_at_ns=now,
            )
        row = conn.execute(
            "SELECT * FROM lead_dispositions WHERE disposition_id = ?",
            (disposition_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Lead disposition was not persisted")
        result = dict(row)
        result["idempotent"] = False
        return result

    def record_lead_disposition(
        self,
        *,
        turn_id: str,
        action: str,
        reason: str,
        work_item_id: str | None = None,
        work_item_revision: int | None = None,
        candidate_id: str | None = None,
        graph_run_id: str | None = None,
        node_id: str | None = None,
        attempt_id: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            return self.record_lead_disposition_in_transaction(
                conn,
                turn_id=turn_id,
                action=action,
                reason=reason,
                work_item_id=work_item_id,
                work_item_revision=work_item_revision,
                candidate_id=candidate_id,
                graph_run_id=graph_run_id,
                node_id=node_id,
                attempt_id=attempt_id,
            )

    def get_lead_disposition(self, turn_id: str) -> dict[str, Any] | None:
        clean_turn_id = self._optional_runtime_text(turn_id, "turn_id")
        if clean_turn_id is None:
            raise ValueError("turn_id must not be empty")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lead_dispositions WHERE turn_id = ?",
                (clean_turn_id,),
            ).fetchone()
        return dict(row) if row is not None else None

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
        work_item_id, work_item_revision = task_packet_work_item_ref(packet)
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
            self._insert_slp_event(
                conn,
                event_type="peer.response",
                turn_id=turn_id,
                session_id=session_id,
                repository=repository,
                route=route,
                work_item_id=work_item_id,
                work_item_revision=work_item_revision,
                payload={"runtime_state": state},
                created_at_ns=now,
            )

    def record_capture_review(
        self,
        *,
        capture_review_id: str,
        session_id: str,
        repository: str,
        agent: str,
        route: str,
        events: Iterable[dict[str, Any]],
    ) -> None:
        captured = [
            dict(event)
            for event in events
            if event.get("hook_event") == "Stop"
            and isinstance(event.get("agent_response"), str)
            and event.get("agent_response")
        ]
        if not captured:
            raise ValueError("capture review must contain at least one Stop response")
        if len(captured) > CAPTURE_MAX_RESPONSES:
            raise ValueError("capture review exceeds response-count limit")
        total_response_chars = sum(len(str(event["agent_response"])) for event in captured)
        if total_response_chars > CAPTURE_MAX_RESPONSE_CHARS:
            raise ValueError("capture review exceeds response-size limit")
        distinct_responses = list(
            dict.fromkeys(str(event["agent_response"]) for event in captured)
        )
        now = time.time_ns()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT repository, agent FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("capture review requires a registered native session")
            if row["repository"] != repository or row["agent"] != agent:
                raise RuntimeError(
                    "session identity changed while recording capture review"
                )
            conn.execute(
                "INSERT INTO capture_reviews("
                "capture_review_id, session_id, repository, route, candidate_count, created_at_ns"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                (
                    capture_review_id,
                    session_id,
                    repository,
                    route,
                    len(distinct_responses),
                    now,
                ),
            )
            for sequence, event in enumerate(captured, start=1):
                conn.execute(
                    "INSERT INTO capture_review_events("
                    "capture_review_id, sequence, hook_event, runtime_state, native_turn_id, "
                    "agent_response, background_task_count, captured_at_ns"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        capture_review_id,
                        sequence,
                        str(event.get("hook_event") or "Stop"),
                        str(event.get("state") or "unknown"),
                        event.get("native_turn_id"),
                        str(event["agent_response"]),
                        int(event.get("background_task_count") or 0),
                        int(event.get("captured_at_ns") or 0),
                    ),
                )
            self._insert_slp_event(
                conn,
                event_type="peer.capture_ambiguous",
                capture_review_id=capture_review_id,
                session_id=session_id,
                repository=repository,
                route=route,
                payload={"candidate_count": len(distinct_responses)},
                created_at_ns=now,
            )

    def get_capture_review(self, capture_review_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            review = conn.execute(
                "SELECT * FROM capture_reviews WHERE capture_review_id = ?",
                (capture_review_id,),
            ).fetchone()
            if review is None:
                return None
            events = conn.execute(
                "SELECT sequence, hook_event, runtime_state, native_turn_id, agent_response, "
                "background_task_count, captured_at_ns "
                "FROM capture_review_events WHERE capture_review_id = ? ORDER BY sequence",
                (capture_review_id,),
            ).fetchall()
        result = dict(review)
        result["candidates"] = [dict(event) for event in events]
        return result

    def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM turns WHERE turn_id = ?", (turn_id,)
            ).fetchone()
        return dict(row) if row is not None else None


def new_turn_id() -> str:
    return str(uuid.uuid4())
