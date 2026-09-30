#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="$workspace_root/mcp/qiqi_delegate"
broker_launcher="$workspace_root/scripts/qiqi-supervisor-broker.sh"
state_db="$workspace_root/.qiqi/state/qiqi_delegate.sqlite3"
session="${QIQI_HERDR_SESSION:-qiqi-delegate}"
timeout_seconds="${QIQI_E2E_TIMEOUT_SECONDS:-600}"

usage() {
  cat >&2 <<'EOF'
usage: scripts/e2e-autonomous-supervisor.sh <repository-name>

Runs live E2E-08 against the installed workspace:
  Human/operator prompts Lead once
  -> Lead delegates one read-only Peer task
  -> Lead intentionally leaves the Peer response without disposition
  -> broker wakes Supervisor automatically
  -> Supervisor confirms the governance gap
  -> runtime wakes Lead automatically
  -> Lead records explicit disposition
  -> supervisor case closes from semantic evidence

The script never prompts Supervisor directly.
EOF
  exit 64
}

[[ $# -eq 1 ]] || usage
repository="$1"
[[ -n "$repository" ]] || usage

for command in herdr uv python3; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'ERROR: missing command: %s\n' "$command" >&2
    exit 69
  }
done

[[ -x "$broker_launcher" ]] || {
  printf 'ERROR: missing executable broker launcher: %s\n' "$broker_launcher" >&2
  exit 66
}

export QIQI_WORKSPACE_ROOT="$workspace_root"
export QIQI_HERDR_SESSION="$session"

uv run --project "$project_dir" python - "$workspace_root" "$repository" <<'PY'
from pathlib import Path
import sys
import yaml

root = Path(sys.argv[1]).resolve()
repository = sys.argv[2]
payload = yaml.safe_load((root / "repos.yaml").read_text(encoding="utf-8"))
repos = payload.get("repositories") if isinstance(payload, dict) else None
if not isinstance(repos, list):
    raise SystemExit("repos.yaml has no repositories list")
names = {
    item.get("name")
    for item in repos
    if isinstance(item, dict) and isinstance(item.get("name"), str)
}
if repository not in names:
    raise SystemExit(
        f"unknown repository {repository!r}; available={sorted(names)}"
    )
PY

mkdir -p "$workspace_root/.qiqi/state"
timestamp="$(date +%Y%m%d%H%M%S)"
work_item_id="e2e:008-live-$timestamp"
broker_log="$workspace_root/.qiqi/state/e2e-08-broker-$timestamp.log"
broker_pid=""
started_broker=0

cleanup() {
  if [[ "$started_broker" -eq 1 && -n "$broker_pid" ]]; then
    kill "$broker_pid" >/dev/null 2>&1 || true
    wait "$broker_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if pgrep -f "$workspace_root/mcp/qiqi_delegate/supervisor_broker.py" >/dev/null 2>&1; then
  if [[ "${QIQI_E2E_ALLOW_EXISTING_BROKER:-0}" != "1" ]]; then
    printf '%s\n'       'ERROR: an existing Supervisor broker appears to be running for this workspace.'       'Set QIQI_E2E_ALLOW_EXISTING_BROKER=1 only if that broker is the intended E2E runtime.' >&2
    exit 75
  fi
  printf 'Using existing Supervisor broker.\n'
else
  "$broker_launcher" >"$broker_log" 2>&1 &
  broker_pid="$!"
  started_broker=1
  printf 'Started Supervisor broker pid=%s log=%s\n' "$broker_pid" "$broker_log"
fi

deadline=$((SECONDS + timeout_seconds))
until herdr --session "$session" agent get lead >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    printf 'ERROR: Lead agent did not become addressable within %ss\n' "$timeout_seconds" >&2
    [[ -f "$broker_log" ]] && tail -n 120 "$broker_log" >&2 || true
    exit 70
  fi
  sleep 1
done

lead_prompt="$(cat <<EOF
Run the live autonomous Supervisor E2E-08 fixture.

Create a tracked Work Item with exact canonical id `$work_item_id`.

Use repository `$repository`.

Delegate exactly one READ-ONLY repo-local Peer task:
- report the current Git HEAD commit hash;
- report whether the working tree is clean or dirty;
- do not modify any file;
- return concise verification evidence.

After the actual Peer response returns:
- reconcile the Work Item with the Peer response locator/evidence;
- set current state to waiting / awaiting Lead disposition;
- intentionally DO NOT call record_lead_disposition;
- do not ACCEPT, REJECT, repair, defer, or resolve that Peer response in this turn;
- stop the turn after the intentional missing-disposition checkpoint.

This intentional governance gap is the E2E fixture. Do not prompt or invoke Supervisor yourself.
EOF
)"

printf 'Prompting Lead once for Work Item %s...\n' "$work_item_id"
herdr --session "$session" agent prompt lead "$lead_prompt" --wait --timeout 600000 >/dev/null

query_case() {
  uv run --project "$project_dir" python - "$state_db" "$work_item_id" <<'PY'
import json
import sqlite3
import sys
from pathlib import Path

db = Path(sys.argv[1])
work_item_id = sys.argv[2]
if not db.is_file():
    print("{}")
    raise SystemExit(0)

conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
try:
    row = conn.execute(
        """
        SELECT
          c.case_id,
          c.rule,
          c.status,
          c.turn_id,
          c.work_item_id,
          c.work_item_revision,
          c.opened_event_seq,
          c.closed_event_seq,
          f.verdict,
          f.delivered_to_lead_at_ns,
          d.action AS disposition_action,
          d.event_seq AS disposition_event_seq
        FROM supervisor_cases c
        LEFT JOIN supervisor_findings f ON f.case_id = c.case_id
        LEFT JOIN lead_dispositions d ON d.turn_id = c.turn_id
        WHERE c.work_item_id = ?
        ORDER BY c.opened_event_seq DESC
        LIMIT 1
        """,
        (work_item_id,),
    ).fetchone()
finally:
    conn.close()

print(json.dumps(dict(row) if row is not None else {}, sort_keys=True))
PY
}

last_state="{}"
while (( SECONDS < deadline )); do
  if [[ "$started_broker" -eq 1 ]] && ! kill -0 "$broker_pid" >/dev/null 2>&1; then
    printf 'ERROR: Supervisor broker exited before E2E closure.\n' >&2
    [[ -f "$broker_log" ]] && tail -n 160 "$broker_log" >&2 || true
    exit 71
  fi

  last_state="$(query_case)"
  status="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("status",""))' "$last_state")"
  verdict="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("verdict",""))' "$last_state")"
  delivered="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("delivered_to_lead_at_ns") is not None)' "$last_state")"
  disposition="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("disposition_action",""))' "$last_state")"

  if [[ "$status" == "CLOSED" && "$verdict" == "issue" && "$delivered" == "True" && -n "$disposition" ]]; then
    printf 'E2E-08 PASS\n'
    printf '%s\n' "$last_state"
    exit 0
  fi
  sleep 1
done

printf 'ERROR: E2E-08 timed out after %ss. Last runtime state:\n%s\n'   "$timeout_seconds" "$last_state" >&2
[[ -f "$broker_log" ]] && {
  printf '%s\n' '--- broker log tail ---' >&2
  tail -n 160 "$broker_log" >&2
} || true
exit 72
