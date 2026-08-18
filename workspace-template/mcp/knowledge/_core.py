from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml
from filelock import FileLock

INDEX_NAME = "INDEX.md"
LOCK_NAME = ".knowledge.lock"
FORMAT_VERSION = 1
SCOPE_DIRS = {
    "global": "global",
    "system": "systems",
    "repo": "repos",
    "domain": "domains",
}
SCOPE_SEGMENT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$|^[a-z0-9]$")
CANONICAL_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$|^[a-z0-9]$")
WORD_RE = re.compile(r"\w+", re.UNICODE)


class KnowledgeError(RuntimeError):
    pass


def _reject_unknown_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise KnowledgeError(f"{label} contains unsupported field(s): {', '.join(unknown)}")


def _require_nonempty_string(value: Any, label: str, *, max_length: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeError(f"{label} must be a non-empty string")
    value = value.strip()
    if len(value) > max_length:
        raise KnowledgeError(f"{label} is too long")
    return value


def _require_string_list(
    value: Any,
    label: str,
    *,
    min_items: int = 1,
    max_items: int = 50,
) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise KnowledgeError(f"{label} must be a list of strings")
    items = [item.strip() for item in value if item.strip()]
    if len(items) < min_items:
        raise KnowledgeError(f"{label} must contain at least {min_items} item(s)")
    if len(items) > max_items:
        raise KnowledgeError(f"{label} must contain at most {max_items} items")
    return items


def _validate_scope(scope: Any) -> dict[str, str]:
    if not isinstance(scope, dict):
        raise KnowledgeError("scope must be an object")
    _reject_unknown_keys(scope, {"kind", "id"}, "scope")
    kind = _require_nonempty_string(scope.get("kind"), "scope.kind", max_length=32)
    if kind not in SCOPE_DIRS:
        raise KnowledgeError(
            "scope.kind must be one of: " + ", ".join(sorted(SCOPE_DIRS))
        )
    scope_id = _require_nonempty_string(scope.get("id"), "scope.id", max_length=200)
    segments = scope_id.split(".")
    if any(not SCOPE_SEGMENT_RE.fullmatch(segment) for segment in segments):
        raise KnowledgeError(
            "scope.id must be dot-separated lowercase ASCII slug segments"
        )
    return {"kind": kind, "id": scope_id}


def _validate_canonical_name(value: Any) -> str:
    name = _require_nonempty_string(value, "canonical_name", max_length=120)
    if not CANONICAL_NAME_RE.fullmatch(name):
        raise KnowledgeError(
            "canonical_name must be a lowercase ASCII kebab-case slug"
        )
    return name


def _validate_routing(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise KnowledgeError("routing must be an object")
    _reject_unknown_keys(
        value,
        {"summary", "when_to_read", "keywords", "aliases"},
        "routing",
    )
    summary = _require_nonempty_string(
        value.get("summary"), "routing.summary", max_length=1200
    )
    when_to_read = _require_string_list(
        value.get("when_to_read"),
        "routing.when_to_read",
        min_items=1,
        max_items=30,
    )
    keywords = _require_string_list(
        value.get("keywords"),
        "routing.keywords",
        min_items=1,
        max_items=50,
    )
    aliases_raw = value.get("aliases", [])
    aliases = _require_string_list(
        aliases_raw,
        "routing.aliases",
        min_items=0,
        max_items=50,
    )
    return {
        "summary": summary,
        "when_to_read": when_to_read,
        "keywords": keywords,
        "aliases": aliases,
    }


def _validate_sources(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise KnowledgeError("sources must be a non-empty list")
    if len(value) > 50:
        raise KnowledgeError("sources must contain at most 50 entries")
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise KnowledgeError(f"sources[{index}] must be an object")
        _reject_unknown_keys(
            item,
            {"type", "repo", "path", "ref", "note"},
            f"sources[{index}]",
        )
        source_type = _require_nonempty_string(
            item.get("type"), f"sources[{index}].type", max_length=32
        )
        if source_type not in {"repo", "document", "decision", "manual"}:
            raise KnowledgeError(
                f"sources[{index}].type must be repo, document, decision, or manual"
            )
        normalized: dict[str, str] = {"type": source_type}
        for key in ("repo", "path", "ref", "note"):
            raw = item.get(key)
            if raw is None:
                continue
            normalized[key] = _require_nonempty_string(
                raw, f"sources[{index}].{key}", max_length=2000
            )
        if source_type == "repo":
            if "repo" not in normalized or "path" not in normalized:
                raise KnowledgeError(
                    f"sources[{index}] repo source requires repo and path"
                )
        elif source_type in {"document", "decision"}:
            if "ref" not in normalized and "path" not in normalized:
                raise KnowledgeError(
                    f"sources[{index}] {source_type} source requires ref or path"
                )
        elif source_type == "manual" and "note" not in normalized:
            raise KnowledgeError(
                f"sources[{index}] manual source requires note"
            )
        result.append(normalized)
    return result


def knowledge_id(scope: dict[str, str], canonical_name: str) -> str:
    return f"{scope['kind']}:{scope['id']}:{canonical_name}"


def parse_knowledge_id(value: str) -> tuple[dict[str, str], str]:
    raw = _require_nonempty_string(value, "id", max_length=400)
    parts = raw.split(":")
    if len(parts) != 3:
        raise KnowledgeError("id must have format <scope-kind>:<scope-id>:<canonical-name>")
    scope = _validate_scope({"kind": parts[0], "id": parts[1]})
    canonical_name = _validate_canonical_name(parts[2])
    if knowledge_id(scope, canonical_name) != raw:
        raise KnowledgeError("id is not canonical")
    return scope, canonical_name


def relative_path_for(scope: dict[str, str], canonical_name: str) -> Path:
    directory = Path(SCOPE_DIRS[scope["kind"]], *scope["id"].split("."))
    return directory / f"{canonical_name}.md"


def _normalize_entry_payload(value: Any, *, require_id: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise KnowledgeError("knowledge entry must be an object")
    _reject_unknown_keys(
        value,
        {
            "id",
            "expected_revision",
            "canonical_name",
            "title",
            "scope",
            "routing",
            "content",
            "sources",
        },
        "knowledge entry",
    )
    scope = _validate_scope(value.get("scope"))
    canonical_name = _validate_canonical_name(value.get("canonical_name"))
    title = _require_nonempty_string(value.get("title"), "title", max_length=500)
    routing = _validate_routing(value.get("routing"))
    content = value.get("content")
    if not isinstance(content, str):
        raise KnowledgeError("content must be a string")
    if len(content) > 200_000:
        raise KnowledgeError("content is too large")
    sources = _validate_sources(value.get("sources"))
    entry_id = value.get("id")
    if require_id:
        entry_id = _require_nonempty_string(entry_id, "id", max_length=400)
        expected_scope, expected_name = parse_knowledge_id(entry_id)
        if expected_scope != scope or expected_name != canonical_name:
            raise KnowledgeError("id must match scope and canonical_name")
    elif entry_id is not None:
        raise KnowledgeError("create entry must omit id")
    return {
        "id": entry_id,
        "canonical_name": canonical_name,
        "title": title,
        "scope": scope,
        "routing": routing,
        "content": content.rstrip(),
        "sources": sources,
    }


def _frontmatter(text: str, label: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise KnowledgeError(f"{label}: missing YAML front matter")
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise KnowledgeError(f"{label}: unterminated YAML front matter")
    raw_meta = "".join(lines[1:end])
    try:
        metadata = yaml.safe_load(raw_meta) or {}
    except yaml.YAMLError as exc:
        raise KnowledgeError(f"{label}: invalid YAML front matter: {exc}") from exc
    if not isinstance(metadata, dict):
        raise KnowledgeError(f"{label}: front matter must be an object")
    body = "".join(lines[end + 1 :]).lstrip("\n")
    return metadata, body


def _metadata_for(payload: dict[str, Any], entry_id: str) -> dict[str, Any]:
    routing = dict(payload["routing"])
    if not routing["aliases"]:
        routing.pop("aliases", None)
    return {
        "version": FORMAT_VERSION,
        "id": entry_id,
        "canonical_name": payload["canonical_name"],
        "title": payload["title"],
        "scope": payload["scope"],
        "routing": routing,
        "sources": payload["sources"],
    }


def render_detail(payload: dict[str, Any], entry_id: str) -> str:
    metadata = _metadata_for(payload, entry_id)
    dumped = yaml.safe_dump(
        metadata,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    ).rstrip()
    content = payload["content"]
    body = f"# {payload['title']}"
    if content:
        body += f"\n\n{content}"
    return f"---\n{dumped}\n---\n\n{body}\n"


def parse_detail(text: str, label: str = "knowledge document") -> dict[str, Any]:
    metadata, body = _frontmatter(text, label)
    _reject_unknown_keys(
        metadata,
        {"version", "id", "canonical_name", "title", "scope", "routing", "sources"},
        f"{label} front matter",
    )
    if metadata.get("version") != FORMAT_VERSION:
        raise KnowledgeError(f"{label}: version must be {FORMAT_VERSION}")
    raw_id = _require_nonempty_string(metadata.get("id"), f"{label}.id", max_length=400)
    scope, canonical_name = parse_knowledge_id(raw_id)
    if metadata.get("canonical_name") != canonical_name:
        raise KnowledgeError(f"{label}: canonical_name does not match id")
    if _validate_scope(metadata.get("scope")) != scope:
        raise KnowledgeError(f"{label}: scope does not match id")
    title = _require_nonempty_string(metadata.get("title"), f"{label}.title", max_length=500)
    routing = _validate_routing(metadata.get("routing"))
    sources = _validate_sources(metadata.get("sources"))
    body_lines = body.splitlines()
    expected_h1 = f"# {title}"
    if not body_lines or body_lines[0].rstrip() != expected_h1:
        raise KnowledgeError(f"{label}: body must start with canonical H1 {expected_h1!r}")
    content = "\n".join(body_lines[1:]).lstrip("\n").rstrip()
    return {
        "id": raw_id,
        "canonical_name": canonical_name,
        "title": title,
        "scope": scope,
        "routing": routing,
        "sources": sources,
        "content": content,
    }


def _index_entry(detail: dict[str, Any], relative_path: Path) -> dict[str, Any]:
    routing = dict(detail["routing"])
    if not routing["aliases"]:
        routing.pop("aliases", None)
    return {
        "id": detail["id"],
        "path": relative_path.as_posix(),
        "canonical_name": detail["canonical_name"],
        "title": detail["title"],
        "scope": detail["scope"],
        "routing": routing,
    }


def _table_text(entries: list[dict[str, Any]]) -> str:
    def cell(value: str) -> str:
        return " ".join(value.split()).replace("|", "\\|")

    lines = [
        "# Knowledge Index",
        "",
        "Generated from canonical knowledge document metadata. Do not treat this file as the knowledge source of truth.",
        "",
        "| ID | Path | Scope | Summary | When to read |",
        "|---|---|---|---|---|",
    ]
    for entry in entries:
        scope = entry["scope"]
        when = "; ".join(entry["routing"]["when_to_read"])
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} |".format(
                cell(entry["id"]),
                cell(entry["path"]),
                cell(f"{scope['kind']}:{scope['id']}"),
                cell(entry["routing"]["summary"]),
                cell(when),
            )
        )
    return "\n".join(lines) + "\n"


def render_index(entries: list[dict[str, Any]]) -> str:
    ordered = sorted(entries, key=lambda item: item["id"])
    metadata = {
        "version": FORMAT_VERSION,
        "entries": ordered,
    }
    dumped = yaml.safe_dump(
        metadata,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    ).rstrip()
    return f"---\n{dumped}\n---\n\n{_table_text(ordered)}"


def parse_index(text: str) -> list[dict[str, Any]]:
    metadata, _ = _frontmatter(text, INDEX_NAME)
    _reject_unknown_keys(metadata, {"version", "entries"}, f"{INDEX_NAME} front matter")
    if metadata.get("version") != FORMAT_VERSION:
        raise KnowledgeError(f"{INDEX_NAME}: version must be {FORMAT_VERSION}")
    entries = metadata.get("entries")
    if not isinstance(entries, list):
        raise KnowledgeError(f"{INDEX_NAME}: entries must be a list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise KnowledgeError(f"{INDEX_NAME}: entries[{index}] must be an object")
        _reject_unknown_keys(
            item,
            {"id", "path", "canonical_name", "title", "scope", "routing"},
            f"{INDEX_NAME}.entries[{index}]",
        )
        entry_id = _require_nonempty_string(
            item.get("id"), f"{INDEX_NAME}.entries[{index}].id", max_length=400
        )
        scope, canonical_name = parse_knowledge_id(entry_id)
        expected_path = relative_path_for(scope, canonical_name).as_posix()
        path = _require_nonempty_string(
            item.get("path"), f"{INDEX_NAME}.entries[{index}].path", max_length=1000
        )
        if path != expected_path:
            raise KnowledgeError(
                f"{INDEX_NAME}: {entry_id} path must be {expected_path}"
            )
        if entry_id in seen:
            raise KnowledgeError(f"{INDEX_NAME}: duplicate id {entry_id}")
        seen.add(entry_id)
        title = _require_nonempty_string(
            item.get("title"), f"{INDEX_NAME}.entries[{index}].title", max_length=500
        )
        item_scope = _validate_scope(item.get("scope"))
        if item_scope != scope:
            raise KnowledgeError(f"{INDEX_NAME}: {entry_id} scope does not match id")
        item_name = _validate_canonical_name(item.get("canonical_name"))
        if item_name != canonical_name:
            raise KnowledgeError(
                f"{INDEX_NAME}: {entry_id} canonical_name does not match id"
            )
        routing = _validate_routing(item.get("routing"))
        if not routing["aliases"]:
            routing.pop("aliases", None)
        result.append(
            {
                "id": entry_id,
                "path": path,
                "canonical_name": canonical_name,
                "title": title,
                "scope": scope,
                "routing": routing,
            }
        )
    return result


def _revision(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _tokens(value: str) -> set[str]:
    return set(WORD_RE.findall(_normalized(value)))


def _match_score(query: str, candidate: str, weight: float) -> float:
    q = _normalized(query)
    c = _normalized(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return weight * 3.0
    if q in c or c in q:
        return weight * 2.0
    qt = _tokens(q)
    ct = _tokens(c)
    if not qt or not ct:
        return 0.0
    overlap = len(qt & ct)
    if not overlap:
        return 0.0
    return weight * (overlap / len(qt))


def _score_entry(
    entry: dict[str, Any],
    keywords: list[str],
    context: dict[str, str],
) -> tuple[float, list[str]]:
    fields: list[tuple[str, list[str], float]] = [
        ("id", [entry["id"], entry["canonical_name"], entry["path"]], 12.0),
        ("routing.keywords", entry["routing"]["keywords"], 10.0),
        ("routing.aliases", entry["routing"].get("aliases", []), 9.0),
        ("routing.when_to_read", entry["routing"]["when_to_read"], 7.0),
        ("routing.summary", [entry["routing"]["summary"]], 5.0),
        ("title", [entry["title"]], 3.0),
    ]
    total = 0.0
    reasons: list[tuple[float, str]] = []
    for query in keywords:
        best = 0.0
        best_reason = ""
        for field_name, values, weight in fields:
            for candidate in values:
                score = _match_score(query, candidate, weight)
                if score > best:
                    best = score
                    best_reason = f"{query!r} matched {field_name}: {candidate!r}"
        total += best
        if best_reason:
            reasons.append((best, best_reason))

    scope = entry["scope"]
    repo_hint = context.get("repo")
    if repo_hint:
        if scope["kind"] == "repo" and scope["id"] == repo_hint:
            total += 4.0
            reasons.append((4.0, f"context repo matched scope {repo_hint!r}"))
        elif scope["kind"] == "domain" and (
            scope["id"] == repo_hint or scope["id"].startswith(repo_hint + ".")
        ):
            total += 3.0
            reasons.append((3.0, f"context repo matched domain scope {scope['id']!r}"))

    domain_hint = context.get("domain")
    if domain_hint and scope["kind"] == "domain":
        if scope["id"] == domain_hint:
            total += 4.0
            reasons.append((4.0, f"context domain matched scope {domain_hint!r}"))
        elif scope["id"].startswith(domain_hint + ".") or domain_hint.startswith(
            scope["id"] + "."
        ):
            total += 2.0
            reasons.append((2.0, f"context domain related to scope {scope['id']!r}"))

    reasons.sort(key=lambda item: item[0], reverse=True)
    return total, [reason for _, reason in reasons[:6]]


class KnowledgeStore:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.index_path = self.root / INDEX_NAME
        self.lock_path = self.root / LOCK_NAME

    @classmethod
    def from_environment(cls) -> "KnowledgeStore":
        raw = os.environ.get("QIQI_KNOWLEDGE_ROOT")
        if not raw or not raw.strip():
            raise KnowledgeError(
                "QIQI_KNOWLEDGE_ROOT must point to the shared knowledge store"
            )
        return cls(Path(raw))

    def initialize(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.lock_path)):
            details = self._scan_details()
            text = render_index(
                [_index_entry(detail, path) for path, detail, _ in details]
            )
            _atomic_write(self.index_path, text)
            return {
                "root": str(self.root),
                "documents": len(details),
                "index": INDEX_NAME,
            }

    def _require_store(self) -> None:
        if not self.root.is_dir():
            raise KnowledgeError(f"knowledge root does not exist: {self.root}")
        if not self.index_path.is_file():
            raise KnowledgeError(
                f"missing {INDEX_NAME}; initialize or reindex the knowledge store"
            )

    def _scan_details(self) -> list[tuple[Path, dict[str, Any], str]]:
        if not self.root.exists():
            return []
        result: list[tuple[Path, dict[str, Any], str]] = []
        ids: set[str] = set()
        for path in sorted(self.root.rglob("*.md")):
            if path == self.index_path:
                continue
            try:
                relative = path.resolve().relative_to(self.root)
            except ValueError as exc:
                raise KnowledgeError(
                    f"knowledge document escaped store root through symlink: {path}"
                ) from exc
            text = path.read_text(encoding="utf-8")
            detail = parse_detail(text, relative.as_posix())
            expected = relative_path_for(
                detail["scope"], detail["canonical_name"]
            )
            if relative != expected:
                raise KnowledgeError(
                    f"{relative.as_posix()}: canonical path is {expected.as_posix()}"
                )
            if detail["id"] in ids:
                raise KnowledgeError(f"duplicate knowledge id: {detail['id']}")
            ids.add(detail["id"])
            result.append((relative, detail, text))
        return result

    def reindex(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.lock_path)):
            details = self._scan_details()
            entries = [_index_entry(detail, path) for path, detail, _ in details]
            text = render_index(entries)
            _atomic_write(self.index_path, text)
            return {
                "root": str(self.root),
                "documents": len(entries),
                "index_revision": _revision(text),
            }

    def check(self) -> dict[str, Any]:
        self._require_store()
        details = self._scan_details()
        expected_entries = [_index_entry(detail, path) for path, detail, _ in details]
        current_text = self.index_path.read_text(encoding="utf-8")
        current_entries = parse_index(current_text)
        if current_entries != sorted(expected_entries, key=lambda item: item["id"]):
            raise KnowledgeError(f"{INDEX_NAME} is stale; run reindex")
        expected_text = render_index(expected_entries)
        if current_text != expected_text:
            raise KnowledgeError(
                f"{INDEX_NAME} is not canonical; run reindex"
            )
        return {
            "root": str(self.root),
            "documents": len(details),
            "index_revision": _revision(current_text),
        }

    def read(
        self,
        keywords: list[str],
        context: dict[str, str] | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        self._require_store()
        clean_keywords = _require_string_list(
            keywords, "keywords", min_items=1, max_items=20
        )
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise KnowledgeError("limit must be an integer from 1 to 20")
        clean_context: dict[str, str] = {}
        if context is not None:
            if not isinstance(context, dict):
                raise KnowledgeError("context must be an object")
            _reject_unknown_keys(context, {"repo", "domain"}, "context")
            for key in ("repo", "domain"):
                raw = context.get(key)
                if raw is not None:
                    clean_context[key] = _require_nonempty_string(
                        raw, f"context.{key}", max_length=200
                    )

        index_text = self.index_path.read_text(encoding="utf-8")
        entries = parse_index(index_text)
        ranked: list[tuple[float, dict[str, Any], list[str]]] = []
        for entry in entries:
            score, reasons = _score_entry(entry, clean_keywords, clean_context)
            if score > 0:
                ranked.append((score, entry, reasons))
        ranked.sort(key=lambda item: (-item[0], item[1]["id"]))

        documents: list[dict[str, Any]] = []
        for score, entry, reasons in ranked[:limit]:
            path = (self.root / entry["path"]).resolve()
            try:
                path.relative_to(self.root)
            except ValueError as exc:
                raise KnowledgeError(
                    f"{INDEX_NAME}: path escaped knowledge root: {entry['path']}"
                ) from exc
            if not path.is_file():
                raise KnowledgeError(
                    f"{INDEX_NAME}: missing document: {entry['path']}; run check/reindex"
                )
            text = path.read_text(encoding="utf-8")
            detail = parse_detail(text, entry["path"])
            if _index_entry(detail, Path(entry["path"])) != entry:
                raise KnowledgeError(
                    f"{INDEX_NAME}: metadata drift for {entry['id']}; run reindex"
                )
            documents.append(
                {
                    "id": detail["id"],
                    "path": entry["path"],
                    "revision": _revision(text),
                    "title": detail["title"],
                    "scope": detail["scope"],
                    "routing": detail["routing"],
                    "sources": detail["sources"],
                    "score": round(score, 3),
                    "match_reason": reasons,
                    "content": detail["content"],
                }
            )
        return {
            "keywords": clean_keywords,
            "context": clean_context,
            "index_revision": _revision(index_text),
            "documents": documents,
        }

    def write(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(entries, list):
            raise KnowledgeError("entries must be a list")
        if len(entries) > 20:
            raise KnowledgeError("entries must contain at most 20 items")
        self.root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.lock_path)):
            existing = self._scan_details()
            by_id = {detail["id"]: (path, detail, text) for path, detail, text in existing}
            staged: list[tuple[str, Path, str, str]] = []
            staged_ids: set[str] = set()

            for index, raw in enumerate(entries):
                if not isinstance(raw, dict):
                    raise KnowledgeError(f"entries[{index}] must be an object")
                raw_id = raw.get("id")
                is_update = raw_id is not None
                payload = _normalize_entry_payload(raw, require_id=is_update)
                entry_id = (
                    _require_nonempty_string(raw_id, f"entries[{index}].id", max_length=400)
                    if is_update
                    else knowledge_id(payload["scope"], payload["canonical_name"])
                )
                if entry_id in staged_ids:
                    raise KnowledgeError(f"duplicate id in write batch: {entry_id}")
                staged_ids.add(entry_id)
                relative = relative_path_for(payload["scope"], payload["canonical_name"])

                if is_update:
                    current = by_id.get(entry_id)
                    if current is None:
                        raise KnowledgeError(f"cannot update missing knowledge id: {entry_id}")
                    current_path, _, current_text = current
                    if current_path != relative:
                        raise KnowledgeError(
                            f"{entry_id}: update cannot change canonical path"
                        )
                    expected_revision = _require_nonempty_string(
                        raw.get("expected_revision"),
                        f"entries[{index}].expected_revision",
                        max_length=128,
                    )
                    current_revision = _revision(current_text)
                    if expected_revision != current_revision:
                        raise KnowledgeError(
                            f"{entry_id}: revision conflict; reread before updating"
                        )
                    action = "updated"
                else:
                    if "expected_revision" in raw:
                        raise KnowledgeError(
                            f"entries[{index}]: create must omit expected_revision"
                        )
                    if entry_id in by_id:
                        raise KnowledgeError(
                            f"knowledge id already exists: {entry_id}; read and update it"
                        )
                    absolute = (self.root / relative).resolve()
                    try:
                        absolute.relative_to(self.root)
                    except ValueError as exc:
                        raise KnowledgeError("canonical path escaped knowledge root") from exc
                    if absolute.exists():
                        raise KnowledgeError(
                            f"canonical path already exists: {relative.as_posix()}"
                        )
                    action = "created"

                rendered = render_detail(payload, entry_id)
                staged.append((action, relative, entry_id, rendered))

            final_entries: dict[str, dict[str, Any]] = {
                detail["id"]: _index_entry(detail, path)
                for path, detail, _ in existing
            }
            for _, relative, entry_id, rendered in staged:
                detail = parse_detail(rendered, relative.as_posix())
                final_entries[entry_id] = _index_entry(detail, relative)

            for action, relative, entry_id, _ in staged:
                if action != "updated":
                    continue
                path = (self.root / relative).resolve()
                current_text = path.read_text(encoding="utf-8")
                raw = next(item for item in entries if item.get("id") == entry_id)
                if _revision(current_text) != raw["expected_revision"]:
                    raise KnowledgeError(
                        f"{entry_id}: revision changed during write; retry after reread"
                    )

            results: list[dict[str, Any]] = []
            for action, relative, entry_id, rendered in staged:
                path = (self.root / relative).resolve()
                try:
                    path.relative_to(self.root)
                except ValueError as exc:
                    raise KnowledgeError("canonical path escaped knowledge root") from exc
                _atomic_write(path, rendered)
                results.append(
                    {
                        "action": action,
                        "id": entry_id,
                        "path": relative.as_posix(),
                        "revision": _revision(rendered),
                    }
                )

            index_text = render_index(list(final_entries.values()))
            _atomic_write(self.index_path, index_text)
            return {
                "reviewed": True,
                "updates": results,
                "index_revision": _revision(index_text),
            }
