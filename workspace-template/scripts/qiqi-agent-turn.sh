#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  qiqi-agent-turn.sh prompt <agent>  # read prompt from stdin
  qiqi-agent-turn.sh wait <agent>
EOF
  exit 64
}

[[ "$#" -eq 2 ]] || usage

mode="$1"
agent="$2"

case "$mode" in
  prompt | wait) ;;
  *) usage ;;
esac

if [[ ! "$agent" =~ ^[a-z][a-z0-9_-]{0,31}$ ]]; then
  printf 'ERROR: invalid agent name: %s\n' "$agent" >&2
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

lock_file="$runtime_dir/${agent}.lock"
exec 9>"$lock_file"

if ! flock -n 9; then
  printf 'QIQI_AGENT_TURN_BUSY agent=%s\n' "$agent" >&2
  exit 75
fi

finish() {
  local rc=$?
  trap - EXIT
  if [[ "$rc" -eq 0 ]]; then
    printf 'QIQI_AGENT_TURN_FINISHED agent=%s mode=%s status=success\n' \
      "$agent" "$mode" >&2
  else
    printf 'QIQI_AGENT_TURN_FINISHED agent=%s mode=%s status=error exit=%s\n' \
      "$agent" "$mode" "$rc" >&2
  fi
  exit "$rc"
}
trap finish EXIT

case "$mode" in
  prompt)
    prompt="$(cat)"
    if [[ -z "${prompt//[[:space:]]/}" ]]; then
      printf 'ERROR: prompt must not be empty\n' >&2
      exit 64
    fi

    prompt_output=""
    if prompt_output="$(herdr agent prompt "$agent" "$prompt" --wait 2>&1)"; then
      [[ -z "$prompt_output" ]] || printf '%s\n' "$prompt_output"
    else
      prompt_rc=$?
      if [[ "$prompt_output" =~ \"code\"[[:space:]]*:[[:space:]]*\"agent_prompt_stalled\" ]]; then
        herdr agent prompt "$agent" "$prompt" --wait
      else
        [[ -z "$prompt_output" ]] || printf '%s\n' "$prompt_output" >&2
        exit "$prompt_rc"
      fi
    fi
    ;;
  wait)
    herdr agent wait "$agent"
    ;;
esac
