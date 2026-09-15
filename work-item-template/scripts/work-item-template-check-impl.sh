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
  'Multi-turn continuity MUST be represented as \*\*current semantic state\*\*' \
  'Requirement change không tự invalidate prior findings' \
  'work_item=<id>; revision=<revision>' \
  'Không tạo mặc định history/turn/execution/checkpoint files' \
  'report.textile'; do
  rg -q "$pattern" "$skill" || fail "skill missing contract: $pattern"
done

if rg -q 'work_item_get|work_item_update|work_item_history_read|Global Work Item MCP|WORK_ITEM_DB_PATH' "$home/README.md" "$home/ARTIFACTS.md" "$skill"; then
  fail 'legacy MCP/SQLite Work Item contract remains in current docs'
fi

bash -n "$home/scripts/install-user-skill.sh"
printf 'Work Item filesystem template: OK\n'
