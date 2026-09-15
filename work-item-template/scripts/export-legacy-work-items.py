#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

WORK_ITEM_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")
ARTIFACT_FILE_BY_TYPE = {
    "intake": "intake.md",
    "investigation": "investigation.md",
    "plan": "plan.md",
    "review": "review.md",
    "report": "report.textile",
}
DEFAULT_DB = Path("~/.local/share/agent-work-items/work-items.sqlite3").expanduser()


def die(message: str) -> "None":
    raise SystemExit(f"ERROR: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export legacy SQLite Work Items into workspace filesystem dossiers."
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--db", default=os.environ.get("WORK_ITEM_DB_PATH", str(DEFAULT_DB)))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def safe_key(item_id: str) -> str:
    if not WORK_ITEM_ID_RE.fullmatch(item_id):
        die(f"legacy Work Item id is not canonical/path-safe: {item_id!r}")
    source, external_id = item_id.split(":", 1)
    return f"{source}--{external_id}"


def ensure_beneath(root: Path, target: Path) -> None:
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError:
        die(f"resolved Work Item path escapes root: {target}")


def yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def bullets(values: list[str], empty: str = "- None") -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return "\n".join(f"- {value}" for value in cleaned) if cleaned else empty


def active_records(document: dict[str, Any], collection: str, status: str) -> list[dict[str, Any]]:
    values = document.get(collection, [])
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict) and item.get("status") == status]


def render_work_item(document: dict[str, Any], revision: int, fallback_status: str) -> str:
    item_id = str(document.get("id", "")).strip()
    title = str(document.get("title", "")).strip()
    status = str(document.get("status") or fallback_status or "active").strip()
    phase = str(document.get("phase") or "intake").strip()
    summary = str(document.get("summary") or "").strip()
    requirements = document.get("current_requirements", [])
    if not isinstance(requirements, list):
        requirements = []

    decisions = [str(item.get("summary", "")).strip() for item in active_records(document, "decisions", "active")]
    questions = [str(item.get("question", "")).strip() for item in active_records(document, "questions", "open")]
    blockers = [str(item.get("summary", "")).strip() for item in active_records(document, "blockers", "open")]

    next_actions: list[str] = []
    raw_actions = document.get("next_actions", [])
    if isinstance(raw_actions, list):
        for item in raw_actions:
            if isinstance(item, dict):
                action = str(item.get("action", "")).strip()
                target = str(item.get("repo") or item.get("owner") or "").strip()
                if action:
                    next_actions.append(f"{action}{f' ({target})' if target else ''}")

    repos = document.get("repos", {})
    repo_lines: list[str] = []
    if isinstance(repos, dict):
        for name, value in sorted(repos.items()):
            if not isinstance(value, dict):
                continue
            repo_status = str(value.get("status") or "unknown")
            repo_summary = str(value.get("summary") or "").strip()
            repo_lines.append(f"- {name}: {repo_status}{f' — {repo_summary}' if repo_summary else ''}")

    return f"""---
id: {yaml_scalar(item_id)}
revision: {revision}
status: {status}
phase: {phase}
legacy_imported: true
---

# Objective

{title or summary or 'Imported legacy Work Item'}

# Current Requirements

{bullets([str(value) for value in requirements])}

# Acceptance Criteria

- Not separately represented in the legacy canonical Work Item; reconcile from imported lifecycle material if needed.

# Scope

## Repository State

{bullets(repo_lines)}

# Decisions

{bullets(decisions)}

# Open Questions

{bullets(questions)}

# Blockers

{bullets(blockers)}

# Current State

{summary or 'Imported from the legacy Work Item store. Reconcile before substantive continuation.'}

# Next Actions

{bullets(next_actions)}
"""


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def read_artifacts(conn: sqlite3.Connection, item_id: str) -> list[dict[str, Any]]:
    required = {
        "work_item_artifacts",
        "work_item_artifact_sections",
        "work_item_artifact_chunks",
    }
    if not all(table_exists(conn, table) for table in required):
        return []
    artifacts: list[dict[str, Any]] = []
    rows = conn.execute(
        "SELECT * FROM work_item_artifacts WHERE work_item_id=? ORDER BY updated_at ASC, artifact_id ASC",
        (item_id,),
    ).fetchall()
    for row in rows:
        artifact = dict(row)
        sections: list[dict[str, Any]] = []
        section_rows = conn.execute(
            "SELECT * FROM work_item_artifact_sections WHERE work_item_id=? AND artifact_id=? ORDER BY section_order ASC, section_id ASC",
            (item_id, row["artifact_id"]),
        ).fetchall()
        for section_row in section_rows:
            section = dict(section_row)
            chunks = conn.execute(
                "SELECT content FROM work_item_artifact_chunks WHERE work_item_id=? AND artifact_id=? AND section_id=? ORDER BY chunk_index ASC",
                (item_id, row["artifact_id"], section_row["section_id"]),
            ).fetchall()
            section["content"] = "".join(str(chunk["content"]) for chunk in chunks)
            sections.append(section)
        artifact["sections"] = sections
        artifacts.append(artifact)
    return artifacts


def render_artifact(artifact: dict[str, Any]) -> str:
    title = str(artifact.get("title") or artifact.get("artifact_id") or "Imported artifact")
    summary = str(artifact.get("summary") or "").strip()
    parts = [f"# {title}"]
    if summary:
        parts.extend(["", summary])
    for section in artifact.get("sections", []):
        section_title = str(section.get("title") or section.get("section_id") or "Section")
        content = str(section.get("content") or "")
        parts.extend(["", f"## {section_title}", "", content.rstrip()])
    return "\n".join(parts).rstrip() + "\n"


def write_text(path: Path, content: str, dry_run: bool) -> None:
    if path.exists():
        die(f"refusing to overwrite existing filesystem Work Item file: {path}")
    print(f"  + {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if not (workspace / "repos.yaml").is_file():
        die(f"workspace is missing repos.yaml: {workspace}")
    db = Path(args.db).expanduser().resolve()
    if not db.is_file():
        print(f"legacy Work Item DB not found; nothing to export: {db}")
        return 0

    work_items_root = (workspace / "work-items").resolve()
    backup_root = workspace / ".qiqi" / "migration-backups" / "v0024" / "legacy-work-items"
    if not args.dry_run:
        work_items_root.mkdir(parents=True, exist_ok=True)
        backup_root.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "work_items"):
            die(f"legacy DB has no work_items table: {db}")
        rows = conn.execute("SELECT * FROM work_items ORDER BY id ASC").fetchall()
        print(f"exporting {len(rows)} legacy Work Item(s) from {db}")
        for row in rows:
            item_id = str(row["id"])
            key = safe_key(item_id)
            target = work_items_root / key
            ensure_beneath(work_items_root, target)
            if target.exists() and any(target.iterdir()):
                die(f"target dossier already exists and is non-empty: {target}")

            document = json.loads(row["document_json"])
            artifacts = read_artifacts(conn, item_id)
            print(f"{item_id} -> work-items/{key}/")
            write_text(
                target / "WORK_ITEM.md",
                render_work_item(document, int(row["revision"]), str(row["status"])),
                args.dry_run,
            )

            latest_by_type: dict[str, dict[str, Any]] = {}
            for artifact in artifacts:
                artifact_type = str(artifact.get("type") or "")
                if artifact_type in ARTIFACT_FILE_BY_TYPE:
                    latest_by_type[artifact_type] = artifact
            for artifact_type, artifact in latest_by_type.items():
                write_text(
                    target / ARTIFACT_FILE_BY_TYPE[artifact_type],
                    render_artifact(artifact),
                    args.dry_run,
                )

            archive = {
                "source_db": str(db),
                "work_item": document,
                "revision": int(row["revision"]),
                "status": str(row["status"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "artifacts": artifacts,
            }
            archive_path = backup_root / f"{key}.json"
            if archive_path.exists():
                die(f"legacy export archive already exists: {archive_path}")
            print(f"  + {archive_path}")
            if not args.dry_run:
                archive_path.write_text(
                    json.dumps(archive, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
    finally:
        conn.close()

    print("legacy Work Item export complete; source SQLite DB was not modified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
