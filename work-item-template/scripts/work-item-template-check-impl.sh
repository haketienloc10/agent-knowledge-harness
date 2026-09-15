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
  'verify nó vẫn nằm dưới resolved `<workspace>/work-items`' \
  'Không tạo mặc định history/turn/execution/checkpoint files' \
  'report.textile'; do
  grep -Fq -- "$pattern" "$skill" || fail "skill missing contract: $pattern"
done

exporter="$home/scripts/export-legacy-work-items.py"
for pattern in \
  'WORK_ITEM_ID_RE = re.compile' \
  'VALID_PHASES = {' \
  'LEGACY_PHASE_ALIASES = {' \
  'return "investigation", raw or None' \
  'source, external_id = item_id.split(":", 1)' \
  'return f"{source}--{external_id}"' \
  'target.resolve().relative_to(root.resolve())' \
  'build_export_plan' \
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
    "repos": {"demo": {"status": "active", "summary": "Investigating"}},
    "questions": [],
    "decisions": [],
    "changes": [],
    "blockers": [],
    "handoffs": [],
    "next_actions": [{"action": "Continue investigation", "repo": "demo"}],
    "checkpoints": [],
}
conn = sqlite3.connect(path)
conn.execute("CREATE TABLE work_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
conn.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)", ("redmine:116655", 7, "active", json.dumps(doc), "2026-01-01", "2026-01-02"))
conn.commit()
conn.close()
PY
python3 "$exporter" --workspace "$tmp/workspace" --db "$tmp/legacy.sqlite3"
[[ -f "$tmp/workspace/work-items/redmine--116655/WORK_ITEM.md" ]] || fail 'legacy exporter did not create safe dossier'
[[ -f "$tmp/workspace/.qiqi/migration-backups/v0024/legacy-work-items/redmine--116655.json" ]] || fail 'legacy exporter did not preserve full archive'
[[ -f "$tmp/legacy.sqlite3" ]] || fail 'legacy exporter modified/deleted source DB'
grep -Fq 'Preserve legacy requirement' "$tmp/workspace/work-items/redmine--116655/WORK_ITEM.md" || fail 'legacy requirement was not exported'
grep -Fxq 'phase: investigation' "$tmp/workspace/work-items/redmine--116655/WORK_ITEM.md" || fail 'unknown legacy phase was not normalized to a valid filesystem phase'
grep -Fxq 'legacy_phase: "review: security"' "$tmp/workspace/work-items/redmine--116655/WORK_ITEM.md" || fail 'raw legacy phase was not preserved safely'

# Preflight must detect a conflict in a later item before writing any earlier item.
mkdir -p "$tmp/preflight-workspace/work-items/redmine--2"
printf 'repositories:\n  - name: demo\n    path: demo\n' > "$tmp/preflight-workspace/repos.yaml"
printf 'occupied\n' > "$tmp/preflight-workspace/work-items/redmine--2/existing.txt"
python3 - "$tmp/preflight.sqlite3" <<'PY'
import json, sqlite3, sys
path = sys.argv[1]
conn = sqlite3.connect(path)
conn.execute("CREATE TABLE work_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, document_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
for item_id in ("redmine:1", "redmine:2"):
    doc = {
        "id": item_id,
        "title": item_id,
        "status": "active",
        "phase": "uat",
        "summary": "legacy",
        "current_requirements": [],
        "repos": {},
        "questions": [],
        "decisions": [],
        "changes": [],
        "blockers": [],
        "handoffs": [],
        "next_actions": [],
        "checkpoints": [],
    }
    conn.execute("INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?)", (item_id, 1, "active", json.dumps(doc), "2026-01-01", "2026-01-01"))
conn.commit()
conn.close()
PY
if python3 "$exporter" --workspace "$tmp/preflight-workspace" --db "$tmp/preflight.sqlite3" >/dev/null 2>&1; then
  fail 'legacy exporter must fail preflight when a later target conflicts'
fi
[[ ! -e "$tmp/preflight-workspace/work-items/redmine--1/WORK_ITEM.md" ]] || fail 'legacy exporter wrote earlier items before completing preflight'

printf 'Work Item filesystem template: OK\n'
