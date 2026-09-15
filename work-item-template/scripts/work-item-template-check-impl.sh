#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

required=(
  README.md
  ARTIFACTS.md
  skills/work-item/SKILL.md
  skills/work-item/templates/WORK_ITEM.md
  skills/work-item/templates/intake.md
  skills/work-item/templates/investigation.md
  skills/work-item/templates/plan.md
  skills/work-item/templates/review.md
  skills/work-item/templates/report.textile
  scripts/install-user-skill.sh
  scripts/export-legacy-work-items.py
)
for rel in "${required[@]}"; do
  [[ -f "$home/$rel" ]] || fail "missing required file: $rel"
done

[[ ! -e "$home/mcp" ]] || fail 'legacy Work Item MCP directory must not exist'
[[ ! -e "$home/config/artifact-templates.json" ]] || fail 'legacy MCP artifact template config must not exist'
for rel in CLI.md scripts/install-user-mcp.sh scripts/work-item-cli.sh scripts/work-item-mcp-server.sh; do
  [[ ! -e "$home/$rel" ]] || fail "legacy Work Item MCP surface remains: $rel"
done

skill="$home/skills/work-item/SKILL.md"
for pattern in \
  'current-state task dossier' \
  'Multi-turn continuity MUST be represented as **current semantic state**' \
  'Requirement change không tự invalidate prior findings' \
  'work_item_path=<absolute-workspace-path>/work-items/<directory-key>; id=<canonical-id>; revision=<revision>' \
  '^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$' \
  'separator `~`' \
  'verify nó vẫn nằm dưới resolved `<workspace>/work-items`' \
  'Không tạo mặc định history/turn/execution/checkpoint files' \
  'report.textile'; do
  grep -Fq -- "$pattern" "$skill" || fail "skill missing contract: $pattern"
done

exporter="$home/scripts/export-legacy-work-items.py"
for pattern in \
  'WORK_ITEM_ID_RE = re.compile' \
  'ARTIFACT_TABLES = {' \
  'VALID_STATUSES = {' \
  'return f"{source}~{external_id}"' \
  'REVISIONED_ARTIFACT_TYPES' \
  'based_on_work_item_revision' \
  'render_textile_report' \
  'legacy_default_status="active"' \
  'legacy_default_status="open"' \
  'validate_artifact_schema' \
  'conn.execute("BEGIN")' \
  'section["chunks"] = chunks' \
  'latest_by_type.setdefault' \
  'if the old installer used --db-path' \
  'mode=0o600' \
  'target.resolve().relative_to(root.resolve())' \
  'No filesystem mutation occurs until every record' \
  'migration-backups' \
  'source SQLite DB was not modified'; do
  grep -Fq -- "$pattern" "$exporter" || fail "legacy exporter missing contract: $pattern"
done

if grep -Eq 'work_item_get|work_item_update|work_item_history_read|Global Work Item MCP|WORK_ITEM_DB_PATH' "$home/ARTIFACTS.md" "$skill"; then
  fail 'legacy MCP/SQLite Work Item contract remains in current operational docs'
fi

python3 -m py_compile "$exporter"
bash -n "$home/scripts/install-user-skill.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Main legacy-export fixture: preserve current semantic state, lifecycle provenance,
# exact chunk archive metadata, Textile report shape, and deterministic latest artifact.
mkdir -p "$tmp/workspace"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/workspace/repos.yaml"
python3 - "$tmp/legacy.sqlite3" <<'PY'
import json, sqlite3, sys
path = sys.argv[1]
doc = {
    "id": "redmine:116655",
    "title": "Legacy task",
    "status": "active",
    "phase": "review: security",
    "summary": "Current imported state",
    "current_requirements": ["Preserve legacy requirement"],
    "repos": {
        "demo": {
            "status": "active",
            "summary": "Investigating",
            "verification": ["pytest -q: pass", "lint: pass"],
        }
    },
    "questions": [{"id": "q1", "question": "Legacy unanswered question"}],
    "decisions": [{"id": "d1", "summary": "Legacy active decision"}],
    "changes": [],
    "blockers": [],
    "handoffs": [
        {
            "id": "h1",
            "from": "demo",
            "to": "api",
            "status": "pending",
            "summary": "Finish API change",
        }
    ],
    "next_actions": [
        {"action": "Coordinate remaining work", "repo": "demo", "owner": "platform"}
    ],
    "checkpoints": [],
}
conn = sqlite3.connect(path)
conn.execute("CREATE TABLE work_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
conn.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)", ("redmine:116655", 7, "active", json.dumps(doc), "2026-01-01", "2026-01-02"))
conn.execute("CREATE TABLE work_item_artifacts (work_item_id TEXT NOT NULL, artifact_id TEXT NOT NULL, type TEXT NOT NULL, state TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL, based_on_work_item_revision INTEGER NOT NULL, revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
conn.execute("CREATE TABLE work_item_artifact_sections (work_item_id TEXT NOT NULL, artifact_id TEXT NOT NULL, section_id TEXT NOT NULL, title TEXT NOT NULL, section_order INTEGER NOT NULL, chunk_count INTEGER NOT NULL DEFAULT 0, char_count INTEGER NOT NULL DEFAULT 0, byte_count INTEGER NOT NULL DEFAULT 0)")
conn.execute("CREATE TABLE work_item_artifact_chunks (work_item_id TEXT NOT NULL, artifact_id TEXT NOT NULL, section_id TEXT NOT NULL, chunk_index INTEGER NOT NULL, content TEXT NOT NULL, char_count INTEGER NOT NULL, byte_count INTEGER NOT NULL, created_at TEXT NOT NULL)")

def add_artifact(artifact_id, artifact_type, title, summary, based_on, section_id, section_title, chunks, updated_at):
    conn.execute(
        "INSERT INTO work_item_artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("redmine:116655", artifact_id, artifact_type, "final", title, summary, based_on, 1, "2026-01-01", updated_at),
    )
    content = "".join(chunks)
    conn.execute(
        "INSERT INTO work_item_artifact_sections VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("redmine:116655", artifact_id, section_id, section_title, 0, len(chunks), len(content), len(content.encode())),
    )
    for index, chunk in enumerate(chunks):
        conn.execute(
            "INSERT INTO work_item_artifact_chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("redmine:116655", artifact_id, section_id, index, chunk, len(chunk), len(chunk.encode()), f"2026-01-02T00:00:0{index}"),
        )

add_artifact(
    "investigation:2", "investigation", "Wrong tie winner", "Do not materialize",
    6, "scope", "Scope", ["wrong"], "2026-01-03",
)
add_artifact(
    "investigation:1", "investigation", "Investigation", "Verified finding",
    5, "scope", "Scope", ["Investigated ", "legacy evidence."], "2026-01-03",
)
add_artifact(
    "report:1", "report", "Final report", "Legacy report summary",
    7, "root-cause", "h3. +1. Root-cause/requirement:+", ["Legacy root cause."], "2026-01-02",
)
conn.commit()
conn.close()
PY

python3 "$exporter" --workspace "$tmp/workspace" --db "$tmp/legacy.sqlite3"
dossier="$tmp/workspace/work-items/redmine~116655"
archive="$tmp/workspace/.qiqi/migration-backups/v0024/legacy-work-items/redmine~116655.json"
[[ -f "$dossier/WORK_ITEM.md" ]] || fail 'legacy exporter did not create safe dossier'
[[ -f "$archive" ]] || fail 'legacy exporter did not preserve full archive'
[[ -f "$tmp/legacy.sqlite3" ]] || fail 'legacy exporter modified/deleted source DB'
grep -Fq 'Preserve legacy requirement' "$dossier/WORK_ITEM.md" || fail 'legacy requirement was not exported'
grep -Fxq 'phase: investigation' "$dossier/WORK_ITEM.md" || fail 'unknown legacy phase was not normalized'
grep -Fxq 'legacy_phase: "review: security"' "$dossier/WORK_ITEM.md" || fail 'raw legacy phase was not preserved'
grep -Fq 'Legacy unanswered question' "$dossier/WORK_ITEM.md" || fail 'pre-v1 question without status was dropped'
grep -Fq 'Legacy active decision' "$dossier/WORK_ITEM.md" || fail 'pre-v1 decision without status was dropped'
grep -Fq 'demo -> api: Finish API change' "$dossier/WORK_ITEM.md" || fail 'pending handoff current state was dropped'
grep -Fq 'demo: pytest -q: pass' "$dossier/WORK_ITEM.md" || fail 'repository verification evidence was dropped'
grep -Fq 'Coordinate remaining work (repo=demo, owner=platform)' "$dossier/WORK_ITEM.md" || fail 'next action repo/owner provenance was collapsed'
grep -Fxq 'based_on_work_item_revision: 5' "$dossier/investigation.md" || fail 'artifact Work Item revision provenance/tie ordering drifted'
[[ "$(head -n 1 "$dossier/report.textile")" == 'h3. +1. Root-cause/requirement:+' ]] || fail 'report.textile must start with the canonical Textile section heading'
if grep -Eq '^h1\. |^#{1,6} |^h2\. h3\.' "$dossier/report.textile"; then
  fail 'legacy report.textile contains synthetic/non-canonical heading syntax'
fi
python3 - "$archive" <<'PY'
import json, stat, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
chunks = data["artifacts"][0]["sections"][0]["chunks"]
assert chunks[0]["chunk_index"] == 0
assert "created_at" in chunks[0]
assert stat.S_IMODE(path.stat().st_mode) == 0o600
PY

# Directory-key encoding must be injective for every canonical ID pair.
mkdir -p "$tmp/collision-workspace"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/collision-workspace/repos.yaml"
python3 - "$tmp/collision.sqlite3" <<'PY'
import json, sqlite3, sys
path = sys.argv[1]
conn = sqlite3.connect(path)
conn.execute("CREATE TABLE work_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
for item_id in ("a:b--c", "a--b:c"):
    doc = {"id": item_id, "title": item_id, "status": "active", "phase": "intake", "summary": "collision test", "current_requirements": [], "repos": {}, "questions": [], "decisions": [], "changes": [], "blockers": [], "handoffs": [], "next_actions": [], "checkpoints": []}
    conn.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)", (item_id, 1, "active", json.dumps(doc), "2026-01-01", "2026-01-01"))
conn.commit()
conn.close()
PY
python3 "$exporter" --workspace "$tmp/collision-workspace" --db "$tmp/collision.sqlite3" >/dev/null
[[ -f "$tmp/collision-workspace/work-items/a~b--c/WORK_ITEM.md" ]] || fail 'collision-safe key missing for a:b--c'
[[ -f "$tmp/collision-workspace/work-items/a--b~c/WORK_ITEM.md" ]] || fail 'collision-safe key missing for a--b:c'

# Incomplete artifact schema must fail closed instead of silently dropping artifact state.
mkdir -p "$tmp/partial-workspace"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/partial-workspace/repos.yaml"
python3 - "$tmp/partial.sqlite3" <<'PY'
import json, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
doc = {"id": "redmine:partial", "title": "partial", "status": "active", "phase": "intake", "summary": "", "current_requirements": [], "repos": {}, "questions": [], "decisions": [], "changes": [], "blockers": [], "handoffs": [], "next_actions": [], "checkpoints": []}
conn.execute("CREATE TABLE work_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
conn.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)", ("redmine:partial", 1, "active", json.dumps(doc), "2026-01-01", "2026-01-01"))
conn.execute("CREATE TABLE work_item_artifacts (work_item_id TEXT, artifact_id TEXT, type TEXT)")
conn.commit()
conn.close()
PY
if python3 "$exporter" --workspace "$tmp/partial-workspace" --db "$tmp/partial.sqlite3" >/dev/null 2>&1; then
  fail 'incomplete legacy artifact schema must fail closed'
fi
[[ ! -e "$tmp/partial-workspace/work-items/redmine~partial/WORK_ITEM.md" ]] || fail 'partial-schema failure wrote a dossier'

# An absent selected DB must be an error; old installs may have used --db-path.
mkdir -p "$tmp/missing-db-workspace"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/missing-db-workspace/repos.yaml"
if python3 "$exporter" --workspace "$tmp/missing-db-workspace" --db "$tmp/does-not-exist.sqlite3" >/dev/null 2>&1; then
  fail 'missing selected legacy DB must not report a successful export'
fi

# Preflight must detect a conflict in a later item before writing any earlier item.
mkdir -p "$tmp/preflight-workspace/work-items/redmine~2"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/preflight-workspace/repos.yaml"
printf 'occupied\n' > "$tmp/preflight-workspace/work-items/redmine~2/existing.txt"
python3 - "$tmp/preflight.sqlite3" <<'PY'
import json, sqlite3, sys
path = sys.argv[1]
conn = sqlite3.connect(path)
conn.execute("CREATE TABLE work_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
for item_id in ("redmine:1", "redmine:2"):
    doc = {
        "id": item_id, "title": item_id, "status": "active", "phase": "uat",
        "summary": "legacy", "current_requirements": [], "repos": {},
        "questions": [], "decisions": [], "changes": [], "blockers": [],
        "handoffs": [], "next_actions": [], "checkpoints": [],
    }
    conn.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)", (item_id, 1, "active", json.dumps(doc), "2026-01-01", "2026-01-01"))
conn.commit()
conn.close()
PY
if python3 "$exporter" --workspace "$tmp/preflight-workspace" --db "$tmp/preflight.sqlite3" >/dev/null 2>&1; then
  fail 'legacy exporter must fail preflight when a later target conflicts'
fi
[[ ! -e "$tmp/preflight-workspace/work-items/redmine~1/WORK_ITEM.md" ]] || fail 'legacy exporter wrote earlier items before completing preflight'

# Installer must adopt only the complete identical skill tree, not a matching SKILL.md
# with missing/outdated templates.
bad_codex="$tmp/install-bad-codex"
bad_claude="$tmp/install-bad-claude"
mkdir -p "$bad_codex/work-item" "$bad_claude/work-item"
cp "$home/skills/work-item/SKILL.md" "$bad_codex/work-item/SKILL.md"
cp "$home/skills/work-item/SKILL.md" "$bad_claude/work-item/SKILL.md"
if bash "$home/scripts/install-user-skill.sh" --codex-root "$bad_codex" --claude-root "$bad_claude" >/dev/null 2>&1; then
  fail 'installer adopted an incomplete unmanaged skill tree'
fi
[[ ! -e "$bad_codex/work-item/.agent-knowledge-harness-managed" ]] || fail 'incomplete Codex skill was marked managed'

good_codex="$tmp/install-good-codex"
good_claude="$tmp/install-good-claude"
mkdir -p "$good_codex/work-item" "$good_claude/work-item"
cp -R "$home/skills/work-item/." "$good_codex/work-item/"
cp -R "$home/skills/work-item/." "$good_claude/work-item/"
bash "$home/scripts/install-user-skill.sh" --codex-root "$good_codex" --claude-root "$good_claude" >/dev/null
[[ -f "$good_codex/work-item/.agent-knowledge-harness-managed" ]] || fail 'identical Codex skill tree was not adopted'
[[ -f "$good_claude/work-item/.agent-knowledge-harness-managed" ]] || fail 'identical Claude skill tree was not adopted'

printf 'Work Item filesystem template: OK\n'