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
TEXTILE_HEADING_RE = re.compile(r"^h[1-6]\.\s+")
ARTIFACT_TABLES = {
    "work_item_artifacts",
    "work_item_artifact_sections",
    "work_item_artifact_chunks",
}
ARTIFACT_FILE_BY_TYPE = {
    "intake": "intake.md",
    "investigation": "investigation.md",
    "plan": "plan.md",
    "review": "review.md",
    "report": "report.textile",
}
REVISIONED_ARTIFACT_TYPES = {"investigation", "plan", "review"}
VALID_PHASES = {
    "intake",
    "investigation",
    "planning",
    "implementation",
    "verification",
    "reporting",
}
VALID_STATUSES = {"active", "waiting", "blocked", "done", "cancelled"}
LEGACY_PHASE_ALIASES = {
    "plan": "planning",
    "review": "verification",
    "test": "verification",
    "testing": "verification",
    "qa": "verification",
    "uat": "verification",
    "report": "reporting",
    "complete": "reporting",
    "completed": "reporting",
    "done": "reporting",
}
DEFAULT_DB = Path("~/.local/share/agent-work-items/work-items.sqlite3").expanduser()
DECISION_CORE_FIELDS = {"id", "status", "summary", "superseded_by"}


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
    return f"{source}~{external_id}"


def casefold_key(value: str) -> str:
    # Canonical IDs are ASCII-only. casefold() therefore models the case aliases
    # relevant to common case-insensitive macOS/Windows filesystems.
    return value.casefold()


def ensure_beneath(root: Path, target: Path) -> None:
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError:
        die(f"resolved Work Item path escapes root: {target}")


def yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def normalize_phase(value: Any) -> tuple[str, str | None]:
    raw = str(value or "").strip()
    lowered = raw.lower()
    if lowered in VALID_PHASES:
        return lowered, raw if raw and raw != lowered else None
    if lowered in LEGACY_PHASE_ALIASES:
        return LEGACY_PHASE_ALIASES[lowered], raw
    # Legacy phase was intentionally free-form. Unknown values must not leak into
    # the new enum contract; route the imported item through reconciliation instead.
    return "investigation", raw or None


def bullets(values: list[str], empty: str = "- None") -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return "\n".join(f"- {value}" for value in cleaned) if cleaned else empty


def active_records(
    document: dict[str, Any],
    collection: str,
    status: str,
    *,
    legacy_default_status: str | None = None,
) -> list[dict[str, Any]]:
    values = document.get(collection, [])
    if not isinstance(values, list):
        return []
    result: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        if item.get("status", legacy_default_status) == status:
            result.append(item)
    return result


def _next_action_line(item: dict[str, Any]) -> str | None:
    action = str(item.get("action", "")).strip()
    if not action:
        return None
    targets: list[str] = []
    repo = str(item.get("repo") or "").strip()
    owner = str(item.get("owner") or "").strip()
    if repo:
        targets.append(f"repo={repo}")
    if owner:
        targets.append(f"owner={owner}")
    suffix = f" ({', '.join(targets)})" if targets else ""
    return f"{action}{suffix}"


def _repo_state_lines(document: dict[str, Any]) -> tuple[list[str], list[str]]:
    repos = document.get("repos", {})
    state_lines: list[str] = []
    verification_lines: list[str] = []
    if not isinstance(repos, dict):
        return state_lines, verification_lines
    for name, value in sorted(repos.items()):
        if not isinstance(value, dict):
            continue
        repo_status = str(value.get("status") or "unknown")
        repo_summary = str(value.get("summary") or "").strip()
        state_lines.append(
            f"{name}: {repo_status}{f' — {repo_summary}' if repo_summary else ''}"
        )
        verification = value.get("verification", [])
        if isinstance(verification, list):
            for evidence in verification:
                text = str(evidence).strip()
                if text:
                    verification_lines.append(f"{name}: {text}")
    return state_lines, verification_lines


def _handoff_lines(document: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in active_records(document, "handoffs", "pending"):
        source = str(item.get("from") or "").strip()
        target = str(item.get("to") or "").strip()
        summary = str(item.get("summary") or "").strip()
        endpoints = " -> ".join(part for part in (source, target) if part)
        prefix = f"{endpoints}: " if endpoints else ""
        text = f"{prefix}{summary}".strip()
        if text:
            result.append(text)
    return result


def _decision_projection(
    document: dict[str, Any],
) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    reconciliation: list[str] = []
    for item in active_records(
        document, "decisions", "active", legacy_default_status="active"
    ):
        decision_id = str(item.get("id") or "<unknown>").strip()
        summary = str(item.get("summary") or "").strip()
        if summary:
            lines.append(summary)
        extension_fields = sorted(set(item) - DECISION_CORE_FIELDS)
        if extension_fields:
            reconciliation.append(
                f"Active decision {decision_id} has legacy extension/provenance fields "
                f"({', '.join(extension_fields)}). Their exact values remain in the protected "
                "legacy archive and MUST be reconciled before relying on this decision for "
                "implementation or report generation."
            )
    return lines, reconciliation


def render_work_item(
    document: dict[str, Any],
    revision: int,
    fallback_status: str,
    *,
    directory_key: str,
) -> str:
    item_id = str(document.get("id", "")).strip()
    title = str(document.get("title", "")).strip()
    status = str(document.get("status") or fallback_status or "active").strip()
    if status not in VALID_STATUSES:
        die(
            f"legacy Work Item {item_id!r} has invalid status for filesystem protocol: "
            f"{status!r}"
        )
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        die(f"legacy Work Item {item_id!r} has invalid revision: {revision!r}")

    phase, legacy_phase = normalize_phase(document.get("phase"))
    summary = str(document.get("summary") or "").strip()
    requirements = document.get("current_requirements", [])
    if not isinstance(requirements, list):
        requirements = []

    decisions, decision_reconciliation = _decision_projection(document)
    questions = [
        str(item.get("question", "")).strip()
        for item in active_records(
            document, "questions", "open", legacy_default_status="open"
        )
    ]
    blockers = [
        str(item.get("summary", "")).strip()
        for item in active_records(document, "blockers", "open")
    ]
    handoffs = _handoff_lines(document)

    next_actions: list[str] = []
    raw_actions = document.get("next_actions", [])
    if isinstance(raw_actions, list):
        for item in raw_actions:
            if isinstance(item, dict):
                line = _next_action_line(item)
                if line:
                    next_actions.append(line)

    repo_lines, repo_verification_lines = _repo_state_lines(document)
    archive_rel = (
        f".qiqi/migration-backups/v0024/legacy-work-items/{directory_key}.json"
    )
    reconciliation_items = [
        "Legacy Work Items did not model the new Acceptance Criteria section separately; "
        "reconcile effective acceptance criteria before substantive continuation.",
        *decision_reconciliation,
    ]
    if legacy_phase is not None:
        reconciliation_items.append(
            f"Legacy phase {legacy_phase!r} was normalized to {phase!r}; confirm the "
            "current phase before substantive continuation."
        )

    legacy_phase_line = (
        f"legacy_phase: {yaml_scalar(legacy_phase)}\n"
        if legacy_phase is not None
        else ""
    )

    return f"""---
id: {yaml_scalar(item_id)}
revision: {revision}
status: {status}
phase: {phase}
{legacy_phase_line}legacy_imported: true
legacy_reconciliation_required: true
---

# Objective

{title or summary or 'Imported legacy Work Item'}

# Current Requirements

{bullets([str(value) for value in requirements])}

# Acceptance Criteria

- Pending legacy-import reconciliation.

# Scope

## Repository State

{bullets(repo_lines)}

## Repository Verification

{bullets(repo_verification_lines)}

# Decisions

{bullets(decisions)}

# Open Questions

{bullets(questions)}

# Blockers

{bullets(blockers)}

# Pending Handoffs

{bullets(handoffs)}

# Current State

{summary or 'Imported from the legacy Work Item store.'}

# Next Actions

{bullets(next_actions)}

# Import Reconciliation

Protected legacy archive: `{archive_rel}`.

{bullets(reconciliation_items)}
"""


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def validate_artifact_schema(conn: sqlite3.Connection) -> bool:
    present = {table for table in ARTIFACT_TABLES if table_exists(conn, table)}
    if not present:
        return False
    missing = ARTIFACT_TABLES - present
    if missing:
        die(
            "legacy artifact schema is incomplete; present="
            + ", ".join(sorted(present))
            + "; missing="
            + ", ".join(sorted(missing))
        )
    return True


def read_artifacts(
    conn: sqlite3.Connection, item_id: str, *, artifact_schema_present: bool
) -> list[dict[str, Any]]:
    if not artifact_schema_present:
        return []
    artifacts: list[dict[str, Any]] = []
    rows = conn.execute(
        "SELECT * FROM work_item_artifacts WHERE work_item_id=? "
        "ORDER BY updated_at DESC, artifact_id ASC",
        (item_id,),
    ).fetchall()
    for row in rows:
        artifact = dict(row)
        sections: list[dict[str, Any]] = []
        section_rows = conn.execute(
            "SELECT * FROM work_item_artifact_sections "
            "WHERE work_item_id=? AND artifact_id=? "
            "ORDER BY section_order ASC, section_id ASC",
            (item_id, row["artifact_id"]),
        ).fetchall()
        for section_row in section_rows:
            section = dict(section_row)
            chunk_rows = conn.execute(
                "SELECT * FROM work_item_artifact_chunks "
                "WHERE work_item_id=? AND artifact_id=? AND section_id=? "
                "ORDER BY chunk_index ASC",
                (item_id, row["artifact_id"], section_row["section_id"]),
            ).fetchall()
            chunks = [dict(chunk) for chunk in chunk_rows]
            section["chunks"] = chunks
            section["content"] = "".join(str(chunk["content"]) for chunk in chunks)
            sections.append(section)
        artifact["sections"] = sections
        artifacts.append(artifact)
    return artifacts


def render_markdown_artifact(artifact_type: str, artifact: dict[str, Any]) -> str:
    title = str(artifact.get("title") or artifact.get("artifact_id") or "Imported artifact")
    summary = str(artifact.get("summary") or "").strip()
    parts: list[str] = []
    if artifact_type in REVISIONED_ARTIFACT_TYPES:
        based_on = artifact.get("based_on_work_item_revision")
        if not isinstance(based_on, int) or isinstance(based_on, bool) or based_on < 1:
            die(
                f"legacy {artifact_type} artifact has invalid "
                "based_on_work_item_revision: "
                f"{artifact.get('artifact_id')!r}"
            )
        parts.extend(["---", f"based_on_work_item_revision: {based_on}", "---", ""])
    parts.append(f"# {title}")
    if summary:
        parts.extend(["", summary])
    for section in artifact.get("sections", []):
        section_title = str(
            section.get("title") or section.get("section_id") or "Section"
        )
        content = str(section.get("content") or "")
        parts.extend(["", f"## {section_title}", "", content.rstrip()])
    return "\n".join(parts).rstrip() + "\n"


def textile_heading(title: str) -> str:
    stripped = title.strip()
    if TEXTILE_HEADING_RE.match(stripped):
        return stripped
    return f"h2. {stripped}"


def render_textile_report(artifact: dict[str, Any]) -> str:
    # The canonical report file is the external Redmine deliverable. Keep artifact
    # metadata in the JSON archive rather than injecting an extra h1/title/summary.
    parts: list[str] = []
    for section in artifact.get("sections", []):
        section_title = str(
            section.get("title") or section.get("section_id") or "Section"
        )
        content = str(section.get("content") or "")
        parts.extend([textile_heading(section_title), "", content.rstrip(), ""])
    return "\n".join(parts).rstrip() + "\n"


def render_artifact(artifact_type: str, artifact: dict[str, Any]) -> str:
    if artifact_type == "report":
        return render_textile_report(artifact)
    return render_markdown_artifact(artifact_type, artifact)


def reserve_output(path: Path, reserved: set[str]) -> None:
    folded = casefold_key(str(path.resolve()))
    if folded in reserved:
        die(f"multiple legacy records map to filesystem-equivalent export paths: {path}")
    if path.exists():
        die(f"refusing to overwrite existing filesystem Work Item file: {path}")
    reserved.add(folded)


def _assert_casefold_name_available(parent: Path, name: str, *, label: str) -> None:
    if not parent.is_dir():
        return
    folded = casefold_key(name)
    for entry in parent.iterdir():
        if casefold_key(entry.name) == folded and entry.name != name:
            die(
                f"{label} {name!r} aliases existing filesystem entry "
                f"{entry.name!r} under case-insensitive name matching"
            )


def build_export_plan(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    db: Path,
    work_items_root: Path,
    backup_root: Path,
    *,
    artifact_schema_present: bool,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    reserved: set[str] = set()
    reserved_keys: set[str] = set()

    for row in rows:
        item_id = str(row["id"])
        key = safe_key(item_id)
        folded_key = casefold_key(key)
        if folded_key in reserved_keys:
            die(
                f"multiple canonical Work Item ids map to case-insensitive-equivalent "
                f"directory keys: {key!r}"
            )
        reserved_keys.add(folded_key)

        _assert_casefold_name_available(
            work_items_root, key, label="Work Item directory key"
        )
        _assert_casefold_name_available(
            backup_root, f"{key}.json", label="legacy archive name"
        )

        target = work_items_root / key
        ensure_beneath(work_items_root, target)
        if target.exists():
            if not target.is_dir():
                die(f"target dossier path is not a directory: {target}")
            if any(target.iterdir()):
                die(f"target dossier already exists and is non-empty: {target}")

        try:
            document = json.loads(row["document_json"])
        except json.JSONDecodeError as exc:
            die(f"legacy Work Item document is invalid JSON for {item_id!r}: {exc}")
        if not isinstance(document, dict):
            die(f"legacy Work Item document must be a JSON object for {item_id!r}")
        if str(document.get("id", "")).strip() != item_id:
            die(f"legacy Work Item document id does not match row id: {item_id!r}")

        revision = int(row["revision"])
        artifacts = read_artifacts(
            conn, item_id, artifact_schema_present=artifact_schema_present
        )
        files: list[tuple[Path, str]] = [
            (
                target / "WORK_ITEM.md",
                render_work_item(
                    document,
                    revision,
                    str(row["status"]),
                    directory_key=key,
                ),
            )
        ]

        # read_artifacts uses the legacy public ordering: newest update first,
        # artifact_id ascending as deterministic tie-break.
        latest_by_type: dict[str, dict[str, Any]] = {}
        for artifact in artifacts:
            artifact_type = str(artifact.get("type") or "")
            if artifact_type in ARTIFACT_FILE_BY_TYPE:
                latest_by_type.setdefault(artifact_type, artifact)
        for artifact_type, artifact in latest_by_type.items():
            files.append(
                (
                    target / ARTIFACT_FILE_BY_TYPE[artifact_type],
                    render_artifact(artifact_type, artifact),
                )
            )

        archive = {
            "source_db": str(db),
            "work_item": document,
            "revision": revision,
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "artifacts": artifacts,
        }
        archive_path = backup_root / f"{key}.json"

        for path, _ in files:
            reserve_output(path, reserved)
        reserve_output(archive_path, reserved)

        plan.append(
            {
                "item_id": item_id,
                "key": key,
                "files": files,
                "archive_path": archive_path,
                "archive_content": json.dumps(
                    archive, ensure_ascii=False, indent=2, sort_keys=True
                )
                + "\n",
            }
        )

    return plan


def write_text(
    path: Path, content: str, dry_run: bool, *, mode: int | None = None
) -> None:
    print(f"  + {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if not (workspace / "repos.yaml").is_file():
        die(f"workspace is missing repos.yaml: {workspace}")
    db = Path(args.db).expanduser().resolve()
    if not db.is_file():
        die(
            f"legacy Work Item DB not found: {db}; "
            "if the old installer used --db-path, pass that exact path with --db"
        )

    work_items_root = (workspace / "work-items").resolve()
    backup_root = (
        workspace
        / ".qiqi"
        / "migration-backups"
        / "v0024"
        / "legacy-work-items"
    )

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        # Keep rows/artifacts/sections/chunks in one read snapshot while the legacy
        # service may still exist during cutover.
        conn.execute("BEGIN")
        if not table_exists(conn, "work_items"):
            die(f"legacy DB has no work_items table: {db}")
        artifact_schema_present = validate_artifact_schema(conn)
        rows = conn.execute("SELECT * FROM work_items ORDER BY id ASC").fetchall()
        print(f"preflighting {len(rows)} legacy Work Item(s) from {db}")
        plan = build_export_plan(
            conn,
            rows,
            db,
            work_items_root,
            backup_root,
            artifact_schema_present=artifact_schema_present,
        )
        conn.execute("ROLLBACK")
    finally:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        conn.close()

    # No filesystem mutation occurs until every legacy record and output has passed
    # preflight, including case-insensitive name aliases.
    if not args.dry_run:
        work_items_root.mkdir(parents=True, exist_ok=True)
        backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup_root.chmod(0o700)

    for entry in plan:
        print(f"{entry['item_id']} -> work-items/{entry['key']}/")
        for path, content in entry["files"]:
            write_text(path, content, args.dry_run)
        write_text(
            entry["archive_path"], entry["archive_content"], args.dry_run, mode=0o600
        )

    print("legacy Work Item export complete; source SQLite DB was not modified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
