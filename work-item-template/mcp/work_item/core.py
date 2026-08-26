from __future__ import annotations

import copy
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORK_ITEM_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")
WORK_ITEM_STATUSES = {"active", "waiting", "blocked", "done", "cancelled"}
REPO_STATUSES = {"pending", "active", "waiting", "blocked", "done", "not_required"}
QUESTION_STATUSES = {"open", "resolved"}
DECISION_STATUSES = {"active", "superseded"}
CHANGE_TYPES = {
    "requirement_added",
    "requirement_changed",
    "requirement_removed",
    "scope_changed",
}
CHANGE_STATUSES = {"proposed", "accepted", "rejected", "superseded"}
BLOCKER_STATUSES = {"open", "resolved"}
HANDOFF_STATUSES = {"pending", "resolved"}

REQUIRED_COLLECTIONS = (
    "current_requirements",
    "questions",
    "decisions",
    "changes",
    "blockers",
    "handoffs",
    "next_actions",
    "checkpoints",
)
IMMUTABLE_UPDATE_FIELDS = {"id", "revision", "created_at", "updated_at"}
DERIVED_FIELDS = {"artifacts"}


class WorkItemError(RuntimeError):
    pass


class ValidationError(WorkItemError):
    pass


class NotFoundError(WorkItemError):
    pass


class ConflictError(WorkItemError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def resolve_db_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path.exists() and path.is_dir():
        raise ValidationError(f"work item DB path is a directory: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_items (
            id TEXT PRIMARY KEY,
            revision INTEGER NOT NULL,
            status TEXT NOT NULL,
            document_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status)"
    )
    return conn


def _required_text(value: Any, label: str, *, max_chars: int = 10_000) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError(f"{label} must not be empty")
    if len(cleaned) > max_chars:
        raise ValidationError(f"{label} exceeds {max_chars} characters")
    return cleaned


def _optional_text(value: Any, label: str, *, max_chars: int = 20_000) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    cleaned = value.strip()
    if len(cleaned) > max_chars:
        raise ValidationError(f"{label} exceeds {max_chars} characters")
    return cleaned


def _validate_string_list(value: Any, label: str) -> None:
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be a list")
    for index, item in enumerate(value):
        _required_text(item, f"{label}[{index}]", max_chars=10_000)


def _validate_id_objects(
    value: Any,
    label: str,
    *,
    allowed_statuses: set[str] | None = None,
    allowed_types: set[str] | None = None,
) -> None:
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be a list")
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValidationError(f"{label}[{index}] must be an object")
        item_id = _required_text(item.get("id"), f"{label}[{index}].id", max_chars=128)
        if item_id in seen:
            raise ValidationError(f"{label} contains duplicate id {item_id!r}")
        seen.add(item_id)
        if "status" in item and allowed_statuses is not None:
            status = _required_text(
                item["status"], f"{label}[{index}].status", max_chars=64
            )
            if status not in allowed_statuses:
                allowed = ", ".join(sorted(allowed_statuses))
                raise ValidationError(
                    f"{label}[{index}].status must be one of: {allowed}"
                )
        if "type" in item and allowed_types is not None:
            change_type = _required_text(
                item["type"], f"{label}[{index}].type", max_chars=64
            )
            if change_type not in allowed_types:
                allowed = ", ".join(sorted(allowed_types))
                raise ValidationError(
                    f"{label}[{index}].type must be one of: {allowed}"
                )


def _validate_repo_map(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationError("repos must be an object keyed by repository name")
    for repo, state in value.items():
        _required_text(repo, "repos key", max_chars=256)
        if not isinstance(state, dict):
            raise ValidationError(f"repos[{repo!r}] must be an object")
        if "status" in state:
            status = _required_text(state["status"], f"repos[{repo!r}].status", max_chars=64)
            if status not in REPO_STATUSES:
                allowed = ", ".join(sorted(REPO_STATUSES))
                raise ValidationError(
                    f"repos[{repo!r}].status must be one of: {allowed}"
                )
        if "summary" in state:
            _optional_text(state["summary"], f"repos[{repo!r}].summary")
        if "verification" in state:
            _validate_string_list(state["verification"], f"repos[{repo!r}].verification")


def validate_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValidationError("work item document must be an object")
    derived = sorted(DERIVED_FIELDS.intersection(document))
    if derived:
        raise ValidationError(
            "work item document must not persist derived fields: " + ", ".join(derived)
        )

    item_id = _required_text(document.get("id"), "id", max_chars=256)
    if not WORK_ITEM_ID_RE.fullmatch(item_id):
        raise ValidationError(
            "id must use <source>:<external-id>, for example redmine:116655"
        )
    _required_text(document.get("title"), "title", max_chars=1_000)
    status = _required_text(document.get("status"), "status", max_chars=64)
    if status not in WORK_ITEM_STATUSES:
        allowed = ", ".join(sorted(WORK_ITEM_STATUSES))
        raise ValidationError(f"status must be one of: {allowed}")
    _required_text(document.get("phase"), "phase", max_chars=64)
    _optional_text(document.get("summary", ""), "summary", max_chars=20_000)

    for key in REQUIRED_COLLECTIONS:
        if key not in document:
            raise ValidationError(f"missing required field: {key}")

    _validate_string_list(document["current_requirements"], "current_requirements")
    _validate_id_objects(
        document["questions"], "questions", allowed_statuses=QUESTION_STATUSES
    )
    for index, question in enumerate(document["questions"]):
        _required_text(question.get("question"), f"questions[{index}].question")
        status_value = question.get("status")
        if status_value == "resolved" and not (
            isinstance(question.get("answer"), str) and question["answer"].strip()
        ) and not (
            isinstance(question.get("decision_id"), str) and question["decision_id"].strip()
        ):
            raise ValidationError(
                f"questions[{index}] resolved item must contain answer or decision_id"
            )
    _validate_id_objects(
        document["decisions"], "decisions", allowed_statuses=DECISION_STATUSES
    )
    for index, decision in enumerate(document["decisions"]):
        _required_text(decision.get("summary"), f"decisions[{index}].summary")
        if decision.get("status") == "superseded":
            _required_text(
                decision.get("superseded_by"),
                f"decisions[{index}].superseded_by",
                max_chars=128,
            )
    _validate_id_objects(
        document["changes"],
        "changes",
        allowed_statuses=CHANGE_STATUSES,
        allowed_types=CHANGE_TYPES,
    )
    for index, change in enumerate(document["changes"]):
        _required_text(change.get("summary"), f"changes[{index}].summary")
        if "type" not in change:
            raise ValidationError(f"changes[{index}].type is required")
        if "status" not in change:
            raise ValidationError(f"changes[{index}].status is required")
    _validate_repo_map(document.get("repos"))
    _validate_id_objects(
        document["blockers"], "blockers", allowed_statuses=BLOCKER_STATUSES
    )
    for index, blocker in enumerate(document["blockers"]):
        _required_text(blocker.get("summary"), f"blockers[{index}].summary")
        if "status" not in blocker:
            raise ValidationError(f"blockers[{index}].status is required")
    _validate_id_objects(
        document["handoffs"], "handoffs", allowed_statuses=HANDOFF_STATUSES
    )
    for index, handoff in enumerate(document["handoffs"]):
        _required_text(handoff.get("from"), f"handoffs[{index}].from", max_chars=256)
        _required_text(handoff.get("to"), f"handoffs[{index}].to", max_chars=256)
        _required_text(handoff.get("summary"), f"handoffs[{index}].summary")
        if "status" not in handoff:
            raise ValidationError(f"handoffs[{index}].status is required")

    next_actions = document["next_actions"]
    if not isinstance(next_actions, list):
        raise ValidationError("next_actions must be a list")
    for index, action in enumerate(next_actions):
        if not isinstance(action, dict):
            raise ValidationError(f"next_actions[{index}] must be an object")
        _required_text(action.get("action"), f"next_actions[{index}].action")
        if "repo" not in action and "owner" not in action:
            raise ValidationError(
                f"next_actions[{index}] must identify either repo or owner"
            )
        if "repo" in action:
            _required_text(action["repo"], f"next_actions[{index}].repo", max_chars=256)
        if "owner" in action:
            _required_text(action["owner"], f"next_actions[{index}].owner", max_chars=256)

    checkpoints = document["checkpoints"]
    if not isinstance(checkpoints, list):
        raise ValidationError("checkpoints must be a list")
    for index, checkpoint in enumerate(checkpoints):
        if not isinstance(checkpoint, dict):
            raise ValidationError(f"checkpoints[{index}] must be an object")
        _required_text(checkpoint.get("summary"), f"checkpoints[{index}].summary")
        if "repo" in checkpoint:
            _required_text(checkpoint["repo"], f"checkpoints[{index}].repo", max_chars=256)
        if "at" in checkpoint:
            _required_text(checkpoint["at"], f"checkpoints[{index}].at", max_chars=128)

    try:
        encoded = json.dumps(document, ensure_ascii=False, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"work item contains non-JSON data: {exc}") from exc
    return decoded


def new_document(
    *,
    item_id: str,
    title: str,
    summary: str = "",
    status: str = "active",
    phase: str = "investigation",
    current_requirements: list[str] | None = None,
    repositories: list[str] | None = None,
) -> dict[str, Any]:
    repos: dict[str, dict[str, Any]] = {}
    for repo in repositories or []:
        name = _required_text(repo, "repository", max_chars=256)
        if name in repos:
            raise ValidationError(f"duplicate repository: {name}")
        repos[name] = {"status": "pending", "summary": "", "verification": []}

    return validate_document(
        {
            "id": item_id,
            "title": title,
            "status": status,
            "phase": phase,
            "summary": summary,
            "current_requirements": list(current_requirements or []),
            "questions": [],
            "decisions": [],
            "changes": [],
            "repos": repos,
            "blockers": [],
            "handoffs": [],
            "next_actions": [],
            "checkpoints": [],
        }
    )


def _row_to_result(row: sqlite3.Row) -> dict[str, Any]:
    document = json.loads(row["document_json"])
    document["revision"] = row["revision"]
    document["created_at"] = row["created_at"]
    document["updated_at"] = row["updated_at"]
    return document


def create_work_item(db_path: str | Path, document: dict[str, Any]) -> dict[str, Any]:
    document = validate_document(document)
    now = _now_iso()
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                INSERT INTO work_items(id, revision, status, document_json, created_at, updated_at)
                VALUES (?, 1, ?, ?, ?, ?)
                """,
                (document["id"], document["status"], encoded, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"work item already exists: {document['id']}") from exc
        row = conn.execute(
            "SELECT * FROM work_items WHERE id = ?", (document["id"],)
        ).fetchone()
        conn.execute("COMMIT")
        assert row is not None
        return _row_to_result(row)
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def get_work_item(db_path: str | Path, item_id: str) -> dict[str, Any]:
    item_id = _required_text(item_id, "id", max_chars=256)
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM work_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"work item not found: {item_id}")
        return _row_to_result(row)
    finally:
        conn.close()


def _merge_patch(target: Any, patch: Any) -> Any:
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    if not isinstance(target, dict):
        target = {}
    result = copy.deepcopy(target)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = _merge_patch(result.get(key), value)
    return result


def update_work_item(
    db_path: str | Path,
    item_id: str,
    expected_revision: int,
    changes: dict[str, Any],
) -> dict[str, Any]:
    item_id = _required_text(item_id, "id", max_chars=256)
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
        raise ValidationError("expected_revision must be a positive integer")
    if not isinstance(changes, dict) or not changes:
        raise ValidationError("changes must be a non-empty object")
    immutable = sorted(IMMUTABLE_UPDATE_FIELDS.intersection(changes))
    if immutable:
        raise ValidationError(
            "changes must not modify immutable fields: " + ", ".join(immutable)
        )
    derived = sorted(DERIVED_FIELDS.intersection(changes))
    if derived:
        raise ValidationError(
            "changes must not modify derived fields: " + ", ".join(derived)
        )

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM work_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"work item not found: {item_id}")
        if row["revision"] != expected_revision:
            raise ConflictError(
                f"revision conflict for {item_id}: expected {expected_revision}, current {row['revision']}"
            )

        current = json.loads(row["document_json"])
        merged = _merge_patch(current, changes)
        merged["id"] = item_id
        merged = validate_document(merged)
        now = _now_iso()
        new_revision = expected_revision + 1
        encoded = json.dumps(merged, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        cursor = conn.execute(
            """
            UPDATE work_items
            SET revision = ?, status = ?, document_json = ?, updated_at = ?
            WHERE id = ? AND revision = ?
            """,
            (new_revision, merged["status"], encoded, now, item_id, expected_revision),
        )
        if cursor.rowcount != 1:
            raise ConflictError(f"revision conflict for {item_id}; reread before retrying")
        updated = conn.execute("SELECT * FROM work_items WHERE id = ?", (item_id,)).fetchone()
        conn.execute("COMMIT")
        assert updated is not None
        return _row_to_result(updated)
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def list_work_items(
    db_path: str | Path,
    *,
    status: str | None = None,
    repository: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if status is not None:
        status = _required_text(status, "status", max_chars=64)
        if status not in WORK_ITEM_STATUSES:
            allowed = ", ".join(sorted(WORK_ITEM_STATUSES))
            raise ValidationError(f"status must be one of: {allowed}")
    if repository is not None:
        repository = _required_text(repository, "repository", max_chars=256)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 200:
        raise ValidationError("limit must be an integer between 1 and 200")

    conn = _connect(db_path)
    try:
        if status is None:
            rows = conn.execute(
                "SELECT * FROM work_items ORDER BY updated_at DESC, id ASC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM work_items WHERE status = ? ORDER BY updated_at DESC, id ASC",
                (status,),
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            item = _row_to_result(row)
            if repository is not None and repository not in item["repos"]:
                continue
            result.append(
                {
                    "id": item["id"],
                    "title": item["title"],
                    "status": item["status"],
                    "phase": item["phase"],
                    "summary": item["summary"],
                    "revision": item["revision"],
                    "updated_at": item["updated_at"],
                    "repositories": sorted(item["repos"]),
                }
            )
            if len(result) >= limit:
                break
        return result
    finally:
        conn.close()
