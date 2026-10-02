#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - long-lived subscriber is POSIX-only today.
    fcntl = None  # type: ignore[assignment]

from core import SessionStore
from supervisor_control import (
    AutonomousSupervisorRuntime,
    HerdrControlPlane,
    default_herdr_session,
)

BROKER_ID = "slp-supervisor"
OPEN_CASE_STATUS = "OPEN"
CLOSED_CASE_STATUS = "CLOSED"
AUDIT_SIGNALS = frozenset({"REOPEN_REQUEST", "DEPENDENCY_REQUEST", "BLOCKED"})
CANDIDATE_RECONCILIATIONS = frozenset({"superseded", "abandoned", "revalidated"})
SIGNAL_DETAILS_MAX_CHARS = 2_000
BROKER_BATCH_LIMIT = 1_000
SUPERVISOR_BATCH_LIMIT = 20
HERDR_GLOBAL_SUBSCRIPTIONS = (
    "workspace.created",
    "workspace.updated",
    "workspace.closed",
    "tab.created",
    "tab.closed",
    "pane.created",
    "pane.closed",
    "pane.exited",
    "pane.agent_detected",
)
HERDR_SESSION_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class BrokerInstanceLock:
    """Process-lifetime non-blocking singleton lock for one Supervisor state DB."""

    def __init__(self, state_db: Path):
        self.state_db = state_db.resolve()
        self.path = self.state_db.with_name(
            self.state_db.name + ".supervisor-broker.lock"
        )
        self._handle = None

    def acquire(self) -> None:
        if fcntl is None:
            raise RuntimeError("Supervisor broker singleton lock requires POSIX fcntl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise RuntimeError(
                "another Supervisor broker already owns this state DB: "
                f"{self.state_db}"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()) + "\n")
        handle.flush()
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            assert fcntl is not None
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class HerdrSubscriptionError(RuntimeError):
    pass


class HerdrEventsLost(HerdrSubscriptionError):
    pass


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HerdrSubscriptionError("Herdr emitted invalid JSON") from exc
    if not isinstance(value, dict):
        raise HerdrSubscriptionError("Herdr emitted a non-object JSON message")
    return value


def _collect_pane_ids(value: Any) -> set[str]:
    pane_ids: set[str] = set()
    if isinstance(value, dict):
        pane_id = value.get("pane_id")
        if isinstance(pane_id, str) and pane_id.strip():
            pane_ids.add(pane_id.strip())
        for child in value.values():
            pane_ids.update(_collect_pane_ids(child))
    elif isinstance(value, list):
        for child in value:
            pane_ids.update(_collect_pane_ids(child))
    return pane_ids


def _herdr_event_name(message: dict[str, Any]) -> str | None:
    event = message.get("event")
    if isinstance(event, str) and event:
        return event
    data = message.get("data")
    if isinstance(data, dict):
        data_type = data.get("type")
        if isinstance(data_type, str) and data_type:
            return data_type
    return None


def resolve_herdr_socket(
    *,
    explicit_socket: Path | None = None,
    session: str | None = None,
    environ: dict[str, str] | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    if explicit_socket is not None:
        return explicit_socket.expanduser().resolve()

    override = env.get("HERDR_SOCKET_PATH")
    if isinstance(override, str) and override.strip():
        return Path(override).expanduser().resolve()

    selected = (
        session
        or env.get("HERDR_SESSION")
        or env.get("QIQI_HERDR_SESSION")
        or "qiqi-delegate"
    )
    selected = _required_text(selected, "Herdr session")
    if not HERDR_SESSION_RE.fullmatch(selected):
        raise ValueError("Herdr session contains unsupported characters")

    config_home = env.get("XDG_CONFIG_HOME")
    if isinstance(config_home, str) and config_home.strip():
        root = Path(config_home).expanduser()
    else:
        home = env.get("HOME")
        if not isinstance(home, str) or not home.strip():
            raise RuntimeError("cannot resolve Herdr socket without HOME or XDG_CONFIG_HOME")
        root = Path(home).expanduser() / ".config"
    herdr_root = root / "herdr"
    if selected == "default":
        return (herdr_root / "herdr.sock").resolve()
    return (herdr_root / "sessions" / selected / "herdr.sock").resolve()


class HerdrLifecycleSubscriber:
    """Long-lived Herdr event subscriber used only as a broker wakeup source.

    Herdr lifecycle events are transient and are never treated as SLP semantic truth.
    Every wakeup causes the broker to replay durable slp_events from SQLite.
    """

    def __init__(
        self,
        socket_path: Path,
        *,
        handshake_timeout_seconds: float = 10.0,
        event_idle_seconds: float = 30.0,
    ):
        if (
            isinstance(handshake_timeout_seconds, bool)
            or not isinstance(handshake_timeout_seconds, (int, float))
            or handshake_timeout_seconds <= 0
        ):
            raise ValueError("handshake_timeout_seconds must be a positive number")
        if (
            isinstance(event_idle_seconds, bool)
            or not isinstance(event_idle_seconds, (int, float))
            or event_idle_seconds <= 0
        ):
            raise ValueError("event_idle_seconds must be a positive number")
        self.socket_path = socket_path
        self.handshake_timeout_seconds = float(handshake_timeout_seconds)
        self.event_idle_seconds = float(event_idle_seconds)

    @staticmethod
    async def _send(
        writer: asyncio.StreamWriter,
        payload: dict[str, Any],
    ) -> None:
        writer.write(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )
        await writer.drain()

    @staticmethod
    async def _read(reader: asyncio.StreamReader) -> dict[str, Any]:
        raw = await reader.readline()
        if not raw:
            raise EOFError("Herdr event socket closed")
        return _json_object(raw.decode("utf-8"))

    async def _read_handshake(
        self,
        reader: asyncio.StreamReader,
        *,
        context: str,
    ) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(
                self._read(reader),
                timeout=self.handshake_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise HerdrSubscriptionError(
                f"{context} timed out after {self.handshake_timeout_seconds:g}s"
            ) from exc

    @staticmethod
    def _raise_error(message: dict[str, Any], *, context: str) -> None:
        error = message.get("error")
        if not isinstance(error, dict):
            return
        code = error.get("code")
        detail = error.get("message")
        if code == "events_lost":
            raise HerdrEventsLost(
                "Herdr lifecycle event history was lost; reconnect and replay SQLite events"
            )
        raise HerdrSubscriptionError(
            f"{context} failed"
            + (f": code={code}" if isinstance(code, str) and code else "")
            + (f"; {detail}" if isinstance(detail, str) and detail else "")
        )

    async def stream_once(
        self,
        *,
        yield_ready: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        if os.name == "nt":
            raise HerdrSubscriptionError(
                "Phase 2 raw Herdr subscriber currently requires a Unix-domain socket"
            )
        reader, writer = await asyncio.open_unix_connection(str(self.socket_path))
        snapshot_id = f"slp_snapshot_{uuid.uuid4().hex}"
        subscribe_id = f"slp_subscribe_{uuid.uuid4().hex}"
        try:
            await self._send(
                writer,
                {"id": snapshot_id, "method": "session.snapshot", "params": {}},
            )
            snapshot = await self._read_handshake(
                reader,
                context="Herdr session.snapshot",
            )
            self._raise_error(snapshot, context="Herdr session.snapshot")
            if snapshot.get("id") != snapshot_id:
                raise HerdrSubscriptionError(
                    "Herdr session.snapshot returned an unexpected request id"
                )
            pane_ids = sorted(_collect_pane_ids(snapshot.get("result")))

            subscriptions = [
                {"type": event_type} for event_type in HERDR_GLOBAL_SUBSCRIPTIONS
            ]
            subscriptions.extend(
                {
                    "type": "pane.agent_status_changed",
                    "pane_id": pane_id,
                }
                for pane_id in pane_ids
            )
            await self._send(
                writer,
                {
                    "id": subscribe_id,
                    "method": "events.subscribe",
                    "params": {"subscriptions": subscriptions},
                },
            )
            acknowledgement = await self._read_handshake(
                reader,
                context="Herdr events.subscribe",
            )
            self._raise_error(
                acknowledgement,
                context="Herdr events.subscribe",
            )
            if acknowledgement.get("id") != subscribe_id:
                raise HerdrSubscriptionError(
                    "Herdr events.subscribe returned an unexpected request id"
                )
            if yield_ready:
                # This synthetic local wakeup is emitted only after Herdr has
                # acknowledged the subscription. Callers can now perform a final
                # SQLite drain while every subsequent lifecycle wakeup is buffered
                # by the already-active subscription.
                yield {
                    "event": "subscription_started",
                    "data": {"type": "subscription_started"},
                }

            while True:
                try:
                    message = await asyncio.wait_for(
                        self._read(reader),
                        timeout=self.event_idle_seconds,
                    )
                except asyncio.TimeoutError:
                    # Herdr is only a wakeup source. A quiet socket must not suppress
                    # later SQLite semantics written by MCP tools or Lead actions.
                    yield {
                        "event": "subscription_idle",
                        "data": {"type": "subscription_idle"},
                    }
                    continue
                self._raise_error(message, context="Herdr event stream")
                yield message
                event_name = _herdr_event_name(message)
                if event_name in {
                    "pane_created",
                    "pane.created",
                    "pane_agent_detected",
                    "pane.agent_detected",
                }:
                    # Reconnect so the next subscription includes the new pane's
                    # agent-status stream. Durable SLP replay makes this lossless.
                    return
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass


class SupervisorBroker:
    """Deterministic SLP governance broker over durable semantic events."""

    def __init__(self, path: Path, *, broker_id: str = BROKER_ID):
        self.path = path
        self.broker_id = _required_text(broker_id, "broker_id")

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        SessionStore._ensure_schema(conn)
        return conn

    def _ensure_state(self, conn: sqlite3.Connection) -> None:
        now = time.time_ns()
        conn.execute(
            "INSERT OR IGNORE INTO supervisor_broker_state("
            "broker_id, last_processed_seq, health_status, last_error, "
            "last_error_at_ns, updated_at_ns"
            ") VALUES (?, 0, 'healthy', NULL, NULL, ?)",
            (self.broker_id, now),
        )

    def mark_retrying(self, error: BaseException) -> None:
        message = f"{type(error).__name__}: {error}"
        with self._connect() as conn:
            self._ensure_state(conn)
            now = time.time_ns()
            conn.execute(
                "UPDATE supervisor_broker_state SET health_status = 'retrying', "
                "last_error = ?, last_error_at_ns = ?, updated_at_ns = ? "
                "WHERE broker_id = ?",
                (message, now, now, self.broker_id),
            )

    def mark_healthy(self) -> None:
        with self._connect() as conn:
            self._ensure_state(conn)
            conn.execute(
                "UPDATE supervisor_broker_state SET health_status = 'healthy', "
                "last_error = NULL, last_error_at_ns = NULL, updated_at_ns = ? "
                "WHERE broker_id = ?",
                (time.time_ns(), self.broker_id),
            )

    def health_state(self) -> dict[str, Any]:
        with self._connect() as conn:
            self._ensure_state(conn)
            row = conn.execute(
                "SELECT health_status, last_error, last_error_at_ns, updated_at_ns "
                "FROM supervisor_broker_state WHERE broker_id = ?",
                (self.broker_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Supervisor broker state was not persisted")
        return dict(row)

    def last_processed_seq(self) -> int:
        with self._connect() as conn:
            self._ensure_state(conn)
            row = conn.execute(
                "SELECT last_processed_seq FROM supervisor_broker_state "
                "WHERE broker_id = ?",
                (self.broker_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Supervisor broker state was not persisted")
        return int(row["last_processed_seq"])

    def list_cases(self, *, include_closed: bool = True) -> list[dict[str, Any]]:
        with self._connect() as conn:
            query = "SELECT * FROM supervisor_cases"
            params: tuple[Any, ...] = ()
            if not include_closed:
                query += " WHERE status != 'CLOSED'"
            query += " ORDER BY opened_event_seq, case_id"
            rows = conn.execute(query, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            result.append(item)
        return result

    @staticmethod
    def _fingerprint(rule: str, subject_key: str) -> str:
        encoded = f"{rule}\0{subject_key}".encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _open_case(
        self,
        conn: sqlite3.Connection,
        *,
        event: dict[str, Any],
        rule: str,
        subject_key: str,
        details: dict[str, Any],
        turn_id: str | None = None,
        work_item_id: str | None = None,
        work_item_revision: int | None = None,
        candidate_id: str | None = None,
    ) -> bool:
        now = time.time_ns()
        fingerprint = self._fingerprint(rule, subject_key)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO supervisor_cases("
            "case_id, rule, status, opened_event_seq, closed_event_seq, "
            "finding_fingerprint, subject_key, turn_id, work_item_id, "
            "work_item_revision, candidate_id, details_json, created_at_ns, updated_at_ns"
            ") VALUES (?, ?, 'OPEN', ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                rule,
                int(event["seq"]),
                fingerprint,
                subject_key,
                turn_id,
                work_item_id,
                work_item_revision,
                candidate_id,
                json.dumps(
                    details,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                    allow_nan=False,
                ),
                now,
                now,
            ),
        )
        return cursor.rowcount == 1

    @staticmethod
    def _close_cases(
        conn: sqlite3.Connection,
        *,
        event_seq: int,
        predicate: Callable[[dict[str, Any]], bool],
    ) -> int:
        rows = conn.execute(
            "SELECT * FROM supervisor_cases WHERE status != 'CLOSED' "
            "ORDER BY opened_event_seq, case_id"
        ).fetchall()
        closed = 0
        now = time.time_ns()
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item["details_json"])
            if not predicate(item):
                continue
            cursor = conn.execute(
                "UPDATE supervisor_cases SET status = 'CLOSED', closed_event_seq = ?, "
                "updated_at_ns = ? WHERE case_id = ? AND status != 'CLOSED'",
                (event_seq, now, item["case_id"]),
            )
            closed += cursor.rowcount
        return closed

    @staticmethod
    def _lead_disposition(
        conn: sqlite3.Connection, turn_id: str | None
    ) -> dict[str, Any] | None:
        if not isinstance(turn_id, str) or not turn_id:
            return None
        row = conn.execute(
            "SELECT * FROM lead_dispositions WHERE turn_id = ?",
            (turn_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _normalize_signal(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip().upper()
        if normalized == "RUNTIME_BLOCKED":
            return "BLOCKED"
        return normalized

    @staticmethod
    def _bounded_signal_details(value: Any) -> tuple[str | None, bool]:
        if not isinstance(value, str) or not value.strip():
            return None, False
        cleaned = value.strip()
        if len(cleaned) <= SIGNAL_DETAILS_MAX_CHARS:
            return cleaned, False
        return cleaned[:SIGNAL_DETAILS_MAX_CHARS], True

    @staticmethod
    def _normalize_scope_item(value: str) -> str:
        item = value.replace("\\", "/").strip()
        while item.startswith("./"):
            item = item[2:]
        if item != "/":
            item = item.rstrip("/")
        return item or "."

    @classmethod
    def _scope_items_overlap(cls, left: str, right: str) -> bool:
        a = cls._normalize_scope_item(left)
        b = cls._normalize_scope_item(right)
        if a in {"*", ".", "/"} or b in {"*", ".", "/"}:
            return True
        if a == b:
            return True
        return a.startswith(b + "/") or b.startswith(a + "/")

    @classmethod
    def _scopes_overlap(cls, left: list[str], right: list[str]) -> bool:
        return any(
            cls._scope_items_overlap(a, b)
            for a in left
            for b in right
        )

    @classmethod
    def _overlap_pairs(
        cls,
        left: list[str],
        right: list[str],
        *,
        limit: int = 20,
    ) -> tuple[list[dict[str, str]], bool]:
        pairs: list[dict[str, str]] = []
        truncated = False
        for left_item in left:
            for right_item in right:
                if not cls._scope_items_overlap(left_item, right_item):
                    continue
                if len(pairs) >= limit:
                    truncated = True
                    return pairs, truncated
                pairs.append({"left": left_item, "right": right_item})
        return pairs, truncated

    @staticmethod
    def _scope_payload(payload: dict[str, Any]) -> list[str] | None:
        scope = payload.get("scope")
        if not isinstance(scope, list) or not scope:
            return None
        cleaned: list[str] = []
        for item in scope:
            if not isinstance(item, str) or not item.strip():
                return None
            cleaned.append(item.strip())
        return cleaned

    def _process_peer_response(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        opened = 0
        closed = 0
        turn_id = event.get("turn_id")
        if isinstance(turn_id, str) and turn_id:
            if self._lead_disposition(conn, turn_id) is None:
                opened += int(
                    self._open_case(
                        conn,
                        event=event,
                        rule="R1",
                        subject_key=f"turn:{turn_id}",
                        details={"turn_id": turn_id},
                        turn_id=turn_id,
                        work_item_id=event.get("work_item_id"),
                        work_item_revision=event.get("work_item_revision"),
                        candidate_id=event.get("candidate_id"),
                    )
                )

        session_id = event.get("session_id")
        if isinstance(session_id, str) and session_id:
            closed += self._close_cases(
                conn,
                event_seq=int(event["seq"]),
                predicate=lambda case: (
                    case["rule"] == "R4"
                    and case["details"].get("runtime_blocked") is True
                    and case["details"].get("session_id") == session_id
                ),
            )

        work_item_id = event.get("work_item_id")
        revision = event.get("work_item_revision")
        if (
            isinstance(work_item_id, str)
            and work_item_id
            and isinstance(revision, int)
        ):
            latest_revision = conn.execute(
                "SELECT work_item_revision FROM slp_events "
                "WHERE event_type = 'work_item.revision_changed' "
                "AND work_item_id = ? AND seq <= ? "
                "ORDER BY seq DESC LIMIT 1",
                (work_item_id, int(event["seq"])),
            ).fetchone()
            if (
                latest_revision is not None
                and isinstance(latest_revision["work_item_revision"], int)
                and int(latest_revision["work_item_revision"]) > revision
                and isinstance(turn_id, str)
                and turn_id
            ):
                current_revision = int(latest_revision["work_item_revision"])
                opened += int(
                    self._open_case(
                        conn,
                        event=event,
                        rule="R5",
                        subject_key=f"turn:{turn_id}:revision:{current_revision}",
                        details={
                            "turn_id": turn_id,
                            "stale_revision": revision,
                            "current_revision": current_revision,
                        },
                        turn_id=turn_id,
                        work_item_id=work_item_id,
                        work_item_revision=current_revision,
                        candidate_id=event.get("candidate_id"),
                    )
                )

        return opened, closed

    def _process_dependency_consumed(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        payload = event["payload"]
        source_turn_id = payload.get("source_turn_id")
        if not isinstance(source_turn_id, str) or not source_turn_id.strip():
            source_turn_id = None
        disposition = None
        if source_turn_id:
            disposition = conn.execute(
                "SELECT * FROM lead_dispositions "
                "WHERE turn_id = ? AND event_seq < ? "
                "ORDER BY event_seq DESC LIMIT 1",
                (source_turn_id, int(event["seq"])),
            ).fetchone()
        if disposition is not None and disposition["action"] == "accept":
            return 0, 0

        source_event = None
        if source_turn_id:
            source_event = conn.execute(
                "SELECT work_item_id, work_item_revision, candidate_id "
                "FROM slp_events WHERE event_type = 'peer.response' AND turn_id = ? "
                "ORDER BY seq DESC LIMIT 1",
                (source_turn_id,),
            ).fetchone()

        opened = self._open_case(
            conn,
            event=event,
            rule="R2",
            subject_key=(
                f"source-turn:{source_turn_id}:consume-event:{event['seq']}"
                if source_turn_id
                else f"event:{event['seq']}"
            ),
            details={
                "source_turn_id": source_turn_id,
                "consumer_turn_id": event.get("turn_id"),
                "consumer_repository": event.get("repository"),
                "consumer_graph_run_id": event.get("graph_run_id"),
                "consumer_node_id": event.get("node_id"),
                "consumer_work_item_id": event.get("work_item_id"),
                "consumer_work_item_revision": event.get("work_item_revision"),
                "consumption_event_seq": int(event["seq"]),
                "accepted_before_consumption": False,
                "prior_disposition_action": (
                    disposition["action"] if disposition is not None else None
                ),
                "prior_disposition_event_seq": (
                    int(disposition["event_seq"]) if disposition is not None else None
                ),
            },
            turn_id=source_turn_id,
            work_item_id=(
                source_event["work_item_id"]
                if source_event is not None
                else event.get("work_item_id")
            ),
            work_item_revision=(
                source_event["work_item_revision"]
                if source_event is not None
                else event.get("work_item_revision")
            ),
            candidate_id=(
                source_event["candidate_id"]
                if source_event is not None
                else event.get("candidate_id")
            ),
        )
        return int(opened), 0

    def _process_dependency_consumption_resolved(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        payload = event["payload"]
        consumption_event_seq = payload.get("consumption_event_seq")
        if (
            isinstance(consumption_event_seq, bool)
            or not isinstance(consumption_event_seq, int)
            or consumption_event_seq <= 0
        ):
            return 0, 0
        closed = self._close_cases(
            conn,
            event_seq=int(event["seq"]),
            predicate=lambda case: (
                case["rule"] == "R2"
                and case["details"].get("consumption_event_seq")
                == consumption_event_seq
            ),
        )
        return 0, closed

    def _process_write_scope_claim(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        payload = event["payload"]
        claim_id = payload.get("claim_id")
        owner = payload.get("owner")
        scope = self._scope_payload(payload)
        repository = event.get("repository")
        if (
            not isinstance(claim_id, str)
            or not claim_id.strip()
            or not isinstance(owner, str)
            or not owner.strip()
            or scope is None
            or not isinstance(repository, str)
            or not repository
        ):
            opened = self._open_case(
                conn,
                event=event,
                rule="R3",
                subject_key=f"malformed-claim-event:{event['seq']}",
                details={"reason": "write_scope.claimed lacks claim_id/owner/scope/repository"},
                work_item_id=event.get("work_item_id"),
                work_item_revision=event.get("work_item_revision"),
            )
            return int(opened), 0

        claim_id = claim_id.strip()
        owner = owner.strip()
        now = time.time_ns()
        conn.execute(
            "INSERT OR IGNORE INTO write_scope_claims("
            "claim_id, claimed_event_seq, released_event_seq, repository, owner, "
            "scope_json, active, created_at_ns, updated_at_ns"
            ") VALUES (?, ?, NULL, ?, ?, ?, 1, ?, ?)",
            (
                claim_id,
                int(event["seq"]),
                repository,
                owner,
                json.dumps(scope, ensure_ascii=False, separators=(",", ":")),
                now,
                now,
            ),
        )
        other_rows = conn.execute(
            "SELECT * FROM write_scope_claims "
            "WHERE repository = ? AND active = 1 AND claim_id != ?",
            (repository, claim_id),
        ).fetchall()
        opened = 0
        for row in other_rows:
            other = dict(row)
            other_scope = json.loads(other["scope_json"])
            if not self._scopes_overlap(scope, other_scope):
                continue
            pair = sorted([claim_id, other["claim_id"]])
            overlap_pairs, overlap_pairs_truncated = self._overlap_pairs(
                scope, other_scope
            )
            opened += int(
                self._open_case(
                    conn,
                    event=event,
                    rule="R3",
                    subject_key=f"claims:{pair[0]}:{pair[1]}",
                    details={
                        "claim_ids": pair,
                        "repository": repository,
                        "overlap": True,
                        "overlap_pairs": overlap_pairs,
                        "overlap_pairs_truncated": overlap_pairs_truncated,
                    },
                    work_item_id=event.get("work_item_id"),
                    work_item_revision=event.get("work_item_revision"),
                )
            )
        return opened, 0

    def _process_write_scope_release(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        claim_id = event["payload"].get("claim_id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            return 0, 0
        claim_id = claim_id.strip()
        now = time.time_ns()
        conn.execute(
            "UPDATE write_scope_claims SET active = 0, released_event_seq = ?, "
            "updated_at_ns = ? WHERE claim_id = ? AND active = 1",
            (int(event["seq"]), now, claim_id),
        )
        closed = self._close_cases(
            conn,
            event_seq=int(event["seq"]),
            predicate=lambda case: (
                case["rule"] == "R3"
                and claim_id in case["details"].get("claim_ids", [])
            ),
        )
        return 0, closed

    def _process_peer_signal(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        raw_signal = event["payload"].get("signal")
        signal = self._normalize_signal(raw_signal)
        if signal not in AUDIT_SIGNALS:
            return 0, 0
        turn_id = event.get("turn_id")
        disposition = self._lead_disposition(conn, turn_id)
        if disposition is not None and disposition["action"] != "defer":
            return 0, 0
        subject = (
            f"turn:{turn_id}:signal:{signal}"
            if isinstance(turn_id, str) and turn_id
            else f"event:{event['seq']}:signal:{signal}"
        )
        signal_details, details_truncated = self._bounded_signal_details(
            event["payload"].get("details")
        )
        details: dict[str, Any] = {
            "turn_id": turn_id,
            "signal": signal,
            "session_id": event.get("session_id"),
            "runtime_blocked": (
                isinstance(raw_signal, str)
                and raw_signal.strip().lower() == "runtime_blocked"
            ),
        }
        if signal_details is not None:
            details["signal_details"] = signal_details
            details["signal_details_truncated"] = details_truncated
        opened = self._open_case(
            conn,
            event=event,
            rule="R4",
            subject_key=subject,
            details=details,
            turn_id=turn_id if isinstance(turn_id, str) else None,
            work_item_id=event.get("work_item_id"),
            work_item_revision=event.get("work_item_revision"),
            candidate_id=event.get("candidate_id"),
        )
        return int(opened), 0

    def _process_peer_signal_resolved(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        turn_id = event.get("turn_id")
        signal = self._normalize_signal(event["payload"].get("signal"))
        if (
            not isinstance(turn_id, str)
            or not turn_id
            or signal not in AUDIT_SIGNALS
        ):
            return 0, 0
        closed = self._close_cases(
            conn,
            event_seq=int(event["seq"]),
            predicate=lambda case: (
                case["rule"] == "R4"
                and case.get("turn_id") == turn_id
                and case["details"].get("signal") == signal
            ),
        )
        return 0, closed

    def _process_work_item_revision(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        work_item_id = event.get("work_item_id")
        current_revision = event.get("work_item_revision")
        if (
            not isinstance(work_item_id, str)
            or not work_item_id
            or not isinstance(current_revision, int)
        ):
            return 0, 0
        stale_rows = conn.execute(
            "SELECT * FROM slp_events "
            "WHERE event_type = 'peer.response' AND work_item_id = ? "
            "AND seq < ? AND work_item_revision < ? "
            "ORDER BY seq ASC",
            (work_item_id, int(event["seq"]), current_revision),
        ).fetchall()
        opened = 0
        for stale in stale_rows:
            stale_event = dict(stale)
            turn_id = stale_event.get("turn_id")
            if not isinstance(turn_id, str) or not turn_id:
                continue

            reconciliation_rows = conn.execute(
                "SELECT work_item_revision, payload_json FROM slp_events "
                "WHERE event_type = 'candidate.reconciled' AND turn_id = ? "
                "AND work_item_id = ? AND seq < ? ORDER BY seq DESC",
                (turn_id, work_item_id, int(event["seq"])),
            ).fetchall()
            reconciled = False
            for reconciliation in reconciliation_rows:
                payload = json.loads(reconciliation["payload_json"])
                resolution = payload.get("resolution")
                if resolution in {"superseded", "abandoned"}:
                    reconciled = True
                    break
                if (
                    resolution == "revalidated"
                    and isinstance(reconciliation["work_item_revision"], int)
                    and int(reconciliation["work_item_revision"]) >= current_revision
                ):
                    reconciled = True
                    break
                # A lower-revision revalidation does not make this candidate current.
                break
            if reconciled:
                continue

            opened += int(
                self._open_case(
                    conn,
                    event=event,
                    rule="R5",
                    subject_key=f"turn:{turn_id}:revision:{current_revision}",
                    details={
                        "turn_id": turn_id,
                        "stale_revision": stale_event.get("work_item_revision"),
                        "current_revision": current_revision,
                    },
                    turn_id=turn_id,
                    work_item_id=work_item_id,
                    work_item_revision=current_revision,
                    candidate_id=stale_event.get("candidate_id"),
                )
            )
        return opened, 0

    def _process_candidate_reconciled(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        payload = event["payload"]
        stale_turn_id = payload.get("stale_turn_id")
        resolution = payload.get("resolution")
        revision = event.get("work_item_revision")
        work_item_id = event.get("work_item_id")
        if (
            not isinstance(stale_turn_id, str)
            or not stale_turn_id
            or resolution not in CANDIDATE_RECONCILIATIONS
            or not isinstance(work_item_id, str)
            or not work_item_id
            or not isinstance(revision, int)
        ):
            return 0, 0
        closed = self._close_cases(
            conn,
            event_seq=int(event["seq"]),
            predicate=lambda case: (
                case["rule"] == "R5"
                and case.get("turn_id") == stale_turn_id
                and case.get("work_item_id") == work_item_id
                and isinstance(case.get("work_item_revision"), int)
                and revision >= int(case["work_item_revision"])
            ),
        )
        return 0, closed

    def _process_lead_disposition(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        turn_id = event.get("turn_id")
        if not isinstance(turn_id, str) or not turn_id:
            return 0, 0
        disposition = self._lead_disposition(conn, turn_id)
        action = (
            disposition["action"]
            if disposition is not None
            else event["payload"].get("action")
        )
        closed = self._close_cases(
            conn,
            event_seq=int(event["seq"]),
            predicate=lambda case: (
                (case["rule"] == "R1" and case.get("turn_id") == turn_id)
                or (
                    case["rule"] == "R4"
                    and action != "defer"
                    and case.get("turn_id") == turn_id
                )
                or (
                    case["rule"] == "R5"
                    and action in {"reject", "repair", "resolve"}
                    and case.get("turn_id") == turn_id
                )
            ),
        )
        return 0, closed

    def _apply_event(
        self,
        conn: sqlite3.Connection,
        event: dict[str, Any],
    ) -> tuple[int, int]:
        event_type = event["event_type"]
        if event_type == "peer.response":
            return self._process_peer_response(conn, event)
        if event_type == "lead.disposition":
            return self._process_lead_disposition(conn, event)
        if event_type == "candidate.reconciled":
            return self._process_candidate_reconciled(conn, event)
        if event_type == "dependency.consumed":
            return self._process_dependency_consumed(conn, event)
        if event_type == "dependency.consumption_resolved":
            return self._process_dependency_consumption_resolved(conn, event)
        if event_type == "write_scope.claimed":
            return self._process_write_scope_claim(conn, event)
        if event_type == "write_scope.released":
            return self._process_write_scope_release(conn, event)
        if event_type == "peer.signal":
            return self._process_peer_signal(conn, event)
        if event_type == "peer.signal_resolved":
            return self._process_peer_signal_resolved(conn, event)
        if event_type == "work_item.revision_changed":
            return self._process_work_item_revision(conn, event)
        return 0, 0

    def process_pending(self, *, limit: int = 1000) -> dict[str, int]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer between 1 and 1000")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_state(conn)
            state = conn.execute(
                "SELECT last_processed_seq FROM supervisor_broker_state "
                "WHERE broker_id = ?",
                (self.broker_id,),
            ).fetchone()
            if state is None:
                raise RuntimeError("Supervisor broker cursor is unavailable")
            start_seq = int(state["last_processed_seq"])
            rows = conn.execute(
                "SELECT * FROM slp_events WHERE seq > ? ORDER BY seq ASC LIMIT ?",
                (start_seq, limit),
            ).fetchall()

            opened = 0
            closed = 0
            last_seq = start_seq
            for row in rows:
                event = dict(row)
                event["payload"] = json.loads(event.pop("payload_json"))
                event_opened, event_closed = self._apply_event(conn, event)
                opened += event_opened
                closed += event_closed
                last_seq = int(event["seq"])
                conn.execute(
                    "UPDATE supervisor_broker_state SET last_processed_seq = ?, "
                    "updated_at_ns = ? WHERE broker_id = ?",
                    (last_seq, time.time_ns(), self.broker_id),
                )

        return {
            "from_seq": start_seq,
            "last_processed_seq": last_seq,
            "processed": len(rows),
            "opened": opened,
            "closed": closed,
        }


def default_workspace_root() -> Path:
    workspace_root = os.environ.get("QIQI_WORKSPACE_ROOT")
    return (
        Path(workspace_root).resolve()
        if isinstance(workspace_root, str) and workspace_root.strip()
        else Path(__file__).resolve().parents[2]
    )


def default_state_db() -> Path:
    return default_workspace_root() / ".qiqi" / "state" / "qiqi_delegate.sqlite3"


async def _drain_durable(
    broker: SupervisorBroker,
    runtime: AutonomousSupervisorRuntime,
) -> dict[str, Any]:
    broker_totals = {"processed": 0, "opened": 0, "closed": 0}
    supervisor_totals = {
        "reviewed": 0,
        "delivered_to_lead": 0,
        "review_attempted": 0,
        "delivery_attempted": 0,
        "review_failures": 0,
        "delivery_failures": 0,
    }
    last_broker_result: dict[str, int] | None = None

    def accumulate_broker(result: dict[str, int]) -> None:
        nonlocal last_broker_result
        last_broker_result = result
        for key in broker_totals:
            broker_totals[key] += int(result[key])

    def accumulate_supervisor(result: dict[str, Any]) -> None:
        for key in supervisor_totals:
            supervisor_totals[key] += int(result[key])

    def raise_supervisor_failure(result: dict[str, Any]) -> None:
        if not (result["review_failures"] or result["delivery_failures"]):
            return
        detail = result.get("last_error")
        if isinstance(detail, str) and detail:
            raise RuntimeError(
                "Supervisor processing left retryable case/delivery failures: "
                + detail
            )
        raise RuntimeError(
            "Supervisor processing left retryable case/delivery failures"
        )

    async def replay_to_quiescence() -> None:
        while True:
            result = broker.process_pending(limit=BROKER_BATCH_LIMIT)
            accumulate_broker(result)
            if result["processed"] < BROKER_BATCH_LIMIT:
                return

    while True:
        # Always materialize every durable closure before review.
        await replay_to_quiescence()

        # Review and delivery are separate phases. A Lead disposition can arrive while
        # prompt_supervisor is awaiting the model, so replay again after review before
        # selecting any issue finding for delivery.
        review_result = await runtime.handle_pending_cases(
            limit=SUPERVISOR_BATCH_LIMIT,
            review=True,
            deliver=False,
        )
        accumulate_supervisor(review_result)
        review_failed = bool(review_result["review_failures"])
        review_error = review_result.get("last_error")

        await replay_to_quiescence()

        # Persisted successful findings must still reach Lead even when another
        # case in the same review batch failed. Surface the retryable review error
        # only after delivery has had a chance to make independent progress.
        delivery_result = await runtime.handle_pending_cases(
            limit=SUPERVISOR_BATCH_LIMIT,
            review=False,
            deliver=True,
            before_delivery=replay_to_quiescence,
        )
        accumulate_supervisor(delivery_result)
        if delivery_result["delivery_failures"]:
            raise_supervisor_failure(delivery_result)
        if review_failed:
            detail = (
                review_error
                if isinstance(review_error, str) and review_error
                else "review batch contained one or more retryable failures"
            )
            raise RuntimeError(
                "Supervisor processing left retryable case/delivery failures: "
                + detail
            )

        # Delivery may itself race with newly persisted semantic evidence. Probe and
        # loop through a full replay before doing more review work.
        probe = broker.process_pending(limit=BROKER_BATCH_LIMIT)
        accumulate_broker(probe)
        if probe["processed"] != 0:
            continue

        if (
            review_result["review_attempted"] >= SUPERVISOR_BATCH_LIMIT
            or delivery_result["delivery_attempted"] >= SUPERVISOR_BATCH_LIMIT
        ):
            continue

        broker.mark_healthy()
        assert last_broker_result is not None
        return {
            "broker": {
                **broker_totals,
                "from_seq": last_broker_result["from_seq"],
                "last_processed_seq": last_broker_result["last_processed_seq"],
            },
            "supervisor": supervisor_totals,
            "health": broker.health_state(),
        }


def _mark_retrying_best_effort(
    broker: SupervisorBroker,
    error: BaseException,
) -> None:
    try:
        broker.mark_retrying(error)
    except sqlite3.DatabaseError as health_error:
        print(
            "[slp-supervisor] could not persist retry health after SQLite failure: "
            f"{type(health_error).__name__}: {health_error}",
            file=sys.stderr,
            flush=True,
        )


async def serve(
    broker: SupervisorBroker,
    subscriber: HerdrLifecycleSubscriber,
    runtime: AutonomousSupervisorRuntime,
    *,
    reconnect_seconds: float = 1.0,
) -> None:
    if reconnect_seconds <= 0:
        raise ValueError("reconnect_seconds must be positive")

    # Durable SQLite truth is drained once before transport setup, then again
    # after Herdr has acknowledged the subscription. The second drain closes the
    # commit->subscribe race: any lifecycle wakeup produced during that drain is
    # already buffered by the active subscription.
    # Any control-plane/reasoning failure is retryable: it must not terminate the daemon.
    while True:
        try:
            await _drain_durable(broker, runtime)
            stream = subscriber.stream_once(yield_ready=True)
            ready = await anext(stream)
            if _herdr_event_name(ready) != "subscription_started":
                raise HerdrSubscriptionError(
                    "Herdr subscriber did not confirm subscription readiness"
                )
            await _drain_durable(broker, runtime)
            async for _wakeup in stream:
                await _drain_durable(broker, runtime)
        except (
            EOFError,
            OSError,
            sqlite3.DatabaseError,
            HerdrSubscriptionError,
            RuntimeError,
            ValueError,
        ) as exc:
            _mark_retrying_best_effort(broker, exc)
            print(
                "[slp-supervisor] retrying after supervision failure: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            await asyncio.sleep(reconnect_seconds)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic SLP Supervisor broker. Herdr events are wakeups only; "
            "semantic governance truth is replayed from qiqi_delegate.sqlite3."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--once",
        action="store_true",
        help="process pending SQLite semantic events and exit without starting agents",
    )
    mode.add_argument(
        "--supervise-once",
        action="store_true",
        help="replay semantic events, ensure the persistent control plane, review/deliver once, and exit",
    )
    parser.add_argument("--db", type=Path, default=None, help="override qiqi_delegate.sqlite3")
    parser.add_argument("--session", default=None, help="Herdr named session")
    parser.add_argument("--socket-path", type=Path, default=None, help="explicit Herdr socket path")
    parser.add_argument("--supervisor-home", type=Path, default=None)
    parser.add_argument("--reconnect-seconds", type=float, default=1.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    workspace_root = default_workspace_root()
    db_path = (args.db or default_state_db()).expanduser().resolve()
    broker = SupervisorBroker(db_path)
    instance_lock = BrokerInstanceLock(db_path)
    instance_lock.acquire()
    if args.once:
        try:
            print(json.dumps(broker.process_pending(), sort_keys=True))
            return 0
        finally:
            instance_lock.release()

    session = (
        args.session
        or os.environ.get("QIQI_HERDR_SESSION")
        or os.environ.get("HERDR_SESSION")
        or default_herdr_session(workspace_root)
    )
    control_plane = HerdrControlPlane(
        workspace_root=workspace_root,
        state_db=db_path,
        session=session,
        herdr_bin=os.environ.get("QIQI_HERDR_BIN", "herdr"),
        supervisor_home=(
            args.supervisor_home.expanduser().resolve()
            if args.supervisor_home is not None
            else None
        ),
    )
    runtime = AutonomousSupervisorRuntime(
        state_db=db_path,
        control_plane=control_plane,
    )
    if args.supervise_once:
        try:
            result = asyncio.run(_drain_durable(broker, runtime))
        except (RuntimeError, ValueError, OSError, sqlite3.DatabaseError) as exc:
            _mark_retrying_best_effort(broker, exc)
            print(
                "[slp-supervisor] supervise-once failed: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            raise
        print(json.dumps(result, sort_keys=True))
        instance_lock.release()
        return 0

    socket_path = resolve_herdr_socket(
        explicit_socket=args.socket_path,
        session=session,
    )
    subscriber = HerdrLifecycleSubscriber(socket_path)
    try:
        asyncio.run(
            serve(
                broker,
                subscriber,
                runtime,
                reconnect_seconds=args.reconnect_seconds,
            )
        )
    except KeyboardInterrupt:
        return 130
    finally:
        instance_lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
