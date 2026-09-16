#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path


MAPPING = (
    ("WORK_ITEM.md", "00_WORK_ITEM.md"),
    ("intake.md", "10_intake.md"),
    ("investigation.md", "20_investigation.md"),
    ("plan.md", "30_plan.md"),
    ("review.md", "40_review.md"),
    ("report.textile", "90_report.textile"),
)


def die(message: str) -> "None":
    raise SystemExit(f"ERROR: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename legacy Work Item lifecycle files to the v27 ordered filename contract."
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Workspace root. Defaults to the parent of this script's scripts/ directory.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def resolve_workspace(value: str | None) -> Path:
    if value is None:
        return Path(__file__).resolve().parents[1]
    return Path(value).expanduser().resolve()


def dossier_directories(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        die(f"work-items root must be a real directory: {root}")

    dossiers: list[Path] = []
    for entry in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
        if entry.name.startswith("."):
            continue
        if entry.is_symlink():
            die(f"Work Item dossier must not be a symlink: {entry}")
        if not entry.is_dir():
            die(f"unexpected non-directory entry under work-items: {entry}")
        dossiers.append(entry)
    return dossiers


def preflight(workspace: Path) -> list[tuple[Path, Path]]:
    if not (workspace / "repos.yaml").is_file() or not (workspace / "identity.md").is_file():
        die(f"not a QiQi workspace root: {workspace}")

    work_items = workspace / "work-items"
    moves: list[tuple[Path, Path]] = []

    for dossier in dossier_directories(work_items):
        old_primary = dossier / "WORK_ITEM.md"
        new_primary = dossier / "00_WORK_ITEM.md"

        if old_primary.exists() or old_primary.is_symlink():
            if not regular_file(old_primary):
                die(f"legacy canonical Work Item is not a regular file: {old_primary}")
            if new_primary.exists() or new_primary.is_symlink():
                die(
                    "old/new canonical Work Item collision; reconcile manually before migration: "
                    f"{old_primary} <-> {new_primary}"
                )
        elif not regular_file(new_primary):
            if new_primary.exists() or new_primary.is_symlink():
                die(f"canonical Work Item is not a regular file: {new_primary}")
            die(
                "dossier has neither legacy nor v27 canonical Work Item file: "
                f"{dossier}"
            )

        for old_name, new_name in MAPPING:
            old = dossier / old_name
            new = dossier / new_name
            old_exists = old.exists() or old.is_symlink()
            new_exists = new.exists() or new.is_symlink()

            if old_exists:
                if not regular_file(old):
                    die(f"legacy lifecycle path is not a regular file: {old}")
                if new_exists:
                    die(
                        "old/new lifecycle filename collision; no files were changed: "
                        f"{old} <-> {new}"
                    )
                moves.append((old, new))
            elif new_exists and not regular_file(new):
                die(f"v27 lifecycle path is not a regular file: {new}")

    return moves


def apply_moves(moves: list[tuple[Path, Path]], *, dry_run: bool) -> None:
    if not moves:
        print("Work Item filename migration: already current; no renames required")
        return

    for old, new in moves:
        print(f"{old} -> {new.name}")
    if dry_run:
        print("dry-run complete; no files were changed")
        return

    completed: list[tuple[Path, Path]] = []
    try:
        for old, new in moves:
            os.replace(old, new)
            completed.append((old, new))
    except Exception as exc:
        rollback_errors: list[str] = []
        for old, new in reversed(completed):
            try:
                if new.exists() and not old.exists():
                    os.replace(new, old)
            except Exception as rollback_exc:  # pragma: no cover - catastrophic filesystem failure
                rollback_errors.append(f"{new} -> {old}: {rollback_exc}")
        detail = f"rename failed: {exc}"
        if rollback_errors:
            detail += "; rollback errors: " + "; ".join(rollback_errors)
        die(detail)

    print(f"Work Item filename migration complete: {len(completed)} file(s) renamed")


def main() -> int:
    args = parse_args()
    workspace = resolve_workspace(args.workspace)
    moves = preflight(workspace)
    apply_moves(moves, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
