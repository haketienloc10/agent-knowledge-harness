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

from core import (
    NotFoundError,
    ValidationError,
    get_work_item,
    list_work_items,
    resolve_db_path,
)

STATUS_ORDER = ("active", "waiting", "blocked", "done", "cancelled")


def _db_path() -> Path:
    raw = os.environ.get("WORK_ITEM_DB_PATH", "").strip()
    if not raw:
        raise RuntimeError(
            "WORK_ITEM_DB_PATH must point to the global Work Item SQLite database"
        )
    return resolve_db_path(raw)


def _summarize_work_items(db_path: Path) -> dict[str, Any]:
    """Read exact ticket counts without creating a second task store or write path."""
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM work_items GROUP BY status"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return {"total": 0, "statuses": {status: 0 for status in STATUS_ORDER}}
        raise RuntimeError(f"cannot read Work Item database: {exc}") from exc
    finally:
        conn.close()
    counts = {status: 0 for status in STATUS_ORDER}
    for status, count in rows:
        if status in counts:
            counts[status] = int(count)
    return {"total": sum(counts.values()), "statuses": counts}


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
    count_line = "  ".join(
        [f"TOTAL {summary['total']}"]
        + [f"{status.upper()} {counts.get(status, 0)}" for status in STATUS_ORDER]
    )
    lines = ["WORK ITEMS", count_line, _line()]

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

    header = (
        f"{'ID':<{id_w}}  {'STATUS':<{status_w}}  {'PHASE':<{phase_w}}  "
        f"{'REPOS':<{repos_w}}  {'UPDATED':<{updated_w}}  TITLE"
    )
    lines.append(header)
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
                    lines.extend(
                        _wrap(
                            rendered,
                            indent=f"{indent}  - ",
                            subsequent=f"{indent}    ",
                        )
                    )
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
            lines.extend(
                _wrap(
                    value,
                    indent=f"{indent}{label}: ",
                    subsequent=f"{indent}  ",
                )
            )


def _render_records(lines: list[str], title: str, records: list[dict[str, Any]]) -> None:
    _section(lines, title, len(records))
    if not records:
        lines.append("  -")
        return
    for index, record in enumerate(records, 1):
        record_id = record.get("id")
        lines.append(f"  {index}. {record_id}" if record_id else f"  {index}.")
        _render_object_fields(lines, record)


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

    _render_records(lines, "QUESTIONS", item.get("questions", []))
    _render_records(lines, "DECISIONS", item.get("decisions", []))
    _render_records(lines, "CHANGES", item.get("changes", []))
    _render_records(lines, "BLOCKERS", item.get("blockers", []))
    _render_records(lines, "HANDOFFS", item.get("handoffs", []))
    _render_records(lines, "NEXT ACTIONS", item.get("next_actions", []))
    _render_records(lines, "CHECKPOINTS", item.get("checkpoints", []))
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-work-item",
        description="Read-only human view of the canonical Global Work Item database.",
    )
    sub = parser.add_subparsers(dest="command")

    list_parser = sub.add_parser(
        "list", help="Show ticket counts and a compact Work Item table."
    )
    list_parser.add_argument("--status", choices=STATUS_ORDER)
    list_parser.add_argument("--repository")
    list_parser.add_argument("--limit", type=int, default=50)

    show_parser = sub.add_parser(
        "show", help="Show one Work Item in a full human-readable layout."
    )
    show_parser.add_argument("id")
    show_parser.add_argument(
        "--json", action="store_true", help="Print the canonical document as JSON."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command or "list"

    try:
        db = _db_path()
        if command == "list":
            status = getattr(args, "status", None)
            repository = getattr(args, "repository", None)
            limit = getattr(args, "limit", 50)
            summary = _summarize_work_items(db)
            items = list_work_items(
                db, status=status, repository=repository, limit=limit
            )
            print(render_list(summary, items))
            return 0

        if command == "show":
            item = get_work_item(db, args.id)
            if args.json:
                print(json.dumps(item, ensure_ascii=False, indent=2, sort_keys=False))
            else:
                print(render_detail(item))
            return 0

        parser.error(f"unknown command: {command}")
    except NotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4
    except (ValidationError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
