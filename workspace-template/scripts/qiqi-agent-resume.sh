#!/usr/bin/env bash
set -euo pipefail

# QiQi resume contract
# --------------------
# Resume is a lifecycle operation and shares the SAME GLOBAL lock as
# qiqi-agent-turn.sh. It must not run while any delegated turn or another resume
# operation is active.
#
# If the tool runner displays this invocation under "Background terminals", that
# does not release the lifecycle lock. QiQi must wait for this same invocation to
# terminally finish and must not inspect/poll the session in parallel.

usage() {
  cat >&2 <<'EOF'
Usage:
  qiqi-agent-resume.sh \
    --name <agent> \
    --pane <pane-id> \
    --kind <agent-kind> \
    -- <native-resume-arguments...>
EOF
  exit 64
}

name=""
pane=""
kind=""

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --name)
      [[ "$#" -ge 2 ]] || usage
      name="$2"
      shift 2
      ;;
    --pane)
      [[ "$#" -ge 2 ]] || usage
      pane="$2"
      shift 2
      ;;
    --kind)
      [[ "$#" -ge 2 ]] || usage
      kind="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      usage
      ;;
  esac
done

[[ -n "$name" && -n "$pane" && -n "$kind" ]] || usage
[[ "$#" -gt 0 ]] || {
  printf 'ERROR: native resume arguments must not be empty\n' >&2
  exit 64
}

if [[ ! "$name" =~ ^[a-z][a-z0-9_-]{0,31}$ ]]; then
  printf 'ERROR: invalid agent name: %s\n' "$name" >&2
  exit 64
fi

if [[ "${HERDR_ENV:-}" != "1" ]]; then
  printf 'ERROR: QiQi must run inside a managed pane (HERDR_ENV=1)\n' >&2
  exit 69
fi

command -v herdr >/dev/null 2>&1 || {
  printf 'ERROR: missing command: herdr\n' >&2
  exit 69
}

command -v flock >/dev/null 2>&1 || {
  printf 'ERROR: missing command: flock\n' >&2
  exit 69
}

runtime_base="${XDG_RUNTIME_DIR:-/tmp}"
runtime_dir="$runtime_base/qiqi-agent-turn-${UID}"
mkdir -p "$runtime_dir"
chmod 700 "$runtime_dir"

lock_file="$runtime_dir/qiqi.lifecycle.lock"
exec 9>"$lock_file"

if ! flock -n 9; then
  printf 'QIQI_AGENT_RESUME_BUSY agent=%s\n' "$name" >&2
  exit 75
fi

finish() {
  local rc=$?
  trap - EXIT
  if [[ "$rc" -eq 0 ]]; then
    printf 'QIQI_AGENT_RESUME_FINISHED agent=%s status=success\n' \
      "$name" >&2
  else
    printf 'QIQI_AGENT_RESUME_FINISHED agent=%s status=error exit=%s\n' \
      "$name" "$rc" >&2
  fi
  exit "$rc"
}
trap finish EXIT

herdr agent start "$name" --kind "$kind" --pane "$pane" -- "$@"
