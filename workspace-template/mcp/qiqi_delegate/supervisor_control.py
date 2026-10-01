#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from core import (
    SessionStore,
    codex_session_hook_key,
    codex_stop_hook_hash,
    load_capture_events,
    resolve_capture_events,
)

CONTROL_ID = "slp-control"
LEAD_AGENT_NAME = "lead"
SUPERVISOR_AGENT_NAME = "supervisor"
DEFAULT_MODEL = "gpt-5.6-luna"
HERDR_AGENT_START_TIMEOUT_MS = 60_000
SUPERVISOR_PROMPT_TIMEOUT_MS = 120_000
SUPERVISOR_CAPTURE_WAIT_SECONDS = 5.0
RESULT_HOOK_PATH = Path(__file__).with_name("result_hook.py").resolve()

_FINDING_KEYS = frozenset(
    {
        "case_id",
        "status",
        "observation",
        "evidence",
        "open_question_for_lead",
    }
)

_RULE_CONTRACTS: dict[str, dict[str, Any]] = {
    "R1": {
        "predicate": (
            "An actual Peer response exists for the exact turn and no explicit Lead "
            "disposition is recorded for that same Peer turn."
        ),
        "issue_when": [
            "peer_response_locator.turn_id is present",
            "disposition_state.recorded is false",
        ],
    },
    "R2": {
        "predicate": (
            "A downstream dependency was consumed before the exact upstream Peer "
            "response had an explicit Lead ACCEPT disposition."
        ),
        "issue_when": [
            "governance_facts.source_turn_id is present",
            "the source Peer turn does not have disposition action accept",
        ],
    },
    "R3": {
        "predicate": (
            "Two active writable ownership claims overlap within the same repository "
            "while both claims remain active."
        ),
        "issue_when": [
            "governance_facts identifies both active claim ids",
            "governance_facts identifies the overlapping writable scope",
        ],
    },
    "R4": {
        "predicate": (
            "A Peer REOPEN_REQUEST, DEPENDENCY_REQUEST, or BLOCKED signal remains "
            "unresolved by subsequent Lead semantic evidence."
        ),
        "issue_when": [
            "governance_facts.signal is REOPEN_REQUEST, DEPENDENCY_REQUEST, or BLOCKED",
            "the case remains open for the exact Peer turn",
        ],
    },
    "R5": {
        "predicate": (
            "A Peer response was produced under an older Work Item revision than the "
            "current material requirement revision and is therefore stale for current "
            "acceptance. A disposition recorded for the older revision does not make "
            "that response current."
        ),
        "issue_when": [
            "governance_facts.stale_revision is lower than governance_facts.current_revision",
            "peer_response_locator.turn_id identifies the stale Peer response",
        ],
    },
}

SUPERVISOR_AGENTS = """# Autonomous SLP Supervisor

You are the Supervisor governance plane for one SLP workspace.

You receive only bounded AuditPackets. Treat them as the complete evidence surface for
this audit. Do not search repositories, Work Items, terminal scrollback, transcripts,
other agents, or external sources.

Authority boundary:
- You do not implement or edit project work.
- You do not ACCEPT or REJECT technical candidates.
- You do not mutate canonical Work Items.
- You do not direct or prompt Peers.
- You do not prescribe implementation.
- You identify a concrete governance deviation, or state that the bounded evidence does
  not establish one.
- AuditPacket.rule_contract is the normative meaning of the deterministic broker rule.
  Evaluate whether the packet facts satisfy that predicate; do not reinterpret an opaque
  rule id from general judgment, severity, technical quality, or implementation outcome.
- Return status=issue when the bounded packet facts satisfy rule_contract.issue_when.
  Return status=no_issue only when the bounded packet is missing or contradicts evidence
  required by that rule contract.

Return exactly one JSON object and no Markdown:
{
  "case_id": "<exact packet case_id>",
  "status": "issue" | "no_issue",
  "observation": "<bounded factual observation>",
  "evidence": ["<packet fact>", "..."],
  "open_question_for_lead": "<question>" | null
}

For status=issue, open_question_for_lead must be a non-empty question that leaves the
technical correction to Lead. For status=no_issue it must be null.
Do not add action, decision, disposition, implementation, delegation, command, patch,
Work Item mutation, or tool-call fields.
"""


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def default_supervisor_home(
    workspace_root: Path,
    *,
    environ: dict[str, str] | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    override = env.get("QIQI_SUPERVISOR_HOME")
    if isinstance(override, str) and override.strip():
        return Path(override).expanduser().resolve()

    digest = hashlib.sha256(str(workspace_root.resolve()).encode("utf-8")).hexdigest()[:16]
    xdg_state = env.get("XDG_STATE_HOME")
    if isinstance(xdg_state, str) and xdg_state.strip():
        root = Path(xdg_state).expanduser()
    else:
        home = env.get("HOME")
        if not isinstance(home, str) or not home.strip():
            raise RuntimeError(
                "cannot resolve isolated Supervisor home without HOME, XDG_STATE_HOME, "
                "or QIQI_SUPERVISOR_HOME"
            )
        root = Path(home).expanduser() / ".local" / "state"
    return (root / "qiqi-supervisor" / digest).resolve()


def build_audit_packet(case: dict[str, Any]) -> dict[str, Any]:
    case_id = _required_text(case.get("case_id"), "case_id")
    rule = _required_text(case.get("rule"), "rule")
    rule_contract = _RULE_CONTRACTS.get(rule)
    if rule_contract is None:
        raise ValueError(f"unsupported Supervisor rule: {rule!r}")
    turn_id = case.get("turn_id")
    if turn_id is not None:
        turn_id = _required_text(turn_id, "turn_id")

    work_item = None
    work_item_id = case.get("work_item_id")
    work_item_revision = case.get("work_item_revision")
    if isinstance(work_item_id, str) and work_item_id:
        if not isinstance(work_item_revision, int) or work_item_revision < 0:
            raise ValueError("case Work Item revision is invalid")
        work_item = {
            "id": work_item_id,
            "revision": work_item_revision,
        }

    details = case.get("details")
    if not isinstance(details, dict):
        details = {}

    disposition = case.get("lead_disposition")
    if isinstance(disposition, dict) and disposition:
        disposition_state = {
            "recorded": True,
            "source": "lead_dispositions",
            "disposition_id": disposition.get("disposition_id"),
            "action": disposition.get("action"),
            "work_item_revision": disposition.get("work_item_revision"),
            "candidate_id": disposition.get("candidate_id"),
        }
    else:
        disposition_state = {
            "recorded": False,
            "source": "lead_dispositions",
        }

    return {
        "version": 2,
        "case_id": case_id,
        "rule": rule,
        "rule_contract": {
            "predicate": rule_contract["predicate"],
            "issue_when": list(rule_contract["issue_when"]),
        },
        "work_item": work_item,
        "lead_brief_locator": (
            {"turn_id": turn_id, "source": "turns.task_packet_json"}
            if turn_id
            else None
        ),
        "peer_response_locator": (
            {"turn_id": turn_id, "source": "turns.agent_response"}
            if turn_id
            else None
        ),
        "disposition_state": disposition_state,
        "candidate_id": case.get("candidate_id"),
        "governance_facts": details,
    }


def render_supervisor_prompt(packet: dict[str, Any]) -> str:
    return (
        "Audit this bounded SLP governance case. Use only the AuditPacket below. "
        "Treat rule_contract as the normative deterministic rule meaning. "
        "Do not inspect files, terminals, transcripts, agents, or tools. "
        "Return exactly the required JSON object.\n\nAuditPacket:\n"
        + json.dumps(
            packet,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    )


def parse_supervisor_finding(raw: str, *, expected_case_id: str) -> dict[str, Any]:
    payload = _json_object(raw.strip(), "Supervisor finding")
    extra = set(payload) - _FINDING_KEYS
    missing = _FINDING_KEYS - set(payload)
    if extra or missing:
        raise ValueError(
            "Supervisor finding schema mismatch: "
            f"missing={sorted(missing)}; extra={sorted(extra)}"
        )

    case_id = _required_text(payload["case_id"], "Supervisor finding case_id")
    if case_id != expected_case_id:
        raise ValueError(
            f"Supervisor finding case_id mismatch: expected {expected_case_id!r}, got {case_id!r}"
        )

    status = payload["status"]
    if status not in {"issue", "no_issue"}:
        raise ValueError("Supervisor finding status must be issue or no_issue")

    observation = _required_text(payload["observation"], "Supervisor observation")
    if len(observation) > 4000:
        raise ValueError("Supervisor observation exceeds bounded size")

    evidence = payload["evidence"]
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 12:
        raise ValueError("Supervisor evidence must contain 1..12 bounded strings")
    clean_evidence: list[str] = []
    for item in evidence:
        text = _required_text(item, "Supervisor evidence item")
        if len(text) > 1000:
            raise ValueError("Supervisor evidence item exceeds bounded size")
        clean_evidence.append(text)

    question = payload["open_question_for_lead"]
    if status == "issue":
        question = _required_text(question, "Supervisor open_question_for_lead")
        if len(question) > 2000:
            raise ValueError("Supervisor open question exceeds bounded size")
        if not question.rstrip().endswith("?"):
            raise ValueError("Supervisor issue must end with an open question for Lead")
    elif question is not None:
        raise ValueError("Supervisor no_issue finding must use null open_question_for_lead")

    return {
        "case_id": case_id,
        "status": status,
        "observation": observation,
        "evidence": clean_evidence,
        "open_question_for_lead": question,
    }


def render_lead_finding(finding: dict[str, Any]) -> str:
    if finding["status"] != "issue":
        raise ValueError("only issue findings may be delivered to Lead")
    evidence_lines = "\n".join(f"- {item}" for item in finding["evidence"])
    context = finding.get("_case_context")
    locator_lines: list[str] = []
    if isinstance(context, dict):
        turn_id = context.get("turn_id")
        if isinstance(turn_id, str) and turn_id:
            locator_lines.append(f"peer_turn_id: {turn_id}")
        work_item_id = context.get("work_item_id")
        revision = context.get("work_item_revision")
        if isinstance(work_item_id, str) and work_item_id and isinstance(revision, int):
            locator_lines.append(f"work_item: {work_item_id}@{revision}")
        candidate_id = context.get("candidate_id")
        if isinstance(candidate_id, str) and candidate_id:
            locator_lines.append(f"candidate_id: {candidate_id}")
    locator_block = (
        "Runtime locator:\n" + "\n".join(locator_lines) + "\n"
        if locator_lines
        else ""
    )
    return (
        "[SLP Supervisor governance finding]\n"
        f"case_id: {finding['case_id']}\n"
        f"{locator_block}"
        f"Observation: {finding['observation']}\n"
        "Evidence:\n"
        f"{evidence_lines}\n"
        f"Open question: {finding['open_question_for_lead']}\n\n"
        "This is an oversight finding, not technical acceptance/rejection or an "
        "implementation instruction. Reconcile it through normal Lead authority. "
        "Use the exact runtime locator above when recording semantic disposition. "
        "The case will close only from new semantic runtime evidence."
    )


class SupervisorControlStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        SessionStore._ensure_schema(conn)
        return conn

    def get_control_plane(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM supervisor_control_plane WHERE control_id = ?",
                (CONTROL_ID,),
            ).fetchone()
        return dict(row) if row is not None else None

    def save_control_plane(
        self,
        *,
        workspace_id: str,
        lead_pane_id: str,
        supervisor_pane_id: str,
        herdr_session: str,
        lead_model: str,
        supervisor_model: str,
        supervisor_home: Path,
        supervisor_capture_dir: Path,
        supervisor_capture_nonce: str,
    ) -> dict[str, Any]:
        values = {
            "workspace_id": _required_text(workspace_id, "workspace_id"),
            "lead_pane_id": _required_text(lead_pane_id, "lead_pane_id"),
            "supervisor_pane_id": _required_text(
                supervisor_pane_id, "supervisor_pane_id"
            ),
            "herdr_session": _required_text(herdr_session, "herdr_session"),
            "lead_model": _required_text(lead_model, "lead_model"),
            "supervisor_model": _required_text(supervisor_model, "supervisor_model"),
            "supervisor_home": str(supervisor_home.resolve()),
            "supervisor_capture_dir": str(supervisor_capture_dir.resolve()),
            "supervisor_capture_nonce": _required_text(
                supervisor_capture_nonce, "supervisor_capture_nonce"
            ),
        }
        now = time.time_ns()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO supervisor_control_plane("
                "control_id, workspace_id, lead_pane_id, supervisor_pane_id, "
                "lead_agent_name, supervisor_agent_name, herdr_session, lead_model, "
                "supervisor_model, supervisor_home, supervisor_capture_dir, "
                "supervisor_capture_nonce, created_at_ns, updated_at_ns"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(control_id) DO UPDATE SET "
                "workspace_id=excluded.workspace_id, "
                "lead_pane_id=excluded.lead_pane_id, "
                "supervisor_pane_id=excluded.supervisor_pane_id, "
                "lead_agent_name=excluded.lead_agent_name, "
                "supervisor_agent_name=excluded.supervisor_agent_name, "
                "herdr_session=excluded.herdr_session, "
                "lead_model=excluded.lead_model, "
                "supervisor_model=excluded.supervisor_model, "
                "supervisor_home=excluded.supervisor_home, "
                "supervisor_capture_dir=excluded.supervisor_capture_dir, "
                "supervisor_capture_nonce=excluded.supervisor_capture_nonce, "
                "updated_at_ns=excluded.updated_at_ns",
                (
                    CONTROL_ID,
                    values["workspace_id"],
                    values["lead_pane_id"],
                    values["supervisor_pane_id"],
                    LEAD_AGENT_NAME,
                    SUPERVISOR_AGENT_NAME,
                    values["herdr_session"],
                    values["lead_model"],
                    values["supervisor_model"],
                    values["supervisor_home"],
                    values["supervisor_capture_dir"],
                    values["supervisor_capture_nonce"],
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM supervisor_control_plane WHERE control_id = ?",
                (CONTROL_ID,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Supervisor control-plane state was not persisted")
        return dict(row)

    def clear_control_plane(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM supervisor_control_plane WHERE control_id = ?",
                (CONTROL_ID,),
            )

    def pending_unreviewed_cases(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.*, d.disposition_id AS disposition_id, "
                "d.action AS disposition_action, "
                "d.work_item_revision AS disposition_work_item_revision, "
                "d.candidate_id AS disposition_candidate_id "
                "FROM supervisor_cases c "
                "LEFT JOIN supervisor_findings f ON f.case_id = c.case_id "
                "LEFT JOIN lead_dispositions d ON d.turn_id = c.turn_id "
                "WHERE c.status = 'OPEN' AND f.case_id IS NULL "
                "ORDER BY c.opened_event_seq, c.case_id LIMIT ?",
                (limit,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            disposition_id = item.pop("disposition_id")
            disposition_action = item.pop("disposition_action")
            disposition_revision = item.pop("disposition_work_item_revision")
            disposition_candidate_id = item.pop("disposition_candidate_id")
            if isinstance(disposition_id, str) and disposition_id:
                item["lead_disposition"] = {
                    "disposition_id": disposition_id,
                    "action": disposition_action,
                    "work_item_revision": disposition_revision,
                    "candidate_id": disposition_candidate_id,
                }
            result.append(item)
        return result

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM supervisor_cases WHERE case_id = ?",
                (_required_text(case_id, "case_id"),),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["details"] = json.loads(item.pop("details_json"))
        return item

    def record_finding(self, finding: dict[str, Any]) -> bool:
        case_id = _required_text(finding.get("case_id"), "finding case_id")
        if finding.get("status") not in {"issue", "no_issue"}:
            raise ValueError("finding status must be issue or no_issue")
        encoded = json.dumps(
            finding,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        now = time.time_ns()
        with self._connect() as conn:
            case = conn.execute(
                "SELECT status FROM supervisor_cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if case is None:
                raise RuntimeError(f"unknown Supervisor case: {case_id}")
            if case["status"] == "CLOSED":
                return False
            cursor = conn.execute(
                "INSERT OR IGNORE INTO supervisor_findings("
                "case_id, verdict, finding_json, delivered_to_lead_at_ns, "
                "created_at_ns, updated_at_ns"
                ") VALUES (?, ?, ?, NULL, ?, ?)",
                (case_id, finding["status"], encoded, now, now),
            )
            if finding["status"] == "no_issue":
                conn.execute(
                    "UPDATE supervisor_cases SET status = 'WAITING_FOR_EVIDENCE', "
                    "updated_at_ns = ? WHERE case_id = ? AND status = 'OPEN'",
                    (now, case_id),
                )
        return cursor.rowcount == 1

    def issue_findings_needing_delivery(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT f.finding_json, c.turn_id, c.work_item_id, "
                "c.work_item_revision, c.candidate_id FROM supervisor_findings f "
                "JOIN supervisor_cases c ON c.case_id = f.case_id "
                "WHERE f.verdict = 'issue' "
                "AND f.delivered_to_lead_at_ns IS NULL "
                "AND c.status != 'CLOSED' "
                "ORDER BY c.opened_event_seq, c.case_id LIMIT ?",
                (limit,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            finding = json.loads(row["finding_json"])
            finding["_case_context"] = {
                "turn_id": row["turn_id"],
                "work_item_id": row["work_item_id"],
                "work_item_revision": row["work_item_revision"],
                "candidate_id": row["candidate_id"],
            }
            result.append(finding)
        return result

    def mark_delivered_to_lead(self, case_id: str) -> bool:
        case_id = _required_text(case_id, "case_id")
        now = time.time_ns()
        with self._connect() as conn:
            case = conn.execute(
                "SELECT status FROM supervisor_cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if case is None or case["status"] == "CLOSED":
                return False
            finding = conn.execute(
                "SELECT verdict, delivered_to_lead_at_ns FROM supervisor_findings "
                "WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if finding is None or finding["verdict"] != "issue":
                raise RuntimeError("only persisted issue findings may be delivered to Lead")
            if finding["delivered_to_lead_at_ns"] is not None:
                return False
            conn.execute(
                "UPDATE supervisor_findings SET delivered_to_lead_at_ns = ?, "
                "updated_at_ns = ? WHERE case_id = ?",
                (now, now, case_id),
            )
            conn.execute(
                "UPDATE supervisor_cases SET status = 'WAITING_FOR_EVIDENCE', "
                "updated_at_ns = ? WHERE case_id = ? AND status != 'CLOSED'",
                (now, case_id),
            )
        return True


class HerdrControlPlane:
    def __init__(
        self,
        *,
        workspace_root: Path,
        state_db: Path,
        session: str = "qiqi-delegate",
        herdr_bin: str = "herdr",
        supervisor_home: Path | None = None,
        lead_model: str = DEFAULT_MODEL,
        supervisor_model: str = DEFAULT_MODEL,
    ):
        self.workspace_root = workspace_root.resolve()
        self.state_db = state_db.resolve()
        self.session = _required_text(session, "Herdr session")
        self.herdr_bin = _required_text(herdr_bin, "Herdr binary")
        self.store = SupervisorControlStore(self.state_db)
        self.supervisor_home = (
            supervisor_home.resolve()
            if supervisor_home is not None
            else default_supervisor_home(self.workspace_root)
        )
        self.lead_model = _required_text(lead_model, "Lead model")
        self.supervisor_model = _required_text(supervisor_model, "Supervisor model")
        self._prompt_lock = asyncio.Lock()
        self._managed_server: asyncio.subprocess.Process | None = None

    def _argv(self, *args: str) -> list[str]:
        return [self.herdr_bin, "--session", self.session, *args]

    async def _run(
        self,
        *args: str,
        check: bool = True,
    ) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *self._argv(*args),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        out_text = stdout.decode("utf-8", errors="replace")
        err_text = stderr.decode("utf-8", errors="replace")
        returncode = proc.returncode or 0
        if check and returncode != 0:
            detail = (err_text or out_text).strip()
            if len(detail) > 3000:
                detail = detail[-3000:]
            raise RuntimeError(
                f"Herdr command failed (exit={returncode}): {' '.join(args)}"
                + (f"; {detail}" if detail else "")
            )
        return returncode, out_text, err_text

    async def _run_json(self, *args: str) -> dict[str, Any]:
        _, stdout, _ = await self._run(*args)
        return _json_object(stdout, f"Herdr {' '.join(args)} response")

    async def _ensure_server(self) -> None:
        if shutil.which(self.herdr_bin) is None:
            raise RuntimeError(f"missing Herdr CLI: {self.herdr_bin}")
        returncode, _, _ = await self._run("status", "server", check=False)
        if returncode == 0:
            return
        self._managed_server = await asyncio.create_subprocess_exec(
            *self._argv("server"),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            returncode, _, _ = await self._run("status", "server", check=False)
            if returncode == 0:
                return
            if self._managed_server.returncode is not None:
                break
        raise RuntimeError(f"failed to start Herdr named session {self.session!r}")

    @staticmethod
    def _result(payload: dict[str, Any], key: str) -> dict[str, Any]:
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Herdr response has no result object")
        value = result.get(key)
        if not isinstance(value, dict):
            raise RuntimeError(f"Herdr response has no result.{key}")
        return value

    async def _agent_info(self, name: str) -> dict[str, Any] | None:
        returncode, stdout, _ = await self._run("agent", "get", name, check=False)
        if returncode != 0:
            return None
        try:
            payload = _json_object(stdout, f"Herdr agent get {name} response")
        except ValueError:
            return None
        result = payload.get("result")
        if not isinstance(result, dict):
            return None
        agent = result.get("agent")
        return agent if isinstance(agent, dict) else None

    @staticmethod
    def _agent_prompt_ready(info: dict[str, Any] | None) -> bool:
        if not isinstance(info, dict):
            return False
        status = info.get("agent_status")
        return (
            info.get("interactive_ready") is True
            and status in {"idle", "done", "working"}
            and info.get("launch_pending") is not True
        )

    @staticmethod
    def _agent_matches_pane(info: dict[str, Any] | None, pane_id: str) -> bool:
        return (
            isinstance(info, dict)
            and isinstance(info.get("pane_id"), str)
            and info.get("pane_id") == pane_id
        )

    async def _agent_exists(self, name: str) -> bool:
        return await self._agent_info(name) is not None

    async def _workspace_exists(self, workspace_id: str) -> bool:
        returncode, _, _ = await self._run(
            "workspace", "get", workspace_id, check=False
        )
        return returncode == 0

    async def _pane_exists(self, pane_id: str) -> bool:
        returncode, _, _ = await self._run("pane", "get", pane_id, check=False)
        return returncode == 0

    async def _discard_stale_control_plane(
        self,
        state: dict[str, Any],
        *,
        require_close_success: bool,
    ) -> None:
        workspace_id = _required_text(state.get("workspace_id"), "workspace_id")
        workspace_exists = await self._workspace_exists(workspace_id)
        if workspace_exists:
            close_code, _, close_err = await self._run(
                "workspace",
                "close",
                workspace_id,
                check=False,
            )
            if require_close_success and close_code != 0:
                raise RuntimeError(
                    "cannot replace stale slp-control topology because Herdr workspace "
                    f"close failed: {close_err.strip() or close_code}"
                )
            if close_code != 0:
                raise RuntimeError(
                    "cannot recover stale slp-control topology because Herdr workspace "
                    f"close failed: {close_err.strip() or close_code}"
                )
        self.store.clear_control_plane()

    async def _wait_agent_prompt_ready(
        self,
        name: str,
        *,
        timeout_ms: int = HERDR_AGENT_START_TIMEOUT_MS,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + (timeout_ms / 1000)
        last_info: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            last_info = await self._agent_info(name)
            if self._agent_prompt_ready(last_info):
                return last_info
            await asyncio.sleep(0.1)
        raise RuntimeError(
            f"Herdr named agent {name!r} exists but is not prompt-ready after "
            f"{timeout_ms}ms; last_info={last_info!r}"
        )

    def _prepare_supervisor_home(self) -> tuple[Path, str]:
        self.supervisor_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.supervisor_home, 0o700)
        except OSError:
            pass
        (self.supervisor_home / "AGENTS.md").write_text(
            SUPERVISOR_AGENTS,
            encoding="utf-8",
        )
        capture_dir = self.supervisor_home / "captures"
        capture_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(capture_dir, 0o700)
        except OSError:
            pass
        return capture_dir, uuid.uuid4().hex

    def _supervisor_hook_args(self, capture_dir: Path, nonce: str) -> list[str]:
        command = shlex.join(
            [
                sys.executable,
                str(RESULT_HOOK_PATH),
                "--adapter",
                "codex",
                "--sink",
                str(capture_dir.resolve()),
                "--nonce",
                nonce,
            ]
        )
        stop_value = (
            "[{hooks=[{type=\"command\",command="
            + json.dumps(command, ensure_ascii=False)
            + ",timeout=10}]}]"
        )
        hook_key = codex_session_hook_key()
        trusted_hash = codex_stop_hook_hash(command)
        state_value = (
            "{"
            + json.dumps(hook_key, ensure_ascii=False)
            + "={trusted_hash="
            + json.dumps(trusted_hash, ensure_ascii=False)
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

    def _lead_args(self) -> list[str]:
        return [
            "--dangerously-bypass-approvals-and-sandbox",
            "--model",
            self.lead_model,
            "-c",
            'model_reasoning_effort="medium"',
        ]

    def _supervisor_args(self, capture_dir: Path, nonce: str) -> list[str]:
        return [
            *self._supervisor_hook_args(capture_dir, nonce),
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "never",
            "--model",
            self.supervisor_model,
            "-c",
            'model_reasoning_effort="medium"',
            "-c",
            'web_search="disabled"',
        ]

    async def _start_agent(
        self,
        name: str,
        pane_id: str,
        args: list[str],
    ) -> None:
        existing = await self._agent_info(name)
        if existing is not None:
            if not self._agent_matches_pane(existing, pane_id):
                raise RuntimeError(
                    f"named agent topology mismatch for {name!r}: "
                    f"expected pane {pane_id!r}, got {existing.get('pane_id')!r}"
                )
            if self._agent_prompt_ready(existing):
                return
            ready = await self._wait_agent_prompt_ready(name)
            if not self._agent_matches_pane(ready, pane_id):
                raise RuntimeError(
                    f"named agent topology mismatch for {name!r} after readiness"
                )
            return

        await self._run(
            "agent",
            "start",
            name,
            "--kind",
            "codex",
            "--pane",
            pane_id,
            "--timeout",
            str(HERDR_AGENT_START_TIMEOUT_MS),
            "--",
            *args,
        )
        await self._wait_agent_prompt_ready(name)

    async def ensure_started(self) -> dict[str, Any]:
        await self._ensure_server()
        state = self.store.get_control_plane()
        if state is not None:
            identity_matches = (
                state.get("herdr_session") == self.session
                and state.get("lead_model") == self.lead_model
                and state.get("supervisor_model") == self.supervisor_model
            )
            if not identity_matches:
                stored_session = state.get("herdr_session")
                if stored_session in {"", self.session}:
                    await self._discard_stale_control_plane(
                        state,
                        require_close_success=True,
                    )
                else:
                    self.store.clear_control_plane()
                state = None

        if state is not None:
            workspace_ok = await self._workspace_exists(state["workspace_id"])
            lead_pane_ok = await self._pane_exists(state["lead_pane_id"])
            supervisor_pane_ok = await self._pane_exists(
                state["supervisor_pane_id"]
            )
            if not (workspace_ok and lead_pane_ok and supervisor_pane_ok):
                await self._discard_stale_control_plane(
                    state,
                    require_close_success=False,
                )
                state = None

        if state is not None:
            lead_info = await self._agent_info(state["lead_agent_name"])
            supervisor_info = await self._agent_info(state["supervisor_agent_name"])
            if (
                self._agent_prompt_ready(lead_info)
                and self._agent_prompt_ready(supervisor_info)
                and self._agent_matches_pane(lead_info, state["lead_pane_id"])
                and self._agent_matches_pane(
                    supervisor_info, state["supervisor_pane_id"]
                )
            ):
                return state
            try:
                await self._start_agent(
                    state["lead_agent_name"],
                    state["lead_pane_id"],
                    self._lead_args(),
                )
                await self._start_agent(
                    state["supervisor_agent_name"],
                    state["supervisor_pane_id"],
                    self._supervisor_args(
                        Path(state["supervisor_capture_dir"]),
                        state["supervisor_capture_nonce"],
                    ),
                )
            except RuntimeError as exc:
                if "agent_pane_not_found" not in str(exc):
                    raise RuntimeError(
                        "persisted slp-control topology could not be restored"
                    ) from exc
                await self._discard_stale_control_plane(
                    state,
                    require_close_success=False,
                )
                state = None
            else:
                return self.store.get_control_plane() or state

        capture_dir, nonce = self._prepare_supervisor_home()
        created = await self._run_json(
            "workspace",
            "create",
            "--cwd",
            str(self.workspace_root),
            "--label",
            CONTROL_ID,
            "--no-focus",
        )
        workspace = self._result(created, "workspace")
        root_pane = self._result(created, "root_pane")
        workspace_id = _required_text(workspace.get("workspace_id"), "workspace_id")
        lead_pane_id = _required_text(root_pane.get("pane_id"), "lead_pane_id")

        split = await self._run_json(
            "pane",
            "split",
            lead_pane_id,
            "--direction",
            "right",
            "--cwd",
            str(self.supervisor_home),
            "--no-focus",
        )
        supervisor_pane = self._result(split, "pane")
        supervisor_pane_id = _required_text(
            supervisor_pane.get("pane_id"),
            "supervisor_pane_id",
        )

        await self._start_agent(LEAD_AGENT_NAME, lead_pane_id, self._lead_args())
        await self._start_agent(
            SUPERVISOR_AGENT_NAME,
            supervisor_pane_id,
            self._supervisor_args(capture_dir, nonce),
        )
        return self.store.save_control_plane(
            workspace_id=workspace_id,
            lead_pane_id=lead_pane_id,
            supervisor_pane_id=supervisor_pane_id,
            herdr_session=self.session,
            lead_model=self.lead_model,
            supervisor_model=self.supervisor_model,
            supervisor_home=self.supervisor_home,
            supervisor_capture_dir=capture_dir,
            supervisor_capture_nonce=nonce,
        )

    @staticmethod
    def _clear_capture_dir(capture_dir: Path) -> None:
        capture_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in capture_dir.glob("event-*.json"):
            path.unlink()

    async def _captured_response(
        self,
        *,
        capture_dir: Path,
        nonce: str,
    ) -> str:
        deadline = time.monotonic() + SUPERVISOR_CAPTURE_WAIT_SECONDS
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            events = load_capture_events(capture_dir, nonce)
            session_ids = {
                event.get("session_id")
                for event in events
                if isinstance(event.get("session_id"), str)
                and event.get("session_id")
            }
            if len(session_ids) == 1:
                session_id = next(iter(session_ids))
                try:
                    resolution = resolve_capture_events(
                        events,
                        adapter="codex",
                        session_id=session_id,
                    )
                except RuntimeError as exc:
                    last_error = exc
                else:
                    if resolution.get("state") == "settled":
                        response = resolution.get("agent_response")
                        if isinstance(response, str) and response.strip():
                            return response
                    elif resolution.get("state") in {"failed", "capture_ambiguous"}:
                        raise RuntimeError(
                            "Supervisor semantic response capture did not settle cleanly"
                        )
            await asyncio.sleep(0.05)
        raise RuntimeError(
            "Supervisor semantic response was not captured by the native Stop hook"
        ) from last_error

    async def prompt_supervisor(self, packet: dict[str, Any]) -> dict[str, Any]:
        state = await self.ensure_started()
        case_id = _required_text(packet.get("case_id"), "AuditPacket case_id")
        capture_dir = Path(state["supervisor_capture_dir"])
        nonce = state["supervisor_capture_nonce"]

        async with self._prompt_lock:
            for attempt in range(2):
                self._clear_capture_dir(capture_dir)
                prompt = render_supervisor_prompt(packet)
                if attempt:
                    prompt = (
                        "Your previous final response did not match the required governance "
                        "JSON schema. Return only one valid JSON object with the exact fields "
                        "specified below. Do not perform any other action.\n\n" + prompt
                    )
                await self._run(
                    "agent",
                    "prompt",
                    state["supervisor_agent_name"],
                    prompt,
                    "--wait",
                    "--timeout",
                    str(SUPERVISOR_PROMPT_TIMEOUT_MS),
                )
                raw = await self._captured_response(
                    capture_dir=capture_dir,
                    nonce=nonce,
                )
                try:
                    return parse_supervisor_finding(
                        raw,
                        expected_case_id=case_id,
                    )
                except ValueError:
                    if attempt:
                        raise
            raise AssertionError("unreachable Supervisor prompt loop")

    async def wake_lead(self, finding: dict[str, Any]) -> None:
        state = await self.ensure_started()
        await self._run(
            "agent",
            "prompt",
            state["lead_agent_name"],
            render_lead_finding(finding),
        )


class AutonomousSupervisorRuntime:
    def __init__(
        self,
        *,
        state_db: Path,
        control_plane: HerdrControlPlane,
    ):
        self.store = SupervisorControlStore(state_db)
        self.control_plane = control_plane

    async def handle_pending_cases(self, *, limit: int = 20) -> dict[str, int]:
        await self.control_plane.ensure_started()
        reviewed = 0
        delivered = 0
        review_failures = 0
        delivery_failures = 0

        cases = self.store.pending_unreviewed_cases(limit=limit)
        for case in cases:
            try:
                finding = await self.control_plane.prompt_supervisor(
                    build_audit_packet(case)
                )
                if self.store.record_finding(finding):
                    reviewed += 1
            except (RuntimeError, ValueError):
                review_failures += 1

        findings = self.store.issue_findings_needing_delivery(limit=limit)
        for finding in findings:
            current = self.store.get_case(finding["case_id"])
            if current is None or current["status"] == "CLOSED":
                continue
            try:
                await self.control_plane.wake_lead(finding)
                if self.store.mark_delivered_to_lead(finding["case_id"]):
                    delivered += 1
            except (RuntimeError, ValueError):
                delivery_failures += 1

        return {
            "reviewed": reviewed,
            "delivered_to_lead": delivered,
            "review_attempted": len(cases),
            "delivery_attempted": len(findings),
            "review_failures": review_failures,
            "delivery_failures": delivery_failures,
        }
