#!/usr/bin/env bash
set -euo pipefail

home="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

required=(
  README.md
  ARTIFACTS.md
  skills/work-item/SKILL.md
  skills/work-item/templates/00_WORK_ITEM.md
  skills/work-item/templates/10_intake.md
  skills/work-item/templates/20_investigation.md
  skills/work-item/templates/30_plan.md
  skills/work-item/templates/40_review.md
  skills/work-item/templates/90_report.textile
  scripts/install-user-skill.sh
  scripts/export-legacy-work-items.py
  scripts/remove-legacy-user-mcp.sh
)
for rel in "${required[@]}"; do
  [[ -f "$home/$rel" ]] || fail "missing required file: $rel"
done

for legacy in WORK_ITEM.md intake.md investigation.md plan.md review.md report.textile; do
  [[ ! -e "$home/skills/work-item/templates/$legacy" ]] || fail "legacy unprefixed Work Item template remains: $legacy"
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
  'casefold-unique directory keys' \
  'front-matter `id` khớp **exact canonical ID**' \
  'legacy_reconciliation_required: true' \
  'verify nó vẫn nằm dưới resolved `<workspace>/work-items`' \
  'Không tạo mặc định history/turn/execution/checkpoint files' \
  '00_WORK_ITEM.md' \
  '10_intake.md' \
  '20_investigation.md' \
  '30_plan.md' \
  '40_review.md' \
  '90_report.textile'; do
  grep -Fq -- "$pattern" "$skill" || fail "skill missing contract: $pattern"
done

exporter="$home/scripts/export-legacy-work-items.py"
for pattern in \
  'WORK_ITEM_ID_RE = re.compile' \
  'ARTIFACT_TABLES = {' \
  'VALID_STATUSES = {' \
  'def casefold_key' \
  'legacy_reconciliation_required: true' \
  'DECISION_CORE_FIELDS' \
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
  'case-insensitive-equivalent' \
  '"intake": "10_intake.md"' \
  '"investigation": "20_investigation.md"' \
  '"plan": "30_plan.md"' \
  '"review": "40_review.md"' \
  '"report": "90_report.textile"' \
  'target / "00_WORK_ITEM.md"' \
  'source SQLite DB was not modified'; do
  grep -Fq -- "$pattern" "$exporter" || fail "legacy exporter missing contract: $pattern"
done

python3 -m py_compile "$exporter"
bash -n "$home/scripts/install-user-skill.sh"
bash -n "$home/scripts/remove-legacy-user-mcp.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Main legacy fixture.
mkdir -p "$tmp/workspace"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/workspace/repos.yaml"
python3 - "$tmp/legacy.sqlite3" <<'PY'
import json, sqlite3, sys
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
            "verification": ["pytest -q: pass"],
        }
    },
    "questions": [{"id": "q1", "question": "Legacy unanswered question"}],
    "decisions": [{
        "id": "d1",
        "summary": "Legacy active decision",
        "source": "user request",
        "rationale": "legacy rationale",
    }],
    "changes": [],
    "blockers": [],
    "handoffs": [{
        "id": "h1", "from": "demo", "to": "api", "status": "pending",
        "summary": "Finish API change",
    }],
    "next_actions": [{
        "action": "Coordinate remaining work", "repo": "demo", "owner": "platform",
    }],
    "checkpoints": [],
}
conn = sqlite3.connect(sys.argv[1])
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
add_artifact("investigation:2", "investigation", "Wrong tie winner", "Do not materialize", 6, "scope", "Scope", ["wrong"], "2026-01-03")
add_artifact("investigation:1", "investigation", "Investigation", "Verified finding", 5, "scope", "Scope", ["Investigated ", "legacy evidence."], "2026-01-03")
add_artifact("report:1", "report", "Final report", "Legacy report summary", 7, "root-cause", "h3. +1. Root-cause/requirement:+", ["Legacy root cause."], "2026-01-02")
conn.commit()
conn.close()
PY

python3 "$exporter" --workspace "$tmp/workspace" --db "$tmp/legacy.sqlite3"
dossier="$tmp/workspace/work-items/redmine~116655"
archive="$tmp/workspace/.qiqi/migration-backups/v0024/legacy-work-items/redmine~116655.json"
[[ -f "$dossier/00_WORK_ITEM.md" ]] || fail 'legacy exporter did not create numbered dossier'
[[ -f "$archive" ]] || fail 'legacy exporter did not preserve archive'
grep -Fxq 'legacy_reconciliation_required: true' "$dossier/00_WORK_ITEM.md" || fail 'legacy reconciliation gate missing'
grep -Fq 'Active decision d1 has legacy extension/provenance fields (rationale, source)' "$dossier/00_WORK_ITEM.md" || fail 'decision provenance reconciliation was not surfaced'
grep -Fq 'Protected legacy archive:' "$dossier/00_WORK_ITEM.md" || fail 'legacy archive locator missing'
grep -Fq 'demo -> api: Finish API change' "$dossier/00_WORK_ITEM.md" || fail 'pending handoff dropped'
grep -Fq 'demo: pytest -q: pass' "$dossier/00_WORK_ITEM.md" || fail 'repository verification dropped'
grep -Fq 'Coordinate remaining work (repo=demo, owner=platform)' "$dossier/00_WORK_ITEM.md" || fail 'next-action ownership collapsed'
grep -Fxq 'based_on_work_item_revision: 5' "$dossier/20_investigation.md" || fail 'artifact revision provenance/tie ordering drifted'
[[ "$(head -n 1 "$dossier/90_report.textile")" == 'h3. +1. Root-cause/requirement:+' ]] || fail 'Textile report heading drifted'

python3 - "$archive" <<'PY'
import json, stat, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
assert data["work_item"]["decisions"][0]["source"] == "user request"
assert data["work_item"]["decisions"][0]["rationale"] == "legacy rationale"
assert data["artifacts"][0]["sections"][0]["chunks"][0]["chunk_index"] == 0
assert stat.S_IMODE(path.stat().st_mode) == 0o600
PY

# Separator mapping remains distinct.
mkdir -p "$tmp/separator-workspace"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/separator-workspace/repos.yaml"
python3 - "$tmp/separator.sqlite3" <<'PY'
import json, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE work_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
for item_id in ("a:b--c", "a--b:c"):
    doc = {"id": item_id, "title": item_id, "status": "active", "phase": "intake", "summary": "", "current_requirements": [], "repos": {}, "questions": [], "decisions": [], "changes": [], "blockers": [], "handoffs": [], "next_actions": [], "checkpoints": []}
    conn.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)", (item_id, 1, "active", json.dumps(doc), "2026-01-01", "2026-01-01"))
conn.commit(); conn.close()
PY
python3 "$exporter" --workspace "$tmp/separator-workspace" --db "$tmp/separator.sqlite3" >/dev/null
[[ -f "$tmp/separator-workspace/work-items/a~b--c/00_WORK_ITEM.md" ]] || fail 'separator-safe key missing'
[[ -f "$tmp/separator-workspace/work-items/a--b~c/00_WORK_ITEM.md" ]] || fail 'separator-safe key missing'

# Cross-platform policy rejects casefold-equivalent keys before any write.
mkdir -p "$tmp/casefold-workspace"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/casefold-workspace/repos.yaml"
python3 - "$tmp/casefold.sqlite3" <<'PY'
import json, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE work_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
for item_id in ("redmine:ABC", "redmine:abc"):
    doc = {"id": item_id, "title": item_id, "status": "active", "phase": "intake", "summary": "", "current_requirements": [], "repos": {}, "questions": [], "decisions": [], "changes": [], "blockers": [], "handoffs": [], "next_actions": [], "checkpoints": []}
    conn.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)", (item_id, 1, "active", json.dumps(doc), "2026-01-01", "2026-01-01"))
conn.commit(); conn.close()
PY
if python3 "$exporter" --workspace "$tmp/casefold-workspace" --db "$tmp/casefold.sqlite3" >/dev/null 2>&1; then
  fail 'casefold-equivalent Work Item keys must be rejected'
fi
[[ ! -e "$tmp/casefold-workspace/work-items/redmine~ABC/00_WORK_ITEM.md" ]] || fail 'casefold collision wrote partial output'
[[ ! -e "$tmp/casefold-workspace/work-items/redmine~abc/00_WORK_ITEM.md" ]] || fail 'casefold collision wrote partial output'

# Partial artifact schema fails closed.
mkdir -p "$tmp/partial-workspace"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/partial-workspace/repos.yaml"
python3 - "$tmp/partial.sqlite3" <<'PY'
import json, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
doc = {"id": "redmine:partial", "title": "partial", "status": "active", "phase": "intake", "summary": "", "current_requirements": [], "repos": {}, "questions": [], "decisions": [], "changes": [], "blockers": [], "handoffs": [], "next_actions": [], "checkpoints": []}
conn.execute("CREATE TABLE work_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
conn.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)", ("redmine:partial", 1, "active", json.dumps(doc), "2026-01-01", "2026-01-01"))
conn.execute("CREATE TABLE work_item_artifacts (work_item_id TEXT, artifact_id TEXT, type TEXT)")
conn.commit(); conn.close()
PY
if python3 "$exporter" --workspace "$tmp/partial-workspace" --db "$tmp/partial.sqlite3" >/dev/null 2>&1; then
  fail 'incomplete legacy artifact schema must fail closed'
fi

# Missing selected DB must fail.
mkdir -p "$tmp/missing-db-workspace"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/missing-db-workspace/repos.yaml"
if python3 "$exporter" --workspace "$tmp/missing-db-workspace" --db "$tmp/does-not-exist.sqlite3" >/dev/null 2>&1; then
  fail 'missing selected legacy DB must not report success'
fi

# Conflict in a later item must not allow earlier writes.
mkdir -p "$tmp/preflight-workspace/work-items/redmine~2"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/preflight-workspace/repos.yaml"
printf 'occupied\n' > "$tmp/preflight-workspace/work-items/redmine~2/existing.txt"
python3 - "$tmp/preflight.sqlite3" <<'PY'
import json, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE work_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
for item_id in ("redmine:1", "redmine:2"):
    doc = {"id": item_id, "title": item_id, "status": "active", "phase": "uat", "summary": "", "current_requirements": [], "repos": {}, "questions": [], "decisions": [], "changes": [], "blockers": [], "handoffs": [], "next_actions": [], "checkpoints": []}
    conn.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)", (item_id, 1, "active", json.dumps(doc), "2026-01-01", "2026-01-01"))
conn.commit(); conn.close()
PY
if python3 "$exporter" --workspace "$tmp/preflight-workspace" --db "$tmp/preflight.sqlite3" >/dev/null 2>&1; then
  fail 'later conflict must fail preflight'
fi
[[ ! -e "$tmp/preflight-workspace/work-items/redmine~1/00_WORK_ITEM.md" ]] || fail 'preflight wrote earlier item'

# Installer adoption protects the complete skill tree.
bad_codex="$tmp/install-bad-codex"
bad_claude="$tmp/install-bad-claude"
mkdir -p "$bad_codex/work-item" "$bad_claude/work-item"
cp "$home/skills/work-item/SKILL.md" "$bad_codex/work-item/SKILL.md"
cp "$home/skills/work-item/SKILL.md" "$bad_claude/work-item/SKILL.md"
if bash "$home/scripts/install-user-skill.sh" --codex-root "$bad_codex" --claude-root "$bad_claude" >/dev/null 2>&1; then
  fail 'installer adopted an incomplete unmanaged skill tree'
fi

good_codex="$tmp/install-good-codex"
good_claude="$tmp/install-good-claude"
mkdir -p "$good_codex/work-item" "$good_claude/work-item"
cp -R "$home/skills/work-item/." "$good_codex/work-item/"
cp -R "$home/skills/work-item/." "$good_claude/work-item/"
bash "$home/scripts/install-user-skill.sh" --codex-root "$good_codex" --claude-root "$good_claude" >/dev/null
[[ -f "$good_codex/work-item/.agent-knowledge-harness-managed" ]] || fail 'identical Codex skill tree was not adopted'
[[ -f "$good_claude/work-item/.agent-knowledge-harness-managed" ]] || fail 'identical Claude skill tree was not adopted'

# Legacy unregister helper removes only harness-owned registrations and verifies absence.
fakebin="$tmp/fakebin"
mkdir -p "$fakebin"
for cli in codex claude; do
  cat > "$fakebin/$cli" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
state="${TMPDIR:?}/${0##*/}.state"
if [[ "$1 $2 $3" == "mcp get work_item" ]]; then
  [[ -f "$state" ]] || exit 1
  printf 'command: /tmp/agent-work-item-mcp\n'
  exit 0
fi
if [[ "$1 $2 $3" == "mcp remove work_item" ]]; then
  rm -f "$state"
  exit 0
fi
exit 64
SH
  chmod +x "$fakebin/$cli"
  : > "$tmp/$cli.state"
done
PATH="$fakebin:$PATH" TMPDIR="$tmp" bash "$home/scripts/remove-legacy-user-mcp.sh" >/dev/null
[[ ! -e "$tmp/codex.state" && ! -e "$tmp/claude.state" ]] || fail 'legacy MCP registration removal was not verified'

printf 'Work Item filesystem template: OK\n'
