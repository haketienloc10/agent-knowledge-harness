#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

STATUS_ORDER = ("active", "waiting", "blocked", "done", "cancelled")


class CliError(RuntimeError):
    pass


class CliNotFoundError(CliError):
    pass


def _db_path() -> Path:
    raw = os.environ.get("WORK_ITEM_DB_PATH", "").strip()
    if not raw:
        raise CliError(
            "WORK_ITEM_DB_PATH must point to the global Work Item SQLite database"
        )
    path = Path(raw).expanduser().resolve()
    if path.exists() and path.is_dir():
        raise CliError(f"Work Item DB path is a directory: {path}")
    return path


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise CliError(f"Work Item database does not exist: {db_path}")
    uri = f"file:{quote(str(db_path), safe='/')}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    except sqlite3.Error as exc:
        raise CliError(f"cannot open Work Item database read-only: {exc}") from exc
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        item = json.loads(row["document_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise CliError(f"invalid Work Item JSON for {row['id']}: {exc}") from exc
    item["revision"] = row["revision"]
    item["created_at"] = row["created_at"]
    item["updated_at"] = row["updated_at"]
    return item


def _summarize_work_items(db_path: Path) -> dict[str, Any]:
    conn = _connect_readonly(db_path)
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM work_items GROUP BY status"
        ).fetchall()
    except sqlite3.Error as exc:
        raise CliError(f"cannot count Work Items: {exc}") from exc
    finally:
        conn.close()
    counts = {status: 0 for status in STATUS_ORDER}
    unknown = 0
    for row in rows:
        status = str(row["status"])
        count = int(row["count"])
        if status in counts:
            counts[status] = count
        else:
            unknown += count
    return {"total": sum(counts.values()) + unknown, "statuses": counts, "unknown": unknown}


def _list_work_items(
    db_path: Path,
    *,
    status: str | None = None,
    repository: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if status is not None and status not in STATUS_ORDER:
        raise CliError(f"unsupported status filter: {status}")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
        raise CliError("limit must be an integer between 1 and 200")

    conn = _connect_readonly(db_path)
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
    except sqlite3.Error as exc:
        raise CliError(f"cannot list Work Items: {exc}") from exc
    finally:
        conn.close()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = _decode_row(row)
        repos = item.get("repos", {})
        if repository is not None and repository not in repos:
            continue
        result.append(
            {
                "id": item.get("id", row["id"]),
                "title": item.get("title", ""),
                "status": item.get("status", row["status"]),
                "phase": item.get("phase", ""),
                "revision": item["revision"],
                "updated_at": item["updated_at"],
                "repositories": sorted(repos),
            }
        )
        if len(result) >= limit:
            break
    return result


def _get_work_item(db_path: Path, item_id: str) -> dict[str, Any]:
    item_id = item_id.strip()
    if not item_id:
        raise CliError("Work Item id must not be empty")
    conn = _connect_readonly(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM work_items WHERE id = ?", (item_id,)
        ).fetchone()
    except sqlite3.Error as exc:
        raise CliError(f"cannot read Work Item {item_id}: {exc}") from exc
    finally:
        conn.close()
    if row is None:
        raise CliNotFoundError(f"Work Item not found: {item_id}")
    return _decode_row(row)


def _list_artifacts_readonly(db_path: Path, item_id: str) -> list[dict[str, Any]]:
    conn = _connect_readonly(db_path)
    try:
        if not _table_exists(conn, "work_item_artifacts"):
            return []
        rows = conn.execute(
            """
            SELECT a.*,
                   COUNT(s.section_id) AS section_count,
                   COALESCE(SUM(s.char_count), 0) AS char_count,
                   COALESCE(SUM(s.byte_count), 0) AS byte_count
            FROM work_item_artifacts a
            LEFT JOIN work_item_artifact_sections s
              ON s.work_item_id = a.work_item_id AND s.artifact_id = a.artifact_id
            WHERE a.work_item_id = ?
            GROUP BY a.work_item_id, a.artifact_id
            ORDER BY a.updated_at DESC, a.artifact_id ASC
            """,
            (item_id,),
        ).fetchall()
        return [
            {
                "artifact_id": row["artifact_id"],
                "type": row["type"],
                "state": row["state"],
                "title": row["title"],
                "summary": row["summary"],
                "based_on_work_item_revision": row["based_on_work_item_revision"],
                "revision": row["revision"],
                "section_count": int(row["section_count"]),
                "char_count": int(row["char_count"]),
                "byte_count": int(row["byte_count"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    except sqlite3.Error as exc:
        raise CliError(f"cannot list Work Item artifacts: {exc}") from exc
    finally:
        conn.close()


def _get_artifact_readonly(db_path: Path, item_id: str, artifact_id: str) -> dict[str, Any]:
    conn = _connect_readonly(db_path)
    try:
        if not _table_exists(conn, "work_item_artifacts"):
            raise CliNotFoundError(f"Artifact not found: {item_id}/{artifact_id}")
        artifact = conn.execute(
            "SELECT * FROM work_item_artifacts WHERE work_item_id = ? AND artifact_id = ?",
            (item_id, artifact_id),
        ).fetchone()
        if artifact is None:
            raise CliNotFoundError(f"Artifact not found: {item_id}/{artifact_id}")
        sections = conn.execute(
            """
            SELECT section_id, title, section_order, chunk_count, char_count, byte_count
            FROM work_item_artifact_sections
            WHERE work_item_id = ? AND artifact_id = ?
            ORDER BY section_order ASC, section_id ASC
            """,
            (item_id, artifact_id),
        ).fetchall()
        result = {
            "work_item_id": item_id,
            "artifact_id": artifact["artifact_id"],
            "type": artifact["type"],
            "state": artifact["state"],
            "title": artifact["title"],
            "summary": artifact["summary"],
            "based_on_work_item_revision": artifact["based_on_work_item_revision"],
            "revision": artifact["revision"],
            "created_at": artifact["created_at"],
            "updated_at": artifact["updated_at"],
            "sections": [],
        }
        for section in sections:
            chunks = conn.execute(
                """
                SELECT content FROM work_item_artifact_chunks
                WHERE work_item_id = ? AND artifact_id = ? AND section_id = ?
                ORDER BY chunk_index ASC
                """,
                (item_id, artifact_id, section["section_id"]),
            ).fetchall()
            result["sections"].append(
                {
                    "section_id": section["section_id"],
                    "title": section["title"],
                    "order": section["section_order"],
                    "chunk_count": section["chunk_count"],
                    "char_count": section["char_count"],
                    "byte_count": section["byte_count"],
                    "content": "".join(str(chunk["content"]) for chunk in chunks),
                }
            )
        return result
    except sqlite3.Error as exc:
        raise CliError(f"cannot read Work Item artifact: {exc}") from exc
    finally:
        conn.close()


def _width() -> int:
    return max(88, min(shutil.get_terminal_size(fallback=(120, 30)).columns, 160))


def _line(char: str = "-") -> str:
    return char * _width()


def _local_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except (TypeError, ValueError):
        return str(value)


def _single_line(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _truncate(value: str, width: int) -> str:
    if width <= 1:
        return value[:width]
    return value if len(value) <= width else value[: width - 1] + "…"


def _wrap(value: Any, *, indent: str = "  ", subsequent: str | None = None) -> list[str]:
    text = _single_line(value)
    if not text:
        return [indent + "-"]
    subsequent = indent if subsequent is None else subsequent
    available = max(20, _width() - len(indent))
    return textwrap.wrap(
        text,
        width=available,
        initial_indent=indent,
        subsequent_indent=subsequent,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [indent]


def _status_label(status: str) -> str:
    return f"[{status.upper()}]"


def render_list(summary: dict[str, Any], items: list[dict[str, Any]]) -> str:
    counts = summary["statuses"]
    parts = [f"TOTAL {summary['total']}"]
    parts.extend(f"{status.upper()} {counts.get(status, 0)}" for status in STATUS_ORDER)
    if summary.get("unknown"):
        parts.append(f"UNKNOWN {summary['unknown']}")
    lines = ["WORK ITEMS", "  ".join(parts), _line()]

    if not items:
        lines.append("No Work Items matched the current filters.")
        return "\n".join(lines)

    id_w = min(28, max(14, max(len(item["id"]) for item in items)))
    status_w = 10
    phase_w = min(18, max(10, max(len(item["phase"]) for item in items)))
    repos_w = min(22, max(8, max(len(",".join(item["repositories"])) for item in items)))
    updated_w = 16
    fixed = id_w + status_w + phase_w + repos_w + updated_w + 10
    title_w = max(16, _width() - fixed)

    lines.append(
        f"{'ID':<{id_w}}  {'STATUS':<{status_w}}  {'PHASE':<{phase_w}}  "
        f"{'REPOS':<{repos_w}}  {'UPDATED':<{updated_w}}  TITLE"
    )
    lines.append(_line())
    for item in items:
        updated = _local_time(item["updated_at"])[:16]
        repos = ",".join(item["repositories"]) or "-"
        lines.append(
            f"{_truncate(item['id'], id_w):<{id_w}}  "
            f"{item['status']:<{status_w}}  "
            f"{_truncate(item['phase'], phase_w):<{phase_w}}  "
            f"{_truncate(repos, repos_w):<{repos_w}}  "
            f"{updated:<{updated_w}}  "
            f"{_truncate(_single_line(item['title']), title_w)}"
        )
    return "\n".join(lines)


def _section(lines: list[str], title: str, count: int | None = None) -> None:
    suffix = "" if count is None else f" ({count})"
    lines.extend(["", f"{title}{suffix}", _line("-")])


def _render_string_list(lines: list[str], title: str, values: Iterable[str]) -> None:
    values = list(values)
    _section(lines, title, len(values))
    if not values:
        lines.append("  -")
        return
    for index, value in enumerate(values, 1):
        lines.extend(_wrap(value, indent=f"  {index}. ", subsequent="     "))


def _render_object_fields(lines: list[str], obj: dict[str, Any], *, indent: str = "    ") -> None:
    preferred = [
        "status",
        "type",
        "kind",
        "repo",
        "owner",
        "from",
        "to",
        "question",
        "answer",
        "summary",
        "source",
        "at",
    ]
    keys = [key for key in preferred if key in obj]
    keys.extend(sorted(key for key in obj if key not in keys and key != "id"))
    for key in keys:
        value = obj[key]
        label = key.replace("_", " ")
        if isinstance(value, list):
            lines.append(f"{indent}{label}: ({len(value)})")
            if not value:
                lines.append(f"{indent}  -")
            else:
                for entry in value:
                    rendered = (
                        json.dumps(entry, ensure_ascii=False, sort_keys=True)
                        if isinstance(entry, (dict, list))
                        else str(entry)
                    )
                    lines.extend(_wrap(rendered, indent=f"{indent}  - ", subsequent=f"{indent}    "))
        elif isinstance(value, dict):
            lines.append(f"{indent}{label}:")
            for nested_key, nested_value in sorted(value.items()):
                rendered = (
                    json.dumps(nested_value, ensure_ascii=False, sort_keys=True)
                    if isinstance(nested_value, (dict, list))
                    else str(nested_value)
                )
                lines.extend(
                    _wrap(
                        rendered,
                        indent=f"{indent}  {nested_key}: ",
                        subsequent=f"{indent}    ",
                    )
                )
        else:
            lines.extend(_wrap(value, indent=f"{indent}{label}: ", subsequent=f"{indent}  "))


def _render_records(lines: list[str], title: str, records: list[dict[str, Any]]) -> None:
    _section(lines, title, len(records))
    if not records:
        lines.append("  -")
        return
    for index, record in enumerate(records, 1):
        record_id = record.get("id")
        lines.append(f"  {index}. {record_id}" if record_id else f"  {index}.")
        _render_object_fields(lines, record)


def _render_artifact_index(lines: list[str], artifacts: list[dict[str, Any]]) -> None:
    _section(lines, "ARTIFACTS", len(artifacts))
    if not artifacts:
        lines.append("  -")
        return
    for artifact in artifacts:
        lines.append(
            f"  {artifact['artifact_id']}  [{str(artifact['state']).upper()}]  "
            f"type={artifact['type']}  rev={artifact['revision']}  "
            f"sections={artifact['section_count']}  bytes={artifact['byte_count']}"
        )
        lines.extend(_wrap(artifact.get("title", ""), indent="    title: ", subsequent="      "))
        lines.extend(_wrap(artifact.get("summary", ""), indent="    summary: ", subsequent="      "))
        lines.append(
            f"    based on Work Item revision: {artifact['based_on_work_item_revision']}"
        )


def render_detail(item: dict[str, Any]) -> str:
    lines = [
        _line("="),
        f"{item['id']}  {_status_label(item['status'])}  phase={item['phase']}  revision={item['revision']}",
        _single_line(item["title"]),
        f"Created: {_local_time(item['created_at'])}",
        f"Updated: {_local_time(item['updated_at'])}",
        _line("="),
    ]

    _section(lines, "SUMMARY")
    lines.extend(_wrap(item.get("summary", "")))
    _render_string_list(lines, "CURRENT REQUIREMENTS", item.get("current_requirements", []))

    repos = item.get("repos", {})
    _section(lines, "REPOSITORIES", len(repos))
    if not repos:
        lines.append("  -")
    else:
        for repo, state in sorted(repos.items()):
            lines.append(f"  {repo}  {_status_label(state.get('status', 'unknown'))}")
            lines.extend(
                _wrap(
                    state.get("summary", ""),
                    indent="    summary: ",
                    subsequent="      ",
                )
            )
            verification = state.get("verification", [])
            lines.append(f"    verification ({len(verification)}):")
            if not verification:
                lines.append("      -")
            else:
                for entry in verification:
                    lines.extend(_wrap(entry, indent="      - ", subsequent="        "))
            extras = {
                key: value
                for key, value in state.items()
                if key not in {"status", "summary", "verification"}
            }
            if extras:
                _render_object_fields(lines, extras, indent="    ")

    _render_artifact_index(lines, item.get("artifacts", []))
    _render_records(lines, "QUESTIONS", item.get("questions", []))
    _render_records(lines, "DECISIONS", item.get("decisions", []))
    _render_records(lines, "CHANGES", item.get("changes", []))
    _render_records(lines, "BLOCKERS", item.get("blockers", []))
    _render_records(lines, "HANDOFFS", item.get("handoffs", []))
    _render_records(lines, "NEXT ACTIONS", item.get("next_actions", []))
    _render_records(lines, "CHECKPOINTS", item.get("checkpoints", []))
    return "\n".join(lines)


def render_artifact(artifact: dict[str, Any], *, section_id: str | None = None) -> str:
    selected = artifact["sections"]
    if section_id is not None:
        selected = [section for section in selected if section["section_id"] == section_id]
        if not selected:
            raise CliNotFoundError(
                f"Artifact section not found: {artifact['work_item_id']}/{artifact['artifact_id']}/{section_id}"
            )

    lines = [
        _line("="),
        f"{artifact['work_item_id']} / {artifact['artifact_id']}  "
        f"[{str(artifact['state']).upper()}]  type={artifact['type']}  revision={artifact['revision']}",
        _single_line(artifact["title"]),
        f"Based on Work Item revision: {artifact['based_on_work_item_revision']}",
        f"Created: {_local_time(artifact['created_at'])}",
        f"Updated: {_local_time(artifact['updated_at'])}",
        _line("="),
        "",
        "SUMMARY",
        _line("-"),
    ]
    lines.extend(_wrap(artifact.get("summary", "")))
    for section in selected:
        lines.extend(
            [
                "",
                f"{section['order']}. {section['title']}  [{section['section_id']}]",
                f"   chunks={section['chunk_count']}  chars={section['char_count']}  bytes={section['byte_count']}",
                _line("-"),
            ]
        )
        content = str(section.get("content", ""))
        lines.append(content if content else "-")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-work-item",
        description="Strictly read-only human view of the canonical Global Work Item database.",
    )
    sub = parser.add_subparsers(dest="command")

    list_parser = sub.add_parser("list", help="Show ticket counts and a compact Work Item table.")
    list_parser.add_argument("--status", choices=STATUS_ORDER)
    list_parser.add_argument("--repository")
    list_parser.add_argument("--limit", type=int, default=50)

    show_parser = sub.add_parser("show", help="Show one Work Item plus a thin artifact index.")
    show_parser.add_argument("id")
    show_parser.add_argument("--json", action="store_true", help="Print Work Item plus artifact index as JSON.")

    artifact_parser = sub.add_parser("artifact", help="Show full optional artifact content for human inspection.")
    artifact_parser.add_argument("id", help="Canonical Work Item id")
    artifact_parser.add_argument("artifact_id")
    artifact_parser.add_argument("--section", dest="section_id", help="Show only one section")
    artifact_parser.add_argument("--json", action="store_true", help="Print the complete selected artifact as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command or "list"

    try:
        db = _db_path()
        if command == "list":
            summary = _summarize_work_items(db)
            items = _list_work_items(
                db,
                status=getattr(args, "status", None),
                repository=getattr(args, "repository", None),
                limit=getattr(args, "limit", 50),
            )
            print(render_list(summary, items))
            return 0

        if command == "show":
            item = _get_work_item(db, args.id)
            item["artifacts"] = _list_artifacts_readonly(db, args.id)
            if args.json:
                print(json.dumps(item, ensure_ascii=False, indent=2, sort_keys=False))
            else:
                print(render_detail(item))
            return 0

        if command == "artifact":
            artifact = _get_artifact_readonly(db, args.id, args.artifact_id)
            if args.section_id is not None:
                sections = [
                    section
                    for section in artifact["sections"]
                    if section["section_id"] == args.section_id
                ]
                if not sections:
                    raise CliNotFoundError(
                        f"Artifact section not found: {args.id}/{args.artifact_id}/{args.section_id}"
                    )
                if args.json:
                    selected = dict(artifact)
                    selected["sections"] = sections
                    print(json.dumps(selected, ensure_ascii=False, indent=2, sort_keys=False))
                else:
                    print(render_artifact(artifact, section_id=args.section_id))
            elif args.json:
                print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=False))
            else:
                print(render_artifact(artifact))
            return 0

        parser.error(f"unknown command: {command}")
    except CliNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4
    except CliError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
