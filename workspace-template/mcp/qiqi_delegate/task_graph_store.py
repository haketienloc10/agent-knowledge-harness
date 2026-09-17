from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from task_graph import TaskGraph
from task_graph_scheduler import GraphSnapshot, NodeState, derive_graph_state

ATTEMPT_TERMINAL_STATES = frozenset({"settled", "failed", "blocked"})
ATTEMPT_STATES = frozenset({"running", *ATTEMPT_TERMINAL_STATES})


def new_graph_run_id() -> str:
    return str(uuid.uuid4())


def new_wave_id() -> str:
    return str(uuid.uuid4())


def new_attempt_id() -> str:
    return str(uuid.uuid4())


def _required_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _optional_id(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _required_id(value, label)


def _result_json(result: Any) -> str:
    if not isinstance(result, dict):
        raise ValueError("normalized node result must be an object")
    try:
        return json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("normalized node result must be JSON-serializable") from exc


def _validated_states(snapshot: GraphSnapshot) -> dict[str, NodeState]:
    # Reuse the Phase-3 state machine as the canonical NodeState/snapshot validator.
    derive_graph_state(snapshot)
    return {state.node_id: state for state in snapshot.node_states}


class GraphRuntimeStore:
    """Durable execution state for TaskGraph runs.

    This store intentionally does not persist authored TaskGraph/TaskPacket semantics.
    Callers supply the current TaskGraph when reconstructing a GraphSnapshot, while
    `.qiqi/state` owns run/wave/attempt/session/result execution facts.
    """

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
            CREATE TABLE IF NOT EXISTS graph_runs (
                graph_run_id TEXT PRIMARY KEY,
                current_wave_id TEXT,
                created_at_ns INTEGER NOT NULL,
                updated_at_ns INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS graph_node_states (
                graph_run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                semantic_state TEXT NOT NULL
                    CHECK (semantic_state IN ('pending', 'satisfied', 'blocked', 'cancelled')),
                runtime_state TEXT NOT NULL
                    CHECK (runtime_state IN ('idle', 'running', 'settled', 'failed', 'blocked', 'awaiting_review')),
                current_attempt_id TEXT,
                session_id TEXT,
                turn_id TEXT,
                updated_at_ns INTEGER NOT NULL,
                PRIMARY KEY (graph_run_id, node_id),
                FOREIGN KEY (graph_run_id) REFERENCES graph_runs(graph_run_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS graph_attempts (
                attempt_id TEXT PRIMARY KEY,
                graph_run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                wave_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
                runtime_state TEXT NOT NULL
                    CHECK (runtime_state IN ('running', 'settled', 'failed', 'blocked')),
                resume_session INTEGER NOT NULL
                    CHECK (resume_session IN (0, 1)),
                session_id TEXT,
                turn_id TEXT,
                result_json TEXT,
                created_at_ns INTEGER NOT NULL,
                updated_at_ns INTEGER NOT NULL,
                UNIQUE (graph_run_id, node_id, attempt_number),
                FOREIGN KEY (graph_run_id, node_id)
                    REFERENCES graph_node_states(graph_run_id, node_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS graph_attempts_run_wave_idx
                ON graph_attempts(graph_run_id, wave_id, attempt_number);
            CREATE INDEX IF NOT EXISTS graph_attempts_run_node_idx
                ON graph_attempts(graph_run_id, node_id, attempt_number);
            CREATE UNIQUE INDEX IF NOT EXISTS graph_attempts_one_running_per_node_idx
                ON graph_attempts(graph_run_id, node_id)
                WHERE runtime_state = 'running';
            """
        )

    def create_run(
        self,
        snapshot: GraphSnapshot,
        *,
        graph_run_id: str | None = None,
    ) -> str:
        states = _validated_states(snapshot)
        if any(state.runtime_state != "idle" for state in states.values()):
            raise ValueError("new graph run must start without active/runtime output state")

        run_id = _required_id(graph_run_id or new_graph_run_id(), "graph_run_id")
        now = time.time_ns()
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO graph_runs(graph_run_id, current_wave_id, created_at_ns, updated_at_ns) "
                    "VALUES (?, NULL, ?, ?)",
                    (run_id, now, now),
                )
                conn.executemany(
                    "INSERT INTO graph_node_states("
                    "graph_run_id, node_id, semantic_state, runtime_state, "
                    "current_attempt_id, session_id, turn_id, updated_at_ns"
                    ") VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?)",
                    [
                        (
                            run_id,
                            state.node_id,
                            state.semantic_state,
                            state.runtime_state,
                            now,
                        )
                        for state in snapshot.node_states
                    ],
                )
        except sqlite3.IntegrityError as exc:
            raise RuntimeError(f"graph run already exists: {run_id!r}") from exc
        return run_id

    def get_run(self, graph_run_id: str) -> dict[str, Any] | None:
        run_id = _required_id(graph_run_id, "graph_run_id")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT graph_run_id, current_wave_id, created_at_ns, updated_at_ns "
                "FROM graph_runs WHERE graph_run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_node(self, graph_run_id: str, node_id: str) -> dict[str, Any] | None:
        run_id = _required_id(graph_run_id, "graph_run_id")
        clean_node_id = _required_id(node_id, "node_id")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM graph_node_states WHERE graph_run_id = ? AND node_id = ?",
                (run_id, clean_node_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def load_snapshot(self, graph_run_id: str, graph: TaskGraph) -> GraphSnapshot:
        run_id = _required_id(graph_run_id, "graph_run_id")
        if not isinstance(graph, TaskGraph):
            raise ValueError("graph must be a TaskGraph")

        with self._connect() as conn:
            run = conn.execute(
                "SELECT 1 FROM graph_runs WHERE graph_run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise RuntimeError(f"unknown graph_run_id: {run_id!r}")
            rows = conn.execute(
                "SELECT node_id, semantic_state, runtime_state "
                "FROM graph_node_states WHERE graph_run_id = ?",
                (run_id,),
            ).fetchall()

        persisted = {row["node_id"]: row for row in rows}
        graph_ids = [node.node_id for node in graph.nodes]
        graph_id_set = set(graph_ids)
        persisted_id_set = set(persisted)
        if graph_id_set != persisted_id_set:
            missing = sorted(graph_id_set - persisted_id_set)
            extra = sorted(persisted_id_set - graph_id_set)
            details: list[str] = []
            if missing:
                details.append("missing persisted states for " + ", ".join(missing))
            if extra:
                details.append("persisted states for unknown nodes " + ", ".join(extra))
            raise RuntimeError("graph run does not match TaskGraph: " + "; ".join(details))

        snapshot = GraphSnapshot(
            graph=graph,
            node_states=tuple(
                NodeState(
                    node_id=node_id,
                    semantic_state=persisted[node_id]["semantic_state"],
                    runtime_state=persisted[node_id]["runtime_state"],
                )
                for node_id in graph_ids
            ),
        )
        _validated_states(snapshot)
        return snapshot

    def save_snapshot(self, graph_run_id: str, snapshot: GraphSnapshot) -> None:
        run_id = _required_id(graph_run_id, "graph_run_id")
        states = _validated_states(snapshot)
        now = time.time_ns()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            run = conn.execute(
                "SELECT 1 FROM graph_runs WHERE graph_run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise RuntimeError(f"unknown graph_run_id: {run_id!r}")

            rows = conn.execute(
                "SELECT node_id, current_attempt_id FROM graph_node_states "
                "WHERE graph_run_id = ?",
                (run_id,),
            ).fetchall()
            persisted_ids = {row["node_id"] for row in rows}
            if persisted_ids != set(states):
                raise RuntimeError("graph snapshot node set differs from persisted graph run")

            for row in rows:
                node_id = row["node_id"]
                current_attempt_id = row["current_attempt_id"]
                if current_attempt_id is None:
                    if states[node_id].runtime_state == "running":
                        raise RuntimeError(
                            f"node {node_id!r} cannot be persisted as running without an active attempt"
                        )
                    continue
                attempt = conn.execute(
                    "SELECT runtime_state FROM graph_attempts WHERE attempt_id = ?",
                    (current_attempt_id,),
                ).fetchone()
                if attempt is None:
                    raise RuntimeError(
                        f"node {node_id!r} references missing attempt {current_attempt_id!r}"
                    )
                if attempt["runtime_state"] == "running" and states[node_id].runtime_state != "running":
                    raise RuntimeError(
                        f"node {node_id!r} has a running attempt and cannot leave runtime_state='running'"
                    )
                if attempt["runtime_state"] != "running" and states[node_id].runtime_state == "running":
                    raise RuntimeError(
                        f"node {node_id!r} cannot be persisted as running after its attempt completed"
                    )

            conn.executemany(
                "UPDATE graph_node_states SET semantic_state = ?, runtime_state = ?, updated_at_ns = ? "
                "WHERE graph_run_id = ? AND node_id = ?",
                [
                    (
                        state.semantic_state,
                        state.runtime_state,
                        now,
                        run_id,
                        state.node_id,
                    )
                    for state in snapshot.node_states
                ],
            )
            conn.execute(
                "UPDATE graph_runs SET updated_at_ns = ? WHERE graph_run_id = ?",
                (now, run_id),
            )

    def start_attempt(
        self,
        graph_run_id: str,
        node_id: str,
        wave_id: str,
        *,
        resume_session: bool = False,
        session_id: str | None = None,
        attempt_id: str | None = None,
    ) -> str:
        run_id = _required_id(graph_run_id, "graph_run_id")
        clean_node_id = _required_id(node_id, "node_id")
        clean_wave_id = _required_id(wave_id, "wave_id")
        clean_attempt_id = _required_id(attempt_id or new_attempt_id(), "attempt_id")
        if not isinstance(resume_session, bool):
            raise ValueError("resume_session must be a boolean")
        clean_session_id = _optional_id(session_id, "session_id")
        if resume_session and clean_session_id is None:
            raise ValueError("resume_session requires an existing session_id")

        now = time.time_ns()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            run = conn.execute(
                "SELECT current_wave_id FROM graph_runs WHERE graph_run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise RuntimeError(f"unknown graph_run_id: {run_id!r}")
            if run["current_wave_id"] not in {None, clean_wave_id}:
                raise RuntimeError(
                    "graph run already has a different active wave: "
                    f"{run['current_wave_id']!r}"
                )

            node = conn.execute(
                "SELECT semantic_state, runtime_state FROM graph_node_states "
                "WHERE graph_run_id = ? AND node_id = ?",
                (run_id, clean_node_id),
            ).fetchone()
            if node is None:
                raise RuntimeError(f"unknown graph node for run: {clean_node_id!r}")
            if node["semantic_state"] != "pending" or node["runtime_state"] != "idle":
                raise RuntimeError(
                    f"node {clean_node_id!r} is not pending+idle and cannot start an attempt"
                )

            attempt_number = int(
                conn.execute(
                    "SELECT COALESCE(MAX(attempt_number), 0) + 1 "
                    "FROM graph_attempts WHERE graph_run_id = ? AND node_id = ?",
                    (run_id, clean_node_id),
                ).fetchone()[0]
            )
            try:
                conn.execute(
                    "INSERT INTO graph_attempts("
                    "attempt_id, graph_run_id, node_id, wave_id, attempt_number, "
                    "runtime_state, resume_session, session_id, turn_id, result_json, "
                    "created_at_ns, updated_at_ns"
                    ") VALUES (?, ?, ?, ?, ?, 'running', ?, ?, NULL, NULL, ?, ?)",
                    (
                        clean_attempt_id,
                        run_id,
                        clean_node_id,
                        clean_wave_id,
                        attempt_number,
                        int(resume_session),
                        clean_session_id,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise RuntimeError(
                    f"attempt identity conflicts with existing runtime state: {clean_attempt_id!r}"
                ) from exc

            conn.execute(
                "UPDATE graph_node_states SET runtime_state = 'running', "
                "current_attempt_id = ?, session_id = ?, turn_id = NULL, updated_at_ns = ? "
                "WHERE graph_run_id = ? AND node_id = ?",
                (clean_attempt_id, clean_session_id, now, run_id, clean_node_id),
            )
            conn.execute(
                "UPDATE graph_runs SET current_wave_id = ?, updated_at_ns = ? "
                "WHERE graph_run_id = ?",
                (clean_wave_id, now, run_id),
            )
        return clean_attempt_id

    def bind_attempt_session(self, attempt_id: str, session_id: str) -> None:
        clean_attempt_id = _required_id(attempt_id, "attempt_id")
        clean_session_id = _required_id(session_id, "session_id")
        now = time.time_ns()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            attempt = conn.execute(
                "SELECT graph_run_id, node_id, runtime_state, session_id "
                "FROM graph_attempts WHERE attempt_id = ?",
                (clean_attempt_id,),
            ).fetchone()
            if attempt is None:
                raise RuntimeError(f"unknown graph attempt: {clean_attempt_id!r}")
            if attempt["runtime_state"] != "running":
                raise RuntimeError("session can only be bound while an attempt is running")
            if attempt["session_id"] not in {None, clean_session_id}:
                raise RuntimeError("attempt session identity cannot change")

            node = conn.execute(
                "SELECT current_attempt_id FROM graph_node_states "
                "WHERE graph_run_id = ? AND node_id = ?",
                (attempt["graph_run_id"], attempt["node_id"]),
            ).fetchone()
            if node is None or node["current_attempt_id"] != clean_attempt_id:
                raise RuntimeError("attempt is no longer the current node execution")

            conn.execute(
                "UPDATE graph_attempts SET session_id = ?, updated_at_ns = ? "
                "WHERE attempt_id = ?",
                (clean_session_id, now, clean_attempt_id),
            )
            conn.execute(
                "UPDATE graph_node_states SET session_id = ?, updated_at_ns = ? "
                "WHERE graph_run_id = ? AND node_id = ?",
                (
                    clean_session_id,
                    now,
                    attempt["graph_run_id"],
                    attempt["node_id"],
                ),
            )
            conn.execute(
                "UPDATE graph_runs SET updated_at_ns = ? WHERE graph_run_id = ?",
                (now, attempt["graph_run_id"]),
            )

    def finish_attempt(
        self,
        attempt_id: str,
        *,
        runtime_state: str,
        result: dict[str, Any],
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        clean_attempt_id = _required_id(attempt_id, "attempt_id")
        if runtime_state not in ATTEMPT_TERMINAL_STATES:
            raise ValueError(f"unsupported terminal attempt state: {runtime_state!r}")
        clean_session_id = _optional_id(session_id, "session_id")
        clean_turn_id = _optional_id(turn_id, "turn_id")
        encoded_result = _result_json(result)
        now = time.time_ns()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            attempt = conn.execute(
                "SELECT graph_run_id, node_id, runtime_state, session_id "
                "FROM graph_attempts WHERE attempt_id = ?",
                (clean_attempt_id,),
            ).fetchone()
            if attempt is None:
                raise RuntimeError(f"unknown graph attempt: {clean_attempt_id!r}")
            if attempt["runtime_state"] != "running":
                raise RuntimeError("graph attempt is already terminal")
            if attempt["session_id"] is not None:
                if clean_session_id is None:
                    clean_session_id = attempt["session_id"]
                elif clean_session_id != attempt["session_id"]:
                    raise RuntimeError("attempt session identity cannot change")

            node = conn.execute(
                "SELECT current_attempt_id FROM graph_node_states "
                "WHERE graph_run_id = ? AND node_id = ?",
                (attempt["graph_run_id"], attempt["node_id"]),
            ).fetchone()
            if node is None or node["current_attempt_id"] != clean_attempt_id:
                raise RuntimeError("attempt is no longer the current node execution")

            conn.execute(
                "UPDATE graph_attempts SET runtime_state = ?, session_id = ?, turn_id = ?, "
                "result_json = ?, updated_at_ns = ? WHERE attempt_id = ?",
                (
                    runtime_state,
                    clean_session_id,
                    clean_turn_id,
                    encoded_result,
                    now,
                    clean_attempt_id,
                ),
            )
            conn.execute(
                "UPDATE graph_node_states SET runtime_state = ?, session_id = ?, turn_id = ?, "
                "updated_at_ns = ? WHERE graph_run_id = ? AND node_id = ?",
                (
                    runtime_state,
                    clean_session_id,
                    clean_turn_id,
                    now,
                    attempt["graph_run_id"],
                    attempt["node_id"],
                ),
            )
            conn.execute(
                "UPDATE graph_runs SET updated_at_ns = ? WHERE graph_run_id = ?",
                (now, attempt["graph_run_id"]),
            )

    def close_wave(self, graph_run_id: str, wave_id: str) -> None:
        run_id = _required_id(graph_run_id, "graph_run_id")
        clean_wave_id = _required_id(wave_id, "wave_id")
        now = time.time_ns()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            run = conn.execute(
                "SELECT current_wave_id FROM graph_runs WHERE graph_run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise RuntimeError(f"unknown graph_run_id: {run_id!r}")
            if run["current_wave_id"] != clean_wave_id:
                raise RuntimeError(
                    f"wave {clean_wave_id!r} is not the current wave for graph run"
                )
            active = conn.execute(
                "SELECT COUNT(*) FROM graph_attempts "
                "WHERE graph_run_id = ? AND wave_id = ? AND runtime_state = 'running'",
                (run_id, clean_wave_id),
            ).fetchone()[0]
            if active:
                raise RuntimeError("cannot close a wave while node attempts are running")
            conn.execute(
                "UPDATE graph_runs SET current_wave_id = NULL, updated_at_ns = ? "
                "WHERE graph_run_id = ?",
                (now, run_id),
            )

    def get_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        clean_attempt_id = _required_id(attempt_id, "attempt_id")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM graph_attempts WHERE attempt_id = ?",
                (clean_attempt_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["resume_session"] = bool(result["resume_session"])
        raw_result = result.pop("result_json")
        result["result"] = json.loads(raw_result) if raw_result is not None else None
        return result

    def list_attempts(self, graph_run_id: str, node_id: str) -> list[dict[str, Any]]:
        run_id = _required_id(graph_run_id, "graph_run_id")
        clean_node_id = _required_id(node_id, "node_id")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM graph_attempts WHERE graph_run_id = ? AND node_id = ? "
                "ORDER BY attempt_number ASC",
                (run_id, clean_node_id),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["resume_session"] = bool(item["resume_session"])
            raw_result = item.pop("result_json")
            item["result"] = json.loads(raw_result) if raw_result is not None else None
            result.append(item)
        return result
