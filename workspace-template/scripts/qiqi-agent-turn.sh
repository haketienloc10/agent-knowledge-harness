#!/usr/bin/env bash
set -euo pipefail

# QiQi synchronous turn contract
# ------------------------------
# This wrapper owns exactly one delegated agent turn from prompt submission until
# terminal completion. These rules are operating constraints, not suggestions.
#
# Normal flow:
#   1. Invoke `prompt` as a foreground operation.
#   2. Remain blocked until THIS SAME invocation reaches terminal completion.
#   3. Reconcile the returned final result.
#   4. Only then may QiQi create another delegated turn.
#
# IMPORTANT — transport backgrounding does NOT release the lifecycle lock:
# Codex/the tool runner may move a long-running foreground command into a UI area
# named "Background terminals". That is transport behavior only. The turn is
# still active and QiQi is still logically blocked until this same wrapper
# invocation emits QIQI_AGENT_TURN_FINISHED.
#
# The flock below is GLOBAL for this QiQi runtime, not per agent. A second turn
# or resume operation for any agent must fail BUSY while this invocation owns the
# lifecycle. This hard-enforces the one-active-delegated-operation policy.
#
# While this invocation is active QiQi MUST NOT issue another tool, shell or
# session-observation command to inspect or advance the turn. In particular:
#   - no `/ps` or equivalent background-terminal inspection;
#   - no `herdr agent wait`, `herdr agent get`, or `herdr agent read`;
#   - no `herdr pane read`, `herdr pane process-info`, or `herdr pane wait-output`;
#   - no sleep/poll/status loop and no second qiqi-agent-turn invocation;
#   - no background, detach, nohup, disown, or fire-and-forget wrapper execution;
#   - no direct `herdr agent prompt`; prompt submission goes through this wrapper.
#
# If QIQI_AGENT_TURN_BUSY is returned, another lifecycle owner already exists.
# Do not retry, poll, or create a replacement waiter. Reconcile according to
# workspace AGENTS.md only after the existing owner has terminally ended.
#
# QIQI_AGENT_TURN_FINISHED means this wrapper turn reached terminal completion.
# It does NOT by itself mean the overall user task is complete.
#
# There is intentionally NO `wait` mode in this wrapper. Recovery after a real
# wrapper/session error is a separate exceptional workflow governed by AGENTS.md.

usage() {
  cat >&2 <<'EOF'
Usage:
  qiqi-agent-turn.sh prompt <agent>  # synchronous; stdin prompt; one turn only
EOF
  exit 64
}

[[ "$#" -eq 2 ]] || usage

mode="$1"
agent="$2"

[[ "$mode" == "prompt" ]] || usage

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

lock_file="$runtime_dir/qiqi.lifecycle.lock"
exec 9>"$lock_file"

if ! flock -n 9; then
  printf 'QIQI_AGENT_TURN_BUSY agent=%s\n' "$agent" >&2
  exit 75
fi

finish() {
  local rc=$?
  trap - EXIT
  if [[ "$rc" -eq 0 ]]; then
    printf 'QIQI_AGENT_TURN_FINISHED agent=%s status=success\n' "$agent" >&2
  else
    printf 'QIQI_AGENT_TURN_FINISHED agent=%s status=error exit=%s\n' \
      "$agent" "$rc" >&2
  fi
  exit "$rc"
}
trap finish EXIT

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
  [[ -z "$prompt_output" ]] || printf '%s\n' "$prompt_output" >&2
  exit "$prompt_rc"
fi
