from __future__ import annotations

import hashlib
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml
from filelock import FileLock

from sections import SectionError, parse_sections

INDEX_FILENAME = "INDEX.md"
LOCK_FILENAME = ".knowledge.lock"
INDEX_VERSION = 1
DOCUMENT_VERSION = 1
MAX_CONTENT_CHARS = 24_000
MAX_DOCUMENT_BYTES = 32_768
MAX_SEARCH_RESULTS = 10
DEFAULT_SEARCH_RESULTS = 5
MAX_READ_RESULTS = 2
MAX_SEARCH_WHEN_TO_READ = 3
MAX_SEARCH_MATCHES = 3
MAX_QUERY_SCORE_CONTRIBUTIONS = 3
LOCK_TIMEOUT_SECONDS = 30
SCOPE_KINDS = {"global", "system", "repo", "domain"}
SOURCE_KINDS = {"repo", "document", "decision", "manual", "url"}
CANONICAL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCOPE_ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
NAMESPACE_DIRS = {"global", "systems", "repos", "domains"}


class KnowledgeError(RuntimeError):
    pass


class ValidationError(KnowledgeError):
    pass


class ConflictError(KnowledgeError):
    pass


def _validate_section_structure(content: str, *, label: str) -> None:
    try:
        parse_sections(content)
    except SectionError as exc:
        raise ValidationError(f"{label}: {exc}") from exc


@dataclass(frozen=True)
class Document:
    path: Path
    relative_path: str
    metadata: dict[str, Any]
    body: str
    revision: str

    @property
    def id(self) -> str:
        return self.metadata["id"]


def resolve_store_root(raw: str | os.PathLike[str]) -> Path:
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise KnowledgeError(f"knowledge store root does not exist: {root}")
    return root


def _ensure_within(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValidationError(f"knowledge path escapes store root: {path}") from exc
    return resolved


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("_", " ")
    out: list[str] = []
    for char in value:
        category = unicodedata.category(char)
        if char.isalnum() or category.startswith("L") or category.startswith("N"):
            out.append(char)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _tokens(value: str) -> set[str]:
    normalized = _normalize_text(value)
    return set(normalized.split()) if normalized else set()


def _require_string(value: Any, label: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    value = value.strip()
    if len(value) > max_length:
        raise ValidationError(f"{label} exceeds {max_length} characters")
    return value


def _require_string_list(
    value: Any,
    label: str,
    *,
    min_items: int,
    max_items: int,
    max_item_length: int,
) -> list[str]:
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be a list")
    if not (min_items <= len(value) <= max_items):
        raise ValidationError(
            f"{label} must contain between {min_items} and {max_items} items"
        )
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        text = _require_string(item, f"{label}[{index}]", max_length=max_item_length)
        key = _normalize_text(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    if len(result) < min_items:
        raise ValidationError(f"{label} has too few unique values")
    return result


def _validate_scope(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValidationError("scope must be an object")
    extra = set(value) - {"kind", "id"}
    if extra:
        raise ValidationError(f"scope has unsupported field(s): {', '.join(sorted(extra))}")
    kind = _require_string(value.get("kind"), "scope.kind", max_length=20)
    scope_id = _require_string(value.get("id"), "scope.id", max_length=120)
    if kind not in SCOPE_KINDS:
        raise ValidationError(f"scope.kind must be one of: {', '.join(sorted(SCOPE_KINDS))}")
    if not SCOPE_ID_RE.fullmatch(scope_id):
        raise ValidationError(
            "scope.id must use lowercase letters/numbers with '.' or '-' separators"
        )
    return {"kind": kind, "id": scope_id}


def _validate_routing(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("routing must be an object")
    extra = set(value) - {"summary", "when_to_read", "keywords", "aliases"}
    if extra:
        raise ValidationError(
            f"routing has unsupported field(s): {', '.join(sorted(extra))}"
        )
    summary = _require_string(value.get("summary"), "routing.summary", max_length=500)
    when_to_read = _require_string_list(
        value.get("when_to_read"),
        "routing.when_to_read",
        min_items=1,
        max_items=20,
        max_item_length=300,
    )
    keywords = _require_string_list(
        value.get("keywords"),
        "routing.keywords",
        min_items=3,
        max_items=30,
        max_item_length=120,
    )
    aliases = _require_string_list(
        value.get("aliases", []),
        "routing.aliases",
        min_items=0,
        max_items=30,
        max_item_length=120,
    )
    return {
        "summary": summary,
        "when_to_read": when_to_read,
        "keywords": keywords,
        "aliases": aliases,
    }


def _validate_sources(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValidationError("sources must be a non-empty list")
    if len(value) > 30:
        raise ValidationError("sources must contain at most 30 items")
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValidationError(f"sources[{index}] must be an object")
        extra = set(item) - {"kind", "locator", "ref", "note"}
        if extra:
            raise ValidationError(
                f"sources[{index}] has unsupported field(s): {', '.join(sorted(extra))}"
            )
        kind = _require_string(item.get("kind"), f"sources[{index}].kind", max_length=20)
        if kind not in SOURCE_KINDS:
            raise ValidationError(
                f"sources[{index}].kind must be one of: {', '.join(sorted(SOURCE_KINDS))}"
            )
        locator = _require_string(
            item.get("locator"), f"sources[{index}].locator", max_length=1000
        )
        normalized: dict[str, str] = {"kind": kind, "locator": locator}
        if item.get("ref") is not None:
            normalized["ref"] = _require_string(
                item.get("ref"), f"sources[{index}].ref", max_length=200
            )
        if item.get("note") is not None:
            normalized["note"] = _require_string(
                item.get("note"), f"sources[{index}].note", max_length=1000
            )
        result.append(normalized)
    return result


def knowledge_id(scope: dict[str, str], canonical_name: str) -> str:
    return f"{scope['kind']}:{scope['id']}:{canonical_name}"


def canonical_relative_path(scope: dict[str, str], canonical_name: str) -> str:
    scope_id = scope["id"]
    if scope["kind"] == "global":
        prefix = Path("global") / scope_id
    elif scope["kind"] == "system":
        prefix = Path("systems") / scope_id
    elif scope["kind"] == "repo":
        prefix = Path("repos") / scope_id
    elif scope["kind"] == "domain":
        prefix = Path("domains") / Path(*scope_id.split("."))
    else:
        raise ValidationError(f"unsupported scope kind: {scope['kind']}")
    return (prefix / f"{canonical_name}.md").as_posix()


def validate_metadata(value: Any, *, expected_path: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("document front matter must be a mapping")
    allowed = {
        "version",
        "id",
        "canonical_name",
        "title",
        "scope",
        "routing",
        "sources",
    }
    extra = set(value) - allowed
    if extra:
        raise ValidationError(
            f"document has unsupported front-matter field(s): {', '.join(sorted(extra))}"
        )
    if value.get("version") != DOCUMENT_VERSION:
        raise ValidationError(f"document version must be {DOCUMENT_VERSION}")

    canonical_name = _require_string(
        value.get("canonical_name"), "canonical_name", max_length=100
    )
    if not CANONICAL_NAME_RE.fullmatch(canonical_name):
        raise ValidationError(
            "canonical_name must be lowercase kebab-case English/canonical terminology"
        )
    title = _require_string(value.get("title"), "title", max_length=200)
    scope = _validate_scope(value.get("scope"))
    routing = _validate_routing(value.get("routing"))
    sources = _validate_sources(value.get("sources"))
    expected_id = knowledge_id(scope, canonical_name)
    actual_id = _require_string(value.get("id"), "id", max_length=260)
    if actual_id != expected_id:
        raise ValidationError(f"id must be derived from scope + canonical_name: {expected_id}")
    canonical_path = canonical_relative_path(scope, canonical_name)
    if expected_path is not None and expected_path != canonical_path:
        raise ValidationError(
            f"document is stored at {expected_path!r}; canonical path is {canonical_path!r}"
        )
    return {
        "version": DOCUMENT_VERSION,
        "id": expected_id,
        "canonical_name": canonical_name,
        "title": title,
        "scope": scope,
        "routing": routing,
        "sources": sources,
    }


def validate_write_entry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("knowledge write entry must be an object")
    allowed = {
        "id",
        "expected_revision",
        "canonical_name",
        "title",
        "scope",
        "routing",
        "content",
        "sources",
    }
    extra = set(value) - allowed
    if extra:
        raise ValidationError(
            f"knowledge write entry has unsupported field(s): {', '.join(sorted(extra))}"
        )
    canonical_name = _require_string(
        value.get("canonical_name"), "canonical_name", max_length=100
    )
    if not CANONICAL_NAME_RE.fullmatch(canonical_name):
        raise ValidationError("canonical_name must be lowercase kebab-case")
    title = _require_string(value.get("title"), "title", max_length=200)
    scope = _validate_scope(value.get("scope"))
    routing = _validate_routing(value.get("routing"))
    sources = _validate_sources(value.get("sources"))
    content = value.get("content")
    if not isinstance(content, str):
        raise ValidationError("content must be a string")
    _validate_section_structure(content, label="knowledge write content")
    content = content.strip()
    if len(content) > MAX_CONTENT_CHARS:
        raise ValidationError(f"content exceeds {MAX_CONTENT_CHARS} characters")

    derived_id = knowledge_id(scope, canonical_name)
    provided_id = value.get("id")
    expected_revision = value.get("expected_revision")
    if provided_id is None:
        if expected_revision is not None:
            raise ValidationError("expected_revision is only valid when updating by id")
    else:
        provided_id = _require_string(provided_id, "id", max_length=260)
        if provided_id != derived_id:
            raise ValidationError(f"id must match scope + canonical_name: {derived_id}")
        expected_revision = _require_string(
            expected_revision, "expected_revision", max_length=128
        )
        if not re.fullmatch(r"[0-9a-f]{64}", expected_revision):
            raise ValidationError("expected_revision must be a lowercase SHA-256 hex digest")

    return {
        "id": derived_id if provided_id is not None else None,
        "expected_revision": expected_revision,
        "canonical_name": canonical_name,
        "title": title,
        "scope": scope,
        "routing": routing,
        "content": content,
        "sources": sources,
        "derived_id": derived_id,
        "path": canonical_relative_path(scope, canonical_name),
    }


def _split_front_matter(text: str, *, label: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValidationError(f"{label}: missing YAML front matter")
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise ValidationError(f"{label}: unterminated YAML front matter")
    raw = "".join(lines[1:end])
    try:
        metadata = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"{label}: invalid YAML front matter: {exc}") from exc
    body = "".join(lines[end + 1 :]).lstrip("\r\n")
    return metadata, body


def _revision(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_document(root: Path, path: Path) -> Document:
    resolved = _ensure_within(root, path)
    if not resolved.is_file():
        raise ValidationError(f"knowledge document does not exist: {resolved}")
    data = resolved.read_bytes()
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ValidationError(
            f"knowledge document exceeds {MAX_DOCUMENT_BYTES} bytes: {resolved}"
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"knowledge document is not UTF-8: {resolved}") from exc
    relative = resolved.relative_to(root.resolve()).as_posix()
    metadata_raw, body = _split_front_matter(text, label=relative)
    metadata = validate_metadata(metadata_raw, expected_path=relative)
    expected_heading = f"# {metadata['title']}"
    first_body_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if first_body_line != expected_heading:
        raise ValidationError(
            f"{relative}: first body heading must exactly match title: {expected_heading}"
        )
    _validate_section_structure(body, label=relative)
    return Document(
        path=resolved,
        relative_path=relative,
        metadata=metadata,
        body=body,
        revision=_revision(data),
    )


def _document_content(document: Document) -> str:
    lines = document.body.splitlines()
    heading_index = next((i for i, line in enumerate(lines) if line.strip()), None)
    if heading_index is None:
        return ""
    return "\n".join(lines[heading_index + 1 :]).strip()


def _detail_paths(root: Path) -> Iterable[Path]:
    for namespace in sorted(NAMESPACE_DIRS):
        directory = root / namespace
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise ValidationError(f"knowledge namespace is not a directory: {directory}")
        yield from sorted(directory.rglob("*.md"))


def scan_documents(root: Path) -> dict[str, Document]:
    root = resolve_store_root(root)
    unexpected = sorted(
        path.relative_to(root).as_posix()
        for path in root.glob("*.md")
        if path.name != INDEX_FILENAME
    )
    if unexpected:
        raise ValidationError(
            "knowledge Markdown must live under a namespace directory; unexpected: "
            + ", ".join(unexpected)
        )
    documents: dict[str, Document] = {}
    seen_paths: set[str] = set()
    for path in _detail_paths(root):
        document = _load_document(root, path)
        if document.id in documents:
            raise ValidationError(f"duplicate knowledge id: {document.id}")
        if document.relative_path in seen_paths:
            raise ValidationError(f"duplicate knowledge path: {document.relative_path}")
        documents[document.id] = document
        seen_paths.add(document.relative_path)
    return documents


def _index_entry(document: Document) -> dict[str, Any]:
    routing = document.metadata["routing"]
    return {
        "id": document.id,
        "path": document.relative_path,
        "revision": document.revision,
        "canonical_name": document.metadata["canonical_name"],
        "title": document.metadata["title"],
        "scope": document.metadata["scope"],
        "summary": routing["summary"],
        "when_to_read": routing["when_to_read"],
        "keywords": routing["keywords"],
        "aliases": routing["aliases"],
    }


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_index(documents: dict[str, Document]) -> str:
    entries = [_index_entry(documents[key]) for key in sorted(documents)]
    metadata = {
        "version": INDEX_VERSION,
        "generated": True,
        "entries": entries,
    }
    front = yaml.safe_dump(
        metadata,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip()
    lines = [
        "---",
        front,
        "---",
        "",
        "# Knowledge Index",
        "",
        "Generated from canonical metadata in knowledge documents. Do not hand-edit this file; edit a detail document and run `knowledge reindex`.",
        "",
        "| ID | Path | Scope | Summary | When to read |",
        "|---|---|---|---|---|",
    ]
    for entry in entries:
        scope = f"{entry['scope']['kind']}:{entry['scope']['id']}"
        when = "; ".join(entry["when_to_read"])
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} |".format(
                _escape_table(entry["id"]),
                _escape_table(entry["path"]),
                _escape_table(scope),
                _escape_table(entry["summary"]),
                _escape_table(when),
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _render_document(entry: dict[str, Any]) -> bytes:
    metadata = {
        "version": DOCUMENT_VERSION,
        "id": entry["derived_id"],
        "canonical_name": entry["canonical_name"],
        "title": entry["title"],
        "scope": entry["scope"],
        "routing": entry["routing"],
        "sources": entry["sources"],
    }
    front = yaml.safe_dump(
        metadata,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip()
    content = entry["content"]
    body = f"# {entry['title']}"
    if content:
        body += f"\n\n{content}"
    text = f"---\n{front}\n---\n\n{body.rstrip()}\n"
    data = text.encode("utf-8")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ValidationError(
            f"rendered knowledge document exceeds {MAX_DOCUMENT_BYTES} bytes"
        )
    return data


def _parse_index(root: Path) -> list[dict[str, Any]]:
    index_path = root / INDEX_FILENAME
    if not index_path.is_file():
        raise KnowledgeError(f"missing knowledge index: {index_path}; run knowledge reindex")
    text = index_path.read_text(encoding="utf-8")
    metadata, _ = _split_front_matter(text, label=INDEX_FILENAME)
    if not isinstance(metadata, dict) or metadata.get("version") != INDEX_VERSION:
        raise ValidationError(f"{INDEX_FILENAME}: version must be {INDEX_VERSION}")
    if metadata.get("generated") is not True:
        raise ValidationError(f"{INDEX_FILENAME}: generated must be true")
    entries = metadata.get("entries")
    if not isinstance(entries, list):
        raise ValidationError(f"{INDEX_FILENAME}: entries must be a list")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise ValidationError(f"{INDEX_FILENAME}: entries[{index}] must be an object")
        required = {
            "id",
            "path",
            "revision",
            "canonical_name",
            "title",
            "scope",
            "summary",
            "when_to_read",
            "keywords",
            "aliases",
        }
        if set(raw) != required:
            raise ValidationError(
                f"{INDEX_FILENAME}: entries[{index}] fields do not match generated schema"
            )
        scope = _validate_scope(raw["scope"])
        canonical_name = _require_string(
            raw["canonical_name"], f"entries[{index}].canonical_name", max_length=100
        )
        if not CANONICAL_NAME_RE.fullmatch(canonical_name):
            raise ValidationError(f"{INDEX_FILENAME}: invalid canonical_name")
        expected_id = knowledge_id(scope, canonical_name)
        item_id = _require_string(raw["id"], f"entries[{index}].id", max_length=260)
        if item_id != expected_id:
            raise ValidationError(f"{INDEX_FILENAME}: id is not canonical: {item_id}")
        path = _require_string(raw["path"], f"entries[{index}].path", max_length=500)
        if path != canonical_relative_path(scope, canonical_name):
            raise ValidationError(f"{INDEX_FILENAME}: path is not canonical for {item_id}")
        revision = _require_string(
            raw["revision"], f"entries[{index}].revision", max_length=128
        )
        if not re.fullmatch(r"[0-9a-f]{64}", revision):
            raise ValidationError(f"{INDEX_FILENAME}: invalid revision for {item_id}")
        title = _require_string(raw["title"], f"entries[{index}].title", max_length=200)
        summary = _require_string(raw["summary"], f"entries[{index}].summary", max_length=500)
        when_to_read = _require_string_list(
            raw["when_to_read"],
            f"entries[{index}].when_to_read",
            min_items=1,
            max_items=20,
            max_item_length=300,
        )
        keywords = _require_string_list(
            raw["keywords"],
            f"entries[{index}].keywords",
            min_items=3,
            max_items=30,
            max_item_length=120,
        )
        aliases = _require_string_list(
            raw["aliases"],
            f"entries[{index}].aliases",
            min_items=0,
            max_items=30,
            max_item_length=120,
        )
        if item_id in seen_ids:
            raise ValidationError(f"{INDEX_FILENAME}: duplicate id {item_id}")
        if path in seen_paths:
            raise ValidationError(f"{INDEX_FILENAME}: duplicate path {path}")
        seen_ids.add(item_id)
        seen_paths.add(path)
        normalized.append(
            {
                "id": item_id,
                "path": path,
                "revision": revision,
                "canonical_name": canonical_name,
                "title": title,
                "scope": scope,
                "summary": summary,
                "when_to_read": when_to_read,
                "keywords": keywords,
                "aliases": aliases,
            }
        )
    return normalized


def init_store(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for namespace in sorted(NAMESPACE_DIRS):
        (root / namespace).mkdir(parents=True, exist_ok=True)
    index_path = root / INDEX_FILENAME
    if not index_path.exists():
        _atomic_write(index_path, render_index({}).encode("utf-8"))
    elif not index_path.is_file():
        raise ValidationError(f"knowledge index path is not a file: {index_path}")
    return {"store_root": str(root), "index_path": INDEX_FILENAME}


def check_store(root: Path) -> dict[str, Any]:
    root = resolve_store_root(root)
    errors: list[str] = []
    documents: dict[str, Document] = {}
    try:
        documents = scan_documents(root)
    except KnowledgeError as exc:
        errors.append(str(exc))
    try:
        index_entries = _parse_index(root)
        if not errors:
            expected = [_index_entry(documents[key]) for key in sorted(documents)]
            if index_entries != expected:
                errors.append(
                    f"{INDEX_FILENAME} is stale or does not match canonical document metadata; run knowledge reindex"
                )
    except KnowledgeError as exc:
        errors.append(str(exc))
    return {
        "ok": not errors,
        "documents": len(documents),
        "errors": errors,
    }


def reindex_store(root: Path) -> dict[str, Any]:
    root = resolve_store_root(root)
    lock = FileLock(str(root / LOCK_FILENAME), timeout=LOCK_TIMEOUT_SECONDS)
    with lock:
        documents = scan_documents(root)
        rendered = render_index(documents).encode("utf-8")
        _atomic_write(root / INDEX_FILENAME, rendered)
    return {"documents": len(documents), "index_path": INDEX_FILENAME}


def _best_text_score(query: str, values: list[str], exact: int, contains: int, token: int) -> int:
    q = _normalize_text(query)
    if not q:
        return 0
    q_tokens = _tokens(q)
    best = 0
    for value in values:
        normalized = _normalize_text(value)
        if not normalized:
            continue
        if normalized == q:
            best = max(best, exact)
            continue
        if q in normalized or normalized in q:
            best = max(best, contains)
        value_tokens = _tokens(normalized)
        if q_tokens and value_tokens:
            overlap = len(q_tokens & value_tokens) / len(q_tokens | value_tokens)
            if overlap:
                best = max(best, round(token * overlap))
    return best


def _score_entry(
    entry: dict[str, Any],
    queries: list[str],
    context: dict[str, str] | None,
) -> tuple[int, list[dict[str, str]]]:
    contributions: list[tuple[int, int, str, str]] = []
    for query_index, query in enumerate(queries):
        q = _normalize_text(query)
        if not q:
            continue
        parts: list[tuple[str, int]] = []
        if q == _normalize_text(entry["id"]):
            parts.append(("exact_id", 220))
        if q == _normalize_text(entry["canonical_name"]):
            parts.append(("canonical_name", 190))
        for field, value in (
            ("keyword", _best_text_score(query, entry["keywords"], 110, 80, 55)),
            ("alias", _best_text_score(query, entry["aliases"], 100, 75, 50)),
            ("when_to_read", _best_text_score(query, entry["when_to_read"], 85, 60, 45)),
            ("summary", _best_text_score(query, [entry["summary"]], 65, 45, 35)),
        ):
            if value:
                parts.append((field, value))
        if parts:
            best_score = max(value for _, value in parts)
            best_field = next(field for field, value in parts if value == best_score)
            contributions.append((best_score, query_index, query, best_field))

    if not contributions:
        return 0, []

    contributions.sort(key=lambda item: (-item[0], item[1], item[3]))
    score = sum(item[0] for item in contributions[:MAX_QUERY_SCORE_CONTRIBUTIONS])

    if context:
        repo = context.get("repo")
        domain = context.get("domain")
        scope = entry["scope"]
        if repo:
            repo_norm = _normalize_text(repo)
            if scope["kind"] == "repo" and _normalize_text(scope["id"]) == repo_norm:
                score += 25
            elif scope["kind"] == "domain" and _normalize_text(scope["id"]).startswith(
                repo_norm + " "
            ):
                score += 18
        if domain:
            domain_norm = _normalize_text(domain)
            scope_norm = _normalize_text(scope["id"])
            if scope["kind"] == "domain" and (
                scope_norm == domain_norm or scope_norm.startswith(domain_norm + " ")
            ):
                score += 30

    matches = [
        {"query": query, "field": field}
        for _, _, query, field in contributions[:MAX_SEARCH_MATCHES]
    ]
    return score, matches


def _validate_search_query(
    keywords: Any,
    context: Any,
    limit: Any,
) -> tuple[list[str], dict[str, str] | None, int]:
    queries = _require_string_list(
        keywords,
        "keywords",
        min_items=1,
        max_items=20,
        max_item_length=200,
    )
    if not isinstance(limit, int) or isinstance(limit, bool) or not (
        1 <= limit <= MAX_SEARCH_RESULTS
    ):
        raise ValidationError(
            f"limit must be an integer between 1 and {MAX_SEARCH_RESULTS}"
        )
    normalized_context: dict[str, str] | None = None
    if context is not None:
        if not isinstance(context, dict):
            raise ValidationError("context must be an object")
        extra = set(context) - {"repo", "domain"}
        if extra:
            raise ValidationError(
                f"context has unsupported field(s): {', '.join(sorted(extra))}"
            )
        normalized_context = {}
        for field in ("repo", "domain"):
            if context.get(field) is not None:
                normalized_context[field] = _require_string(
                    context[field], f"context.{field}", max_length=120
                )
        if not normalized_context:
            normalized_context = None
    return queries, normalized_context, limit


def _validate_read_ids(ids: Any) -> list[str]:
    normalized = _require_string_list(
        ids,
        "ids",
        min_items=1,
        max_items=MAX_READ_RESULTS,
        max_item_length=260,
    )
    if len(normalized) != len(ids):
        raise ValidationError("ids must contain unique exact knowledge ids")
    return normalized


def _load_verified_index_document(
    root: Path,
    entry: dict[str, Any],
) -> Document:
    path = _ensure_within(root, root / entry["path"])
    document = _load_document(root, path)
    if document.id != entry["id"]:
        raise ConflictError(
            f"knowledge index points to a different id at {entry['path']}; run knowledge reindex"
        )
    if document.revision != entry["revision"]:
        raise ConflictError(
            f"knowledge index is stale for {entry['id']}; run knowledge reindex before reading"
        )
    return document


def search_knowledge(
    root: Path,
    keywords: Any,
    context: Any = None,
    limit: int = DEFAULT_SEARCH_RESULTS,
) -> dict[str, Any]:
    root = resolve_store_root(root)
    queries, normalized_context, normalized_limit = _validate_search_query(
        keywords, context, limit
    )
    index_entries = _parse_index(root)
    ranked: list[tuple[int, dict[str, Any], list[dict[str, str]]]] = []
    for entry in index_entries:
        score, matches = _score_entry(entry, queries, normalized_context)
        if score > 0:
            ranked.append((score, entry, matches))
    ranked.sort(key=lambda item: (-item[0], item[1]["id"]))

    results: list[dict[str, Any]] = []
    for score, entry, matches in ranked[:normalized_limit]:
        _load_verified_index_document(root, entry)
        results.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "scope": entry["scope"],
                "summary": entry["summary"],
                "when_to_read": entry["when_to_read"][:MAX_SEARCH_WHEN_TO_READ],
                "matches": matches,
                "score": score,
            }
        )
    return {"results": results}


def read_knowledge(root: Path, ids: Any) -> dict[str, Any]:
    root = resolve_store_root(root)
    normalized_ids = _validate_read_ids(ids)
    index_entries = _parse_index(root)
    by_id = {entry["id"]: entry for entry in index_entries}

    results: list[dict[str, Any]] = []
    for item_id in normalized_ids:
        entry = by_id.get(item_id)
        if entry is None:
            raise KnowledgeError(f"knowledge id does not exist: {item_id}")
        document = _load_verified_index_document(root, entry)
        results.append(
            {
                "id": document.id,
                "revision": document.revision,
                "canonical_name": document.metadata["canonical_name"],
                "title": document.metadata["title"],
                "scope": document.metadata["scope"],
                "routing": document.metadata["routing"],
                "sources": document.metadata["sources"],
                "content": _document_content(document),
            }
        )
    return {"results": results}


def write_knowledge(root: Path, entries: Any) -> dict[str, Any]:
    root = resolve_store_root(root)
    if not isinstance(entries, list):
        raise ValidationError("entries must be a list")
    if len(entries) > 20:
        raise ValidationError("entries must contain at most 20 items")
    normalized = [validate_write_entry(item) for item in entries]
    derived_ids = [item["derived_id"] for item in normalized]
    if len(set(derived_ids)) != len(derived_ids):
        raise ValidationError("knowledge_write batch contains duplicate derived ids")
    if not normalized:
        return {"reviewed": True, "changes": []}

    lock = FileLock(str(root / LOCK_FILENAME), timeout=LOCK_TIMEOUT_SECONDS)
    with lock:
        current = scan_documents(root)
        planned: list[tuple[dict[str, Any], Path, bytes, str]] = []
        for entry in normalized:
            item_id = entry["derived_id"]
            path = _ensure_within(root, root / entry["path"])
            existing = current.get(item_id)
            if entry["id"] is None:
                if existing is not None or path.exists():
                    collision = existing.id if existing is not None else entry["path"]
                    raise ConflictError(
                        f"knowledge already exists or collides with create target: {collision}"
                    )
                operation = "created"
            else:
                if existing is None:
                    raise ConflictError(f"knowledge id does not exist for update: {item_id}")
                if existing.relative_path != entry["path"]:
                    raise ConflictError(
                        f"knowledge id resolves to {existing.relative_path}, not {entry['path']}"
                    )
                if existing.revision != entry["expected_revision"]:
                    raise ConflictError(
                        f"knowledge revision conflict for {item_id}: expected {entry['expected_revision']}, current {existing.revision}"
                    )
                operation = "updated"
            rendered = _render_document(entry)
            planned.append((entry, path, rendered, operation))

        backups: dict[Path, bytes | None] = {}
        index_path = root / INDEX_FILENAME
        original_index = index_path.read_bytes() if index_path.exists() else None
        changes: list[dict[str, Any]] = []
        try:
            for entry, path, rendered, operation in planned:
                backups[path] = path.read_bytes() if path.exists() else None
                if entry["id"] is not None:
                    current_bytes = path.read_bytes()
                    current_revision = _revision(current_bytes)
                    if current_revision != entry["expected_revision"]:
                        raise ConflictError(
                            f"knowledge changed during update for {entry['derived_id']}: expected {entry['expected_revision']}, current {current_revision}"
                        )
                elif path.exists():
                    raise ConflictError(
                        f"knowledge create target appeared during write: {entry['path']}"
                    )
                _atomic_write(path, rendered)
                revision = _revision(rendered)
                changes.append(
                    {
                        "operation": operation,
                        "id": entry["derived_id"],
                        "path": entry["path"],
                        "revision": revision,
                    }
                )

            refreshed = scan_documents(root)
            _atomic_write(index_path, render_index(refreshed).encode("utf-8"))
        except BaseException:
            for path, old in reversed(list(backups.items())):
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write(path, old)
            if original_index is None:
                index_path.unlink(missing_ok=True)
            else:
                _atomic_write(index_path, original_index)
            raise
    return {"reviewed": True, "changes": changes}
