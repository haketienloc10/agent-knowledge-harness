from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import ConflictError, NotFoundError, ValidationError, resolve_db_path

ARTIFACT_TYPES = {"intake", "investigation", "plan", "review", "report"}
ARTIFACT_STATES = {"draft", "complete"}
ARTIFACT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")
SECTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

ARTIFACT_APPEND_MAX_BYTES = 16 * 1024
ARTIFACT_READ_MAX_CHUNKS = 2
ARTIFACT_INDEX_LIMIT = 20
ARTIFACT_LIST_LIMIT_MAX = 100


class ArtifactNotFoundError(NotFoundError):
    pass


class ArtifactConflictError(ConflictError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _required_text(value: Any, label: str, *, max_chars: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError(f"{label} must not be empty")
    if len(cleaned) > max_chars:
        raise ValidationError(f"{label} exceeds {max_chars} characters")
    return cleaned


def _optional_text(value: Any, label: str, *, max_chars: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    cleaned = value.strip()
    if len(cleaned) > max_chars:
        raise ValidationError(f"{label} exceeds {max_chars} characters")
    return cleaned


def _positive_revision(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValidationError(f"{label} must be a positive integer")
    return value


def _artifact_type(value: Any) -> str:
    artifact_type = _required_text(value, "type", max_chars=64)
    if artifact_type not in ARTIFACT_TYPES:
        allowed = ", ".join(sorted(ARTIFACT_TYPES))
        raise ValidationError(f"type must be one of: {allowed}")
    return artifact_type


def _artifact_id(value: Any) -> str:
    artifact_id = _required_text(value, "artifact_id", max_chars=256)
    if not ARTIFACT_ID_RE.fullmatch(artifact_id):
        raise ValidationError(
            "artifact_id must use <type>:<id>, for example investigation:1"
        )
    return artifact_id


def _section_id(value: Any) -> str:
    section_id = _required_text(value, "section_id", max_chars=128)
    if not SECTION_ID_RE.fullmatch(section_id):
        raise ValidationError(
            "section_id may contain only letters, digits, dot, underscore and hyphen"
        )
    return section_id


def _chunk_content(value: Any) -> tuple[str, int]:
    if not isinstance(value, str):
        raise ValidationError("content must be a string")
    if value == "":
        raise ValidationError("content must not be empty")
    size = len(value.encode("utf-8"))
    if size > ARTIFACT_APPEND_MAX_BYTES:
        raise ValidationError(
            f"artifact chunk exceeds {ARTIFACT_APPEND_MAX_BYTES} UTF-8 bytes; "
            "split the content into smaller append calls"
        )
    return value, size


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_item_artifacts (
            work_item_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            type TEXT NOT NULL,
            state TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            based_on_work_item_revision INTEGER NOT NULL,
            revision INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (work_item_id, artifact_id),
            FOREIGN KEY (work_item_id) REFERENCES work_items(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_item_artifact_sections (
            work_item_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            section_id TEXT NOT NULL,
            title TEXT NOT NULL,
            position INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (work_item_id, artifact_id, section_id),
            UNIQUE (work_item_id, artifact_id, position),
            FOREIGN KEY (work_item_id, artifact_id)
                REFERENCES work_item_artifacts(work_item_id, artifact_id)
                ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_item_artifact_chunks (
            work_item_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            section_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_bytes INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (work_item_id, artifact_id, section_id, chunk_index),
            FOREIGN KEY (work_item_id, artifact_id, section_id)
                REFERENCES work_item_artifact_sections(work_item_id, artifact_id, section_id)
                ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_item_artifacts_type "
        "ON work_item_artifacts(work_item_id, type, updated_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_item_artifact_chunks_section "
        "ON work_item_artifact_chunks(work_item_id, artifact_id, section_id, chunk_index)"
    )
    return conn


def _require_work_item(conn: sqlite3.Connection, item_id: str) -> sqlite3.Row:
    item_id = _required_text(item_id, "id", max_chars=256)
    try:
        row = conn.execute(
            "SELECT id, revision FROM work_items WHERE id = ?", (item_id,)
        ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            raise NotFoundError(f"work item not found: {item_id}") from exc
        raise
    if row is None:
        raise NotFoundError(f"work item not found: {item_id}")
    return row


def _require_artifact(
    conn: sqlite3.Connection, item_id: str, artifact_id: str
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM work_item_artifacts WHERE work_item_id = ? AND artifact_id = ?",
        (item_id, artifact_id),
    ).fetchone()
    if row is None:
        raise ArtifactNotFoundError(
            f"artifact not found: {item_id}/{artifact_id}"
        )
    return row


def _artifact_metadata(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "work_item_id": row["work_item_id"],
        "artifact_id": row["artifact_id"],
        "type": row["type"],
        "state": row["state"],
        "title": row["title"],
        "summary": row["summary"],
        "based_on_work_item_revision": row["based_on_work_item_revision"],
        "revision": row["revision"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _counts_for_artifact(
    conn: sqlite3.Connection, item_id: str, artifact_id: str
) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(DISTINCT s.section_id) AS section_count,
            COALESCE(SUM(c.content_bytes), 0) AS total_bytes
        FROM work_item_artifact_sections AS s
        LEFT JOIN work_item_artifact_chunks AS c
          ON c.work_item_id = s.work_item_id
         AND c.artifact_id = s.artifact_id
         AND c.section_id = s.section_id
        WHERE s.work_item_id = ? AND s.artifact_id = ?
        """,
        (item_id, artifact_id),
    ).fetchone()
    assert row is not None
    return int(row["section_count"]), int(row["total_bytes"])


def _metadata_with_counts(
    conn: sqlite3.Connection, row: sqlite3.Row
) -> dict[str, Any]:
    result = _artifact_metadata(row)
    section_count, total_bytes = _counts_for_artifact(
        conn, row["work_item_id"], row["artifact_id"]
    )
    result["section_count"] = section_count
    result["total_bytes"] = total_bytes
    return result


def list_artifacts(
    db_path: str | Path,
    item_id: str,
    *,
    artifact_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if artifact_type is not None:
        artifact_type = _artifact_type(artifact_type)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= ARTIFACT_LIST_LIMIT_MAX:
        raise ValidationError(
            f"limit must be an integer between 1 and {ARTIFACT_LIST_LIMIT_MAX}"
        )

    conn = _connect(db_path)
    try:
        _require_work_item(conn, item_id)
        if artifact_type is None:
            rows = conn.execute(
                """
                SELECT * FROM work_item_artifacts
                WHERE work_item_id = ?
                ORDER BY updated_at DESC, artifact_id ASC
                LIMIT ?
                """,
                (item_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM work_item_artifacts
                WHERE work_item_id = ? AND type = ?
                ORDER BY updated_at DESC, artifact_id ASC
                LIMIT ?
                """,
                (item_id, artifact_type, limit),
            ).fetchall()
        return [_metadata_with_counts(conn, row) for row in rows]
    finally:
        conn.close()


def get_artifact_index(
    db_path: str | Path,
    item_id: str,
    *,
    limit: int = ARTIFACT_INDEX_LIMIT,
) -> dict[str, Any]:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValidationError("artifact index limit must be a positive integer")
    conn = _connect(db_path)
    try:
        _require_work_item(conn, item_id)
        count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM work_item_artifacts WHERE work_item_id = ?",
            (item_id,),
        ).fetchone()
        assert count_row is not None
        count = int(count_row["count"])
        rows = conn.execute(
            """
            SELECT * FROM work_item_artifacts
            WHERE work_item_id = ?
            ORDER BY updated_at DESC, artifact_id ASC
            LIMIT ?
            """,
            (item_id, limit),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            metadata = _metadata_with_counts(conn, row)
            metadata.pop("summary", None)
            items.append(metadata)
        return {"count": count, "items": items, "truncated": count > limit}
    finally:
        conn.close()


def get_artifact(
    db_path: str | Path, item_id: str, artifact_id: str
) -> dict[str, Any]:
    artifact_id = _artifact_id(artifact_id)
    conn = _connect(db_path)
    try:
        _require_work_item(conn, item_id)
        row = _require_artifact(conn, item_id, artifact_id)
        result = _artifact_metadata(row)
        section_rows = conn.execute(
            """
            SELECT
                s.section_id,
                s.title,
                s.position,
                s.created_at,
                s.updated_at,
                COUNT(c.chunk_index) AS chunk_count,
                COALESCE(SUM(c.content_bytes), 0) AS total_bytes
            FROM work_item_artifact_sections AS s
            LEFT JOIN work_item_artifact_chunks AS c
              ON c.work_item_id = s.work_item_id
             AND c.artifact_id = s.artifact_id
             AND c.section_id = s.section_id
            WHERE s.work_item_id = ? AND s.artifact_id = ?
            GROUP BY
                s.section_id, s.title, s.position, s.created_at, s.updated_at
            ORDER BY s.position ASC
            """,
            (item_id, artifact_id),
        ).fetchall()
        sections = [
            {
                "section_id": section["section_id"],
                "title": section["title"],
                "position": section["position"],
                "chunk_count": int(section["chunk_count"]),
                "total_bytes": int(section["total_bytes"]),
                "created_at": section["created_at"],
                "updated_at": section["updated_at"],
            }
            for section in section_rows
        ]
        result["section_count"] = len(sections)
        result["total_bytes"] = sum(section["total_bytes"] for section in sections)
        result["sections"] = sections
        return result
    finally:
        conn.close()


def _next_generated_artifact_id(
    conn: sqlite3.Connection, item_id: str, artifact_type: str
) -> str:
    rows = conn.execute(
        "SELECT artifact_id FROM work_item_artifacts WHERE work_item_id = ? AND type = ?",
        (item_id, artifact_type),
    ).fetchall()
    highest = 0
    prefix = artifact_type + ":"
    for row in rows:
        value = row["artifact_id"]
        if not value.startswith(prefix):
            continue
        suffix = value[len(prefix) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{artifact_type}:{highest + 1}"


def create_artifact(
    db_path: str | Path,
    item_id: str,
    *,
    artifact_type: str,
    title: str,
    summary: str,
    based_on_work_item_revision: int,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    artifact_type = _artifact_type(artifact_type)
    title = _required_text(title, "title", max_chars=1_000)
    summary = _optional_text(summary, "summary", max_chars=2_000)
    based_on_work_item_revision = _positive_revision(
        based_on_work_item_revision, "based_on_work_item_revision"
    )
    if artifact_id is not None:
        artifact_id = _artifact_id(artifact_id)
        if not artifact_id.startswith(artifact_type + ":"):
            raise ValidationError(
                "artifact_id prefix must match the artifact type, "
                f"for example {artifact_type}:1"
            )

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        work_item = _require_work_item(conn, item_id)
        if work_item["revision"] != based_on_work_item_revision:
            raise ConflictError(
                f"revision conflict for {item_id}: expected {based_on_work_item_revision}, "
                f"current {work_item['revision']}"
            )
        resolved_id = artifact_id or _next_generated_artifact_id(
            conn, item_id, artifact_type
        )
        now = _now_iso()
        try:
            conn.execute(
                """
                INSERT INTO work_item_artifacts(
                    work_item_id, artifact_id, type, state, title, summary,
                    based_on_work_item_revision, revision, created_at, updated_at
                ) VALUES (?, ?, ?, 'draft', ?, ?, ?, 1, ?, ?)
                """,
                (
                    item_id,
                    resolved_id,
                    artifact_type,
                    title,
                    summary,
                    based_on_work_item_revision,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ArtifactConflictError(
                f"artifact already exists: {item_id}/{resolved_id}"
            ) from exc
        row = _require_artifact(conn, item_id, resolved_id)
        conn.execute("COMMIT")
        return _metadata_with_counts(conn, row)
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def append_artifact_chunk(
    db_path: str | Path,
    item_id: str,
    artifact_id: str,
    *,
    expected_artifact_revision: int,
    section_id: str,
    content: str,
    section_title: str | None = None,
) -> dict[str, Any]:
    artifact_id = _artifact_id(artifact_id)
    expected_artifact_revision = _positive_revision(
        expected_artifact_revision, "expected_artifact_revision"
    )
    section_id = _section_id(section_id)
    content, content_bytes = _chunk_content(content)
    if section_title is not None:
        section_title = _required_text(section_title, "section_title", max_chars=500)

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _require_work_item(conn, item_id)
        artifact = _require_artifact(conn, item_id, artifact_id)
        if artifact["revision"] != expected_artifact_revision:
            raise ArtifactConflictError(
                f"artifact revision conflict for {item_id}/{artifact_id}: "
                f"expected {expected_artifact_revision}, current {artifact['revision']}"
            )
        if artifact["state"] != "draft":
            raise ValidationError(
                f"artifact is {artifact['state']}; only draft artifacts accept append"
            )

        section = conn.execute(
            """
            SELECT * FROM work_item_artifact_sections
            WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?
            """,
            (item_id, artifact_id, section_id),
        ).fetchone()
        now = _now_iso()
        if section is None:
            if section_title is None:
                raise ValidationError(
                    "section_title is required when appending the first chunk of a section"
                )
            position_row = conn.execute(
                """
                SELECT COALESCE(MAX(position), -1) + 1 AS next_position
                FROM work_item_artifact_sections
                WHERE work_item_id = ? AND artifact_id = ?
                """,
                (item_id, artifact_id),
            ).fetchone()
            assert position_row is not None
            conn.execute(
                """
                INSERT INTO work_item_artifact_sections(
                    work_item_id, artifact_id, section_id, title, position,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    artifact_id,
                    section_id,
                    section_title,
                    int(position_row["next_position"]),
                    now,
                    now,
                ),
            )
        elif section_title is not None and section_title != section["title"]:
            raise ValidationError(
                f"section_title mismatch for {section_id}: expected {section['title']!r}"
            )

        chunk_row = conn.execute(
            """
            SELECT COALESCE(MAX(chunk_index), -1) + 1 AS next_chunk
            FROM work_item_artifact_chunks
            WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?
            """,
            (item_id, artifact_id, section_id),
        ).fetchone()
        assert chunk_row is not None
        chunk_index = int(chunk_row["next_chunk"])
        conn.execute(
            """
            INSERT INTO work_item_artifact_chunks(
                work_item_id, artifact_id, section_id, chunk_index,
                content, content_bytes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                artifact_id,
                section_id,
                chunk_index,
                content,
                content_bytes,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE work_item_artifact_sections
            SET updated_at = ?
            WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?
            """,
            (now, item_id, artifact_id, section_id),
        )
        new_revision = expected_artifact_revision + 1
        cursor = conn.execute(
            """
            UPDATE work_item_artifacts
            SET revision = ?, updated_at = ?
            WHERE work_item_id = ? AND artifact_id = ? AND revision = ?
            """,
            (new_revision, now, item_id, artifact_id, expected_artifact_revision),
        )
        if cursor.rowcount != 1:
            raise ArtifactConflictError(
                f"artifact revision conflict for {item_id}/{artifact_id}; reread before retrying"
            )
        conn.execute("COMMIT")
        return {
            "work_item_id": item_id,
            "artifact_id": artifact_id,
            "state": "draft",
            "revision": new_revision,
            "appended": {
                "section_id": section_id,
                "chunk_index": chunk_index,
                "bytes": content_bytes,
            },
        }
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def read_artifact_section(
    db_path: str | Path,
    item_id: str,
    artifact_id: str,
    section_id: str,
    *,
    cursor: int = 0,
    limit_chunks: int = 1,
) -> dict[str, Any]:
    artifact_id = _artifact_id(artifact_id)
    section_id = _section_id(section_id)
    if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
        raise ValidationError("cursor must be a non-negative chunk index")
    if (
        not isinstance(limit_chunks, int)
        or isinstance(limit_chunks, bool)
        or not 1 <= limit_chunks <= ARTIFACT_READ_MAX_CHUNKS
    ):
        raise ValidationError(
            f"limit_chunks must be between 1 and {ARTIFACT_READ_MAX_CHUNKS}"
        )

    conn = _connect(db_path)
    try:
        _require_work_item(conn, item_id)
        artifact = _require_artifact(conn, item_id, artifact_id)
        section = conn.execute(
            """
            SELECT * FROM work_item_artifact_sections
            WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?
            """,
            (item_id, artifact_id, section_id),
        ).fetchone()
        if section is None:
            raise ArtifactNotFoundError(
                f"artifact section not found: {item_id}/{artifact_id}/{section_id}"
            )
        count_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM work_item_artifact_chunks
            WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?
            """,
            (item_id, artifact_id, section_id),
        ).fetchone()
        assert count_row is not None
        chunk_count = int(count_row["count"])
        if cursor > chunk_count:
            raise ValidationError(
                f"cursor {cursor} is past section chunk count {chunk_count}"
            )
        if cursor == chunk_count:
            return {
                "work_item_id": item_id,
                "artifact_id": artifact_id,
                "artifact_revision": artifact["revision"],
                "artifact_state": artifact["state"],
                "section_id": section_id,
                "section_title": section["title"],
                "cursor": cursor,
                "returned_chunks": 0,
                "returned_bytes": 0,
                "content": "",
                "next_cursor": None,
                "has_more": False,
            }
        rows = conn.execute(
            """
            SELECT chunk_index, content, content_bytes
            FROM work_item_artifact_chunks
            WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?
              AND chunk_index >= ?
            ORDER BY chunk_index ASC
            LIMIT ?
            """,
            (item_id, artifact_id, section_id, cursor, limit_chunks),
        ).fetchall()
        content = "".join(row["content"] for row in rows)
        returned_bytes = sum(int(row["content_bytes"]) for row in rows)
        next_cursor = int(rows[-1]["chunk_index"]) + 1
        has_more = next_cursor < chunk_count
        return {
            "work_item_id": item_id,
            "artifact_id": artifact_id,
            "artifact_revision": artifact["revision"],
            "artifact_state": artifact["state"],
            "section_id": section_id,
            "section_title": section["title"],
            "cursor": cursor,
            "returned_chunks": len(rows),
            "returned_bytes": returned_bytes,
            "content": content,
            "next_cursor": next_cursor if has_more else None,
            "has_more": has_more,
        }
    finally:
        conn.close()


def finalize_artifact(
    db_path: str | Path,
    item_id: str,
    artifact_id: str,
    *,
    expected_artifact_revision: int,
    summary: str | None = None,
) -> dict[str, Any]:
    artifact_id = _artifact_id(artifact_id)
    expected_artifact_revision = _positive_revision(
        expected_artifact_revision, "expected_artifact_revision"
    )
    if summary is not None:
        summary = _optional_text(summary, "summary", max_chars=2_000)

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _require_work_item(conn, item_id)
        artifact = _require_artifact(conn, item_id, artifact_id)
        if artifact["revision"] != expected_artifact_revision:
            raise ArtifactConflictError(
                f"artifact revision conflict for {item_id}/{artifact_id}: "
                f"expected {expected_artifact_revision}, current {artifact['revision']}"
            )
        if artifact["state"] != "draft":
            raise ValidationError(
                f"artifact is already {artifact['state']}; only draft artifacts can be finalized"
            )
        count_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM work_item_artifact_chunks
            WHERE work_item_id = ? AND artifact_id = ?
            """,
            (item_id, artifact_id),
        ).fetchone()
        assert count_row is not None
        if int(count_row["count"]) == 0:
            raise ValidationError("cannot finalize an artifact with no content chunks")

        now = _now_iso()
        new_revision = expected_artifact_revision + 1
        if summary is None:
            cursor = conn.execute(
                """
                UPDATE work_item_artifacts
                SET state = 'complete', revision = ?, updated_at = ?
                WHERE work_item_id = ? AND artifact_id = ? AND revision = ?
                """,
                (new_revision, now, item_id, artifact_id, expected_artifact_revision),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE work_item_artifacts
                SET state = 'complete', summary = ?, revision = ?, updated_at = ?
                WHERE work_item_id = ? AND artifact_id = ? AND revision = ?
                """,
                (
                    summary,
                    new_revision,
                    now,
                    item_id,
                    artifact_id,
                    expected_artifact_revision,
                ),
            )
        if cursor.rowcount != 1:
            raise ArtifactConflictError(
                f"artifact revision conflict for {item_id}/{artifact_id}; reread before retrying"
            )
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return get_artifact(db_path, item_id, artifact_id)
