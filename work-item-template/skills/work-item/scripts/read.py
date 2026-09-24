#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HARD_OUTPUT_BYTES = 8192
MAX_RANGE_LINES = 120
MAX_SECTIONS = 6
PRIMARY = "00_WORK_ITEM.md"
ALLOWED_FILES = {
    "00_WORK_ITEM.md",
    "10_intake.md",
    "20_investigation.md",
    "30_plan.md",
    "40_review.md",
}
BOOTSTRAP_SECTIONS = (
    "Objective",
    "Current Requirements",
    "Acceptance Criteria",
    "Open Questions",
    "Blockers",
    "Current State",
)
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
FRONT_VALUE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*?)\s*$")


class ReadError(Exception):
    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def error(code: str, message: str, **details: object) -> None:
    payload = {"ok": False, "error": code, "message": message, **details}
    sys.stderr.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    raise SystemExit(2)


def read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ReadError("invalid_file", f"expected regular file: {path.name}", file=path.name)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ReadError("invalid_utf8", f"file is not valid UTF-8: {path.name}", file=path.name) from exc


def parse_simple_front_matter(text: str) -> tuple[dict[str, object], int]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, 0
    values: dict[str, object] = {}
    for raw in match.group(1).splitlines():
        found = FRONT_VALUE_RE.match(raw)
        if not found:
            continue
        key, value = found.groups()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key in {"revision", "based_on_work_item_revision"}:
            try:
                values[key] = int(value)
            except ValueError as exc:
                raise ReadError("invalid_revision", f"front-matter {key} must be an integer") from exc
        else:
            values[key] = value
    return values, match.end()


def parse_front_matter(text: str) -> tuple[dict[str, object], int]:
    values, end = parse_simple_front_matter(text)
    if not values:
        raise ReadError("missing_front_matter", f"{PRIMARY} must start with YAML front matter")
    for key in ("id", "revision", "status", "phase"):
        if key not in values:
            raise ReadError("missing_metadata", f"missing required front-matter field: {key}", field=key)
    if not isinstance(values["revision"], int) or values["revision"] < 1:
        raise ReadError("invalid_revision", "front-matter revision must be >= 1")
    return values, end


def headings(text: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    offset = 0
    in_fence = False
    fence_char = ""
    fence_len = 0
    for number, line in enumerate(text.splitlines(keepends=True), start=1):
        stripped = line.lstrip()
        fence = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                in_fence = False
            offset += len(line)
            continue
        if not in_fence:
            match = HEADING_RE.match(line.rstrip("\r\n"))
            if match:
                out.append(
                    {
                        "level": len(match.group(1)),
                        "heading": match.group(2).strip(),
                        "line": number,
                        "offset": offset,
                    }
                )
        offset += len(line)
    return out


def section_slice(text: str, wanted: str) -> tuple[str, dict[str, object]]:
    all_headings = headings(text)
    matches = [item for item in all_headings if item["heading"] == wanted]
    if not matches:
        raise ReadError("section_not_found", f"section not found: {wanted}", section=wanted)
    if len(matches) > 1:
        raise ReadError(
            "ambiguous_section",
            f"section heading is not unique: {wanted}",
            section=wanted,
            matches=len(matches),
        )
    current = matches[0]
    start = int(current["offset"])
    level = int(current["level"])
    end = len(text)
    for item in all_headings:
        if int(item["offset"]) <= start:
            continue
        if int(item["level"]) <= level:
            end = int(item["offset"])
            break
    content = text[start:end].rstrip() + "\n"
    info = {
        "heading": wanted,
        "level": level,
        "start_line": int(current["line"]),
        "end_line": int(current["line"]) + len(content.splitlines()) - 1,
    }
    return content, info


def top_level_headings(text: str) -> list[str]:
    hs = headings(text)
    if not hs:
        return []
    minimum = min(int(item["level"]) for item in hs)
    return [str(item["heading"]) for item in hs if int(item["level"]) == minimum]


def parse_range(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"([1-9][0-9]*):([1-9][0-9]*)", value)
    if not match:
        raise argparse.ArgumentTypeError("range must be START:END with 1-based inclusive line numbers")
    start, end = map(int, match.groups())
    if end < start:
        raise argparse.ArgumentTypeError("range END must be >= START")
    if end - start + 1 > MAX_RANGE_LINES:
        raise argparse.ArgumentTypeError(f"range may contain at most {MAX_RANGE_LINES} lines")
    return start, end


def safe_dossier(raw: str) -> Path:
    dossier = Path(raw).expanduser()
    if dossier.is_symlink():
        raise ReadError("invalid_dossier", f"dossier must not be a symlink: {dossier}")
    try:
        resolved = dossier.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ReadError("missing_dossier", f"dossier does not exist: {dossier}") from exc
    if not resolved.is_dir():
        raise ReadError("invalid_dossier", f"dossier must be a real directory: {dossier}")
    return resolved


def target_path(dossier: Path, filename: str) -> Path:
    if filename not in ALLOWED_FILES:
        raise ReadError("invalid_file", f"unsupported Work Item file: {filename}", file=filename)
    candidate = dossier / filename
    resolved = candidate.resolve(strict=False)
    if resolved.parent != dossier:
        raise ReadError("path_escape", "requested file escapes dossier", file=filename)
    return candidate


def compact_emit(payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    size = len(encoded.encode("utf-8"))
    if size > HARD_OUTPUT_BYTES:
        raise ReadError(
            "output_budget_exceeded",
            "selected Work Item surface exceeds hard output budget; request fewer sections or a smaller line range",
            selected_bytes=size,
            max_bytes=HARD_OUTPUT_BYTES,
        )
    sys.stdout.write(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bounded semantic reader for filesystem Work Item lifecycle documents."
    )
    parser.add_argument("--dossier", required=True)
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--profile", choices=["bootstrap"])
    parser.add_argument("--file", choices=sorted(ALLOWED_FILES))
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--headings", action="store_true")
    selector.add_argument("--section", action="append", default=[])
    selector.add_argument("--lines", type=parse_range)
    args = parser.parse_args()

    if bool(args.profile) == bool(args.file):
        parser.error("provide exactly one of --profile or --file")
    if args.profile and (args.headings or args.section or args.lines):
        parser.error("--profile cannot be combined with file selectors")
    if args.file and not (args.headings or args.section or args.lines):
        parser.error("--file requires exactly one of --headings, --section, or --lines")
    if len(args.section) > MAX_SECTIONS:
        parser.error(f"at most {MAX_SECTIONS} --section selectors are allowed")
    if args.expected_revision is not None and args.expected_revision < 1:
        parser.error("--expected-revision must be >= 1")

    try:
        dossier = safe_dossier(args.dossier)
        primary_text = read_text(target_path(dossier, PRIMARY))
        meta, _ = parse_front_matter(primary_text)
        revision = int(meta["revision"])
        if args.expected_revision is not None and revision != args.expected_revision:
            raise ReadError(
                "revision_mismatch",
                "Work Item revision changed; reread bounded current state before using lifecycle evidence",
                expected_revision=args.expected_revision,
                actual_revision=revision,
            )

        if args.profile == "bootstrap":
            selected: list[dict[str, object]] = []
            chunks: list[str] = []
            for name in BOOTSTRAP_SECTIONS:
                content, info = section_slice(primary_text, name)
                selected.append(info)
                chunks.append(content)
            selected_names = list(BOOTSTRAP_SECTIONS)
            omitted = [name for name in top_level_headings(primary_text) if name not in selected_names]
            payload = {
                "ok": True,
                "revision": revision,
                "metadata": {key: meta[key] for key in ("id", "revision", "status", "phase")},
                "coverage": {
                    "file": PRIMARY,
                    "mode": "bootstrap",
                    "sections": selected,
                    "omitted_top_level_sections": omitted,
                    "complete_file": False,
                },
                "content": "\n".join(chunks).rstrip() + "\n",
            }
            compact_emit(payload)
            return 0

        filename = str(args.file)
        text = read_text(target_path(dossier, filename))
        file_metadata, _ = parse_simple_front_matter(text)
        if args.headings:
            payload = {
                "ok": True,
                "revision": revision,
                "file_metadata": file_metadata,
                "coverage": {
                    "file": filename,
                    "mode": "headings",
                    "complete_file": False,
                },
                "headings": [
                    {key: item[key] for key in ("level", "heading", "line")}
                    for item in headings(text)
                ],
            }
            compact_emit(payload)
            return 0

        if args.section:
            selected = []
            chunks = []
            for name in args.section:
                content, info = section_slice(text, name)
                selected.append(info)
                chunks.append(content)
            selected_names = set(args.section)
            payload = {
                "ok": True,
                "revision": revision,
                "file_metadata": file_metadata,
                "coverage": {
                    "file": filename,
                    "mode": "sections",
                    "sections": selected,
                    "omitted_top_level_sections": [
                        name for name in top_level_headings(text) if name not in selected_names
                    ],
                    "complete_file": False,
                },
                "content": "\n".join(chunks).rstrip() + "\n",
            }
            compact_emit(payload)
            return 0

        assert args.lines is not None
        start, end = args.lines
        all_lines = text.splitlines(keepends=True)
        if start > len(all_lines):
            raise ReadError(
                "range_out_of_bounds",
                "line range starts after end of file",
                start=start,
                total_lines=len(all_lines),
            )
        end = min(end, len(all_lines))
        content = "".join(all_lines[start - 1 : end])
        payload = {
            "ok": True,
            "revision": revision,
            "file_metadata": file_metadata,
            "coverage": {
                "file": filename,
                "mode": "lines",
                "start_line": start,
                "end_line": end,
                "total_lines": len(all_lines),
                "complete_file": start == 1 and end == len(all_lines),
            },
            "content": content,
        }
        compact_emit(payload)
        return 0
    except ReadError as exc:
        error(exc.code, exc.message, **exc.details)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
