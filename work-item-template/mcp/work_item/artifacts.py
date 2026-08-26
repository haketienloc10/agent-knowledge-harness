from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import ConflictError, NotFoundError, ValidationError, resolve_db_path

ARTIFACT_TYPES = {"intake", "investigation", "plan", "review", "report"}
ARTIFACT_STATES = {"draft", "complete"}
ARTIFACT_CHUNK_MAX_BYTES = 32_000
ARTIFACT_READ_MAX_BYTES = 32_000
ARTIFACT_LIST_MAX = 100
ARTIFACT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")
SECTION_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class ArtifactConflictError(ConflictError):
    pass


class ArtifactNotFoundError(NotFoundError):
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
            section_order INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            char_count INTEGER NOT NULL DEFAULT 0,
            byte_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (work_item_id, artifact_id, section_id),
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
            char_count INTEGER NOT NULL,
            byte_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (work_item_id, artifact_id, section_id, chunk_index),
            FOREIGN KEY (work_item_id, artifact_id, section_id)
                REFERENCES work_item_artifact_sections(work_item_id, artifact_id, section_id)
                ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_item_artifacts_type ON work_item_artifacts(work_item_id, type, updated_at)"
    )
    return conn


def _validate_type(value: str) -> str:
    artifact_type = _required_text(value, "type", max_chars=64)
    if artifact_type not in ARTIFACT_TYPES:
        raise ValidationError("type must be one of: " + ", ".join(sorted(ARTIFACT_TYPES)))
    return artifact_type


def _validate_artifact_id(value: str) -> str:
    artifact_id = _required_text(value, "artifact_id", max_chars=128)
    if not ARTIFACT_ID_RE.fullmatch(artifact_id):
        raise ValidationError("artifact_id must use <type>:<id>, for example report:1")
    return artifact_id


def _validate_section_id(value: str) -> str:
    section_id = _required_text(value, "section_id", max_chars=128)
    if not SECTION_ID_RE.fullmatch(section_id):
        raise ValidationError("section_id must start with a lowercase letter and contain only lowercase letters, digits, _ or -")
    return section_id


def _artifact_row(row: sqlite3.Row, *, section_count: int = 0, char_count: int = 0, byte_count: int = 0) -> dict[str, Any]:
    return {
        "artifact_id": row["artifact_id"],
        "type": row["type"],
        "state": row["state"],
        "title": row["title"],
        "summary": row["summary"],
        "based_on_work_item_revision": row["based_on_work_item_revision"],
        "revision": row["revision"],
        "section_count": section_count,
        "char_count": char_count,
        "byte_count": byte_count,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _artifact_totals(conn: sqlite3.Connection, work_item_id: str, artifact_id: str) -> tuple[int, int, int]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS section_count,
               COALESCE(SUM(char_count), 0) AS char_count,
               COALESCE(SUM(byte_count), 0) AS byte_count
        FROM work_item_artifact_sections
        WHERE work_item_id = ? AND artifact_id = ?
        """,
        (work_item_id, artifact_id),
    ).fetchone()
    assert row is not None
    return int(row["section_count"]), int(row["char_count"]), int(row["byte_count"])


def list_artifacts(
    db_path: str | Path,
    work_item_id: str,
    *,
    artifact_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    work_item_id = _required_text(work_item_id, "work_item_id", max_chars=256)
    if artifact_type is not None:
        artifact_type = _validate_type(artifact_type)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= ARTIFACT_LIST_MAX:
        raise ValidationError(f"limit must be an integer between 1 and {ARTIFACT_LIST_MAX}")

    conn = _connect(db_path)
    try:
        exists = conn.execute("SELECT 1 FROM work_items WHERE id = ?", (work_item_id,)).fetchone()
        if exists is None:
            raise NotFoundError(f"work item not found: {work_item_id}")
        if artifact_type is None:
            rows = conn.execute(
                "SELECT * FROM work_item_artifacts WHERE work_item_id = ? ORDER BY updated_at DESC, artifact_id ASC LIMIT ?",
                (work_item_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM work_item_artifacts WHERE work_item_id = ? AND type = ? ORDER BY updated_at DESC, artifact_id ASC LIMIT ?",
                (work_item_id, artifact_type, limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            section_count, char_count, byte_count = _artifact_totals(conn, work_item_id, row["artifact_id"])
            result.append(
                _artifact_row(
                    row,
                    section_count=section_count,
                    char_count=char_count,
                    byte_count=byte_count,
                )
            )
        return result
    finally:
        conn.close()


def get_artifact(db_path: str | Path, work_item_id: str, artifact_id: str) -> dict[str, Any]:
    work_item_id = _required_text(work_item_id, "work_item_id", max_chars=256)
    artifact_id = _validate_artifact_id(artifact_id)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM work_item_artifacts WHERE work_item_id = ? AND artifact_id = ?",
            (work_item_id, artifact_id),
        ).fetchone()
        if row is None:
            raise ArtifactNotFoundError(f"artifact not found: {work_item_id}/{artifact_id}")
        sections = conn.execute(
            """
            SELECT section_id, title, section_order, chunk_count, char_count, byte_count
            FROM work_item_artifact_sections
            WHERE work_item_id = ? AND artifact_id = ?
            ORDER BY section_order ASC, section_id ASC
            """,
            (work_item_id, artifact_id),
        ).fetchall()
        metadata = _artifact_row(
            row,
            section_count=len(sections),
            char_count=sum(int(section["char_count"]) for section in sections),
            byte_count=sum(int(section["byte_count"]) for section in sections),
        )
        metadata["sections"] = [
            {
                "section_id": section["section_id"],
                "title": section["title"],
                "order": section["section_order"],
                "chunk_count": section["chunk_count"],
                "char_count": section["char_count"],
                "byte_count": section["byte_count"],
            }
            for section in sections
        ]
        return metadata
    finally:
        conn.close()


def _next_artifact_id(conn: sqlite3.Connection, work_item_id: str, artifact_type: str) -> str:
    prefix = artifact_type + ":"
    rows = conn.execute(
        "SELECT artifact_id FROM work_item_artifacts WHERE work_item_id = ? AND artifact_id LIKE ?",
        (work_item_id, prefix + "%"),
    ).fetchall()
    highest = 0
    for row in rows:
        suffix = str(row["artifact_id"])[len(prefix) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{artifact_type}:{highest + 1}"


def create_artifact(
    db_path: str | Path,
    work_item_id: str,
    *,
    artifact_type: str,
    title: str,
    summary: str,
    based_on_work_item_revision: int,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    work_item_id = _required_text(work_item_id, "work_item_id", max_chars=256)
    artifact_type = _validate_type(artifact_type)
    title = _required_text(title, "title", max_chars=1_000)
    summary = _optional_text(summary, "summary", max_chars=4_000)
    if not isinstance(based_on_work_item_revision, int) or isinstance(based_on_work_item_revision, bool) or based_on_work_item_revision < 1:
        raise ValidationError("based_on_work_item_revision must be a positive integer")
    if artifact_id is not None:
        artifact_id = _validate_artifact_id(artifact_id)
        if not artifact_id.startswith(artifact_type + ":"):
            raise ValidationError("artifact_id prefix must match artifact type")

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        work_item = conn.execute("SELECT revision FROM work_items WHERE id = ?", (work_item_id,)).fetchone()
        if work_item is None:
            raise NotFoundError(f"work item not found: {work_item_id}")
        current_revision = int(work_item["revision"])
        if current_revision != based_on_work_item_revision:
            raise ConflictError(
                f"revision conflict for {work_item_id}: expected {based_on_work_item_revision}, current {current_revision}"
            )
        final_artifact_id = artifact_id or _next_artifact_id(conn, work_item_id, artifact_type)
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
                    work_item_id,
                    final_artifact_id,
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
                f"artifact already exists: {work_item_id}/{final_artifact_id}"
            ) from exc
        conn.execute("COMMIT")
        return get_artifact(db_path, work_item_id, final_artifact_id)
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def append_artifact(
    db_path: str | Path,
    work_item_id: str,
    artifact_id: str,
    *,
    expected_artifact_revision: int,
    section_id: str,
    content: str,
    section_title: str | None = None,
) -> dict[str, Any]:
    work_item_id = _required_text(work_item_id, "work_item_id", max_chars=256)
    artifact_id = _validate_artifact_id(artifact_id)
    section_id = _validate_section_id(section_id)
    if not isinstance(expected_artifact_revision, int) or isinstance(expected_artifact_revision, bool) or expected_artifact_revision < 1:
        raise ValidationError("expected_artifact_revision must be a positive integer")
    content = _required_text(content, "content", max_chars=ARTIFACT_CHUNK_MAX_BYTES)
    encoded = content.encode("utf-8")
    if len(encoded) > ARTIFACT_CHUNK_MAX_BYTES:
        raise ValidationError(
            f"artifact chunk exceeds {ARTIFACT_CHUNK_MAX_BYTES} UTF-8 bytes; split it into smaller chunks"
        )
    if section_title is not None:
        section_title = _required_text(section_title, "section_title", max_chars=500)

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        artifact = conn.execute(
            "SELECT * FROM work_item_artifacts WHERE work_item_id = ? AND artifact_id = ?",
            (work_item_id, artifact_id),
        ).fetchone()
        if artifact is None:
            raise ArtifactNotFoundError(f"artifact not found: {work_item_id}/{artifact_id}")
        current_revision = int(artifact["revision"])
        if current_revision != expected_artifact_revision:
            raise ArtifactConflictError(
                f"artifact revision conflict for {work_item_id}/{artifact_id}: expected {expected_artifact_revision}, current {current_revision}"
            )
        if artifact["state"] != "draft":
            raise ArtifactConflictError(
                f"artifact is complete and immutable: {work_item_id}/{artifact_id}"
            )

        section = conn.execute(
            "SELECT * FROM work_item_artifact_sections WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?",
            (work_item_id, artifact_id, section_id),
        ).fetchone()
        if section is None:
            if section_title is None:
                raise ValidationError("section_title is required when appending the first chunk of a section")
            order_row = conn.execute(
                "SELECT COALESCE(MAX(section_order), 0) + 1 AS next_order FROM work_item_artifact_sections WHERE work_item_id = ? AND artifact_id = ?",
                (work_item_id, artifact_id),
            ).fetchone()
            assert order_row is not None
            conn.execute(
                """
                INSERT INTO work_item_artifact_sections(
                    work_item_id, artifact_id, section_id, title, section_order,
                    chunk_count, char_count, byte_count
                ) VALUES (?, ?, ?, ?, ?, 0, 0, 0)
                """,
                (work_item_id, artifact_id, section_id, section_title, int(order_row["next_order"])),
            )
            section = conn.execute(
                "SELECT * FROM work_item_artifact_sections WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?",
                (work_item_id, artifact_id, section_id),
            ).fetchone()
            assert section is not None
        elif section_title is not None and section_title != section["title"]:
            raise ValidationError(
                f"section_title does not match existing title {section['title']!r}"
            )

        chunk_index = int(section["chunk_count"])
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO work_item_artifact_chunks(
                work_item_id, artifact_id, section_id, chunk_index,
                content, char_count, byte_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_item_id,
                artifact_id,
                section_id,
                chunk_index,
                content,
                len(content),
                len(encoded),
                now,
            ),
        )
        conn.execute(
            """
            UPDATE work_item_artifact_sections
            SET chunk_count = chunk_count + 1,
                char_count = char_count + ?,
                byte_count = byte_count + ?
            WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?
            """,
            (len(content), len(encoded), work_item_id, artifact_id, section_id),
        )
        new_revision = current_revision + 1
        conn.execute(
            """
            UPDATE work_item_artifacts
            SET revision = ?, updated_at = ?
            WHERE work_item_id = ? AND artifact_id = ? AND revision = ?
            """,
            (new_revision, now, work_item_id, artifact_id, current_revision),
        )
        conn.execute("COMMIT")
        return get_artifact(db_path, work_item_id, artifact_id)
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def _take_utf8_prefix(text: str, start: int, max_bytes: int) -> tuple[str, int, int]:
    used = 0
    end = start
    length = len(text)
    while end < length:
        char_bytes = len(text[end].encode("utf-8"))
        if used + char_bytes > max_bytes:
            break
        used += char_bytes
        end += 1
    return text[start:end], end, used


def read_artifact_section(
    db_path: str | Path,
    work_item_id: str,
    artifact_id: str,
    *,
    section_id: str,
    cursor: str | None = None,
    limit_bytes: int = ARTIFACT_READ_MAX_BYTES,
) -> dict[str, Any]:
    work_item_id = _required_text(work_item_id, "work_item_id", max_chars=256)
    artifact_id = _validate_artifact_id(artifact_id)
    section_id = _validate_section_id(section_id)
    if not isinstance(limit_bytes, int) or isinstance(limit_bytes, bool) or not 1 <= limit_bytes <= ARTIFACT_READ_MAX_BYTES:
        raise ValidationError(
            f"limit_bytes must be an integer between 1 and {ARTIFACT_READ_MAX_BYTES}"
        )

    chunk_index = 0
    char_offset = 0
    if cursor:
        try:
            left, right = cursor.split(":", 1)
            chunk_index = int(left)
            char_offset = int(right)
        except (ValueError, AttributeError) as exc:
            raise ValidationError("cursor is invalid") from exc
        if chunk_index < 0 or char_offset < 0:
            raise ValidationError("cursor is invalid")

    conn = _connect(db_path)
    try:
        artifact = conn.execute(
            "SELECT revision, state FROM work_item_artifacts WHERE work_item_id = ? AND artifact_id = ?",
            (work_item_id, artifact_id),
        ).fetchone()
        if artifact is None:
            raise ArtifactNotFoundError(f"artifact not found: {work_item_id}/{artifact_id}")
        section = conn.execute(
            "SELECT title, chunk_count, char_count, byte_count FROM work_item_artifact_sections WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?",
            (work_item_id, artifact_id, section_id),
        ).fetchone()
        if section is None:
            raise ArtifactNotFoundError(
                f"artifact section not found: {work_item_id}/{artifact_id}/{section_id}"
            )

        parts: list[str] = []
        remaining = limit_bytes
        current_chunk = chunk_index
        current_offset = char_offset
        next_cursor: str | None = None
        while remaining > 0:
            row = conn.execute(
                """
                SELECT chunk_index, content
                FROM work_item_artifact_chunks
                WHERE work_item_id = ? AND artifact_id = ? AND section_id = ? AND chunk_index >= ?
                ORDER BY chunk_index ASC
                LIMIT 1
                """,
                (work_item_id, artifact_id, section_id, current_chunk),
            ).fetchone()
            if row is None:
                next_cursor = None
                break
            actual_index = int(row["chunk_index"])
            content = str(row["content"])
            if actual_index != current_chunk:
                current_offset = 0
            if current_offset > len(content):
                raise ValidationError("cursor points beyond the stored chunk")
            piece, end_offset, used = _take_utf8_prefix(content, current_offset, remaining)
            parts.append(piece)
            remaining -= used
            if end_offset < len(content):
                next_cursor = f"{actual_index}:{end_offset}"
                break
            current_chunk = actual_index + 1
            current_offset = 0
            more = conn.execute(
                """
                SELECT 1 FROM work_item_artifact_chunks
                WHERE work_item_id = ? AND artifact_id = ? AND section_id = ? AND chunk_index >= ?
                LIMIT 1
                """,
                (work_item_id, artifact_id, section_id, current_chunk),
            ).fetchone()
            next_cursor = f"{current_chunk}:0" if more is not None else None
            if remaining == 0:
                break

        content_out = "".join(parts)
        return {
            "artifact_id": artifact_id,
            "artifact_revision": int(artifact["revision"]),
            "state": artifact["state"],
            "section_id": section_id,
            "section_title": section["title"],
            "content": content_out,
            "returned_bytes": len(content_out.encode("utf-8")),
            "next_cursor": next_cursor,
            "section_char_count": int(section["char_count"]),
            "section_byte_count": int(section["byte_count"]),
        }
    finally:
        conn.close()


def finalize_artifact(
    db_path: str | Path,
    work_item_id: str,
    artifact_id: str,
    *,
    expected_artifact_revision: int,
) -> dict[str, Any]:
    work_item_id = _required_text(work_item_id, "work_item_id", max_chars=256)
    artifact_id = _validate_artifact_id(artifact_id)
    if not isinstance(expected_artifact_revision, int) or isinstance(expected_artifact_revision, bool) or expected_artifact_revision < 1:
        raise ValidationError("expected_artifact_revision must be a positive integer")

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        artifact = conn.execute(
            "SELECT * FROM work_item_artifacts WHERE work_item_id = ? AND artifact_id = ?",
            (work_item_id, artifact_id),
        ).fetchone()
        if artifact is None:
            raise ArtifactNotFoundError(f"artifact not found: {work_item_id}/{artifact_id}")
        current_revision = int(artifact["revision"])
        if current_revision != expected_artifact_revision:
            raise ArtifactConflictError(
                f"artifact revision conflict for {work_item_id}/{artifact_id}: expected {expected_artifact_revision}, current {current_revision}"
            )
        if artifact["state"] != "draft":
            raise ArtifactConflictError(
                f"artifact is already complete: {work_item_id}/{artifact_id}"
            )
        content = conn.execute(
            "SELECT 1 FROM work_item_artifact_chunks WHERE work_item_id = ? AND artifact_id = ? LIMIT 1",
            (work_item_id, artifact_id),
        ).fetchone()
        if content is None:
            raise ValidationError("cannot finalize an artifact without content")
        now = _now_iso()
        conn.execute(
            """
            UPDATE work_item_artifacts
            SET state = 'complete', revision = ?, updated_at = ?
            WHERE work_item_id = ? AND artifact_id = ? AND revision = ?
            """,
            (current_revision + 1, now, work_item_id, artifact_id, current_revision),
        )
        conn.execute("COMMIT")
        return get_artifact(db_path, work_item_id, artifact_id)
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
