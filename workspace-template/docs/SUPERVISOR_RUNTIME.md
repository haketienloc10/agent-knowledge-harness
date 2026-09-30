# Autonomous SLP Supervisor Runtime

This document describes the runtime implemented by issue #97 phases 1–3.

## Runtime topology

```text
Herdr named session: qiqi-delegate

workspace: slp-control
├── lead        # persistent technical Lead at workspace root
└── supervisor  # persistent governance agent in isolated control cwd
```

The Lead and Supervisor are independent Herdr agents. Supervisor is not a child of Lead.

## Sources of truth

```text
work-items/                         current product-task truth
repo source/tests                   implementation truth
.qiqi/state/qiqi_delegate.sqlite3   runtime/session + SLP semantic truth
Herdr events                        transient wakeup/lifecycle transport only
```

Herdr lifecycle/status events are never used to infer technical acceptance, Work Item state,
Peer response semantics, or case closure.

## Durable semantic loop

```text
Peer response
  -> slp_events
  -> deterministic Supervisor Broker
  -> supervisor_cases
  -> bounded AuditPacket
  -> persistent Supervisor
  -> issue | no_issue finding
  -> issue only: Herdr agent prompt -> persistent Lead
  -> new SLP semantic event
  -> evidence-driven case closure
```

A finding, prompt delivery, Lead acknowledgement, agent state, or passing tests does not close
a case. Closure is driven by the semantic event store.

## AuditPacket boundary

Supervisor receives the smallest sufficient governance packet:

- case id and rule;
- Work Item id + revision when present;
- Lead-brief locator by captured turn id;
- Peer-response locator by captured turn id;
- current disposition state;
- candidate identity when present;
- deterministic rule facts.

The packet intentionally does not contain raw Peer responses, TaskPacket bodies, transcripts,
terminal output, source trees, or Work Item filesystem paths.

## Supervisor response boundary

Supervisor must return exactly:

```json
{
  "case_id": "...",
  "status": "issue",
  "observation": "...",
  "evidence": ["..."],
  "open_question_for_lead": "...?"
}
```

or `status=no_issue` with `open_question_for_lead=null`.

Runtime validation rejects extra fields, including action/decision/delegation/patch/tool-call
fields. Supervisor output is persisted as structured governance evidence, not as technical
authority.

## Runtime authority controls

Lead runs at the actual workspace root and keeps the normal QiQi project configuration.

Supervisor runs from an isolated state directory outside the project tree by default:

```text
$XDG_STATE_HOME/qiqi-supervisor/<workspace-hash>/
```

or `~/.local/state/qiqi-supervisor/<workspace-hash>/`.

The location can be overridden with `QIQI_SUPERVISOR_HOME`.

Supervisor is launched with:

```text
sandbox = read-only
approval policy = never
```

and does not start from the project root, so project-local qiqi_delegate MCP configuration is not
part of its control surface.

This is a runtime capability boundary and defense-in-depth policy. It is not an OS/container
security claim against a malicious local process with independent host access.

## Phase 4 semantic integration

The runtime now emits/records the semantic inputs consumed by the deterministic broker:

- tracked TaskPacket observation records `work_item.revision_changed` idempotently;
- canonical Work Item mutation must call `record_work_item_revision` immediately;
- direct Peer signals are recorded with `record_peer_signal`;
- direct downstream consumption uses `record_dependency_consumed`;
- TaskGraph downstream execution automatically records each accepted upstream dependency turn;
- every direct/TaskGraph repository delegation uses the existing repository ownership lock and
  emits conservative `write_scope.claimed/released` events with scope `["*"]`;
- explicit Lead `accept` also emits `candidate.accepted`.

The current `["*"]` claim mirrors the actual qiqi_delegate same-repository serialization
boundary. It is intentionally conservative and does not replace Lead's finer-grained write-scope
planning.

## Herdr wakeup contract

The broker uses raw `events.subscribe` only as a wakeup stream. On startup, reconnect, topology
change, or event loss, it replays durable SLP events from the SQLite cursor.

Supervisor responses are captured through the native Stop hook. The broker does not use
`pane.read` or `agent.read` as semantic input.

Confirmed Supervisor findings are delivered to Lead with Herdr `agent prompt` without treating
prompt acknowledgement as completion.

## Operations

Start the autonomous broker:

```bash
scripts/qiqi-supervisor-broker.sh
```

Process one full autonomous cycle and exit:

```bash
scripts/qiqi-supervisor-broker.sh --supervise-once
```

Process only durable deterministic rules without starting control-plane agents:

```bash
scripts/qiqi-supervisor-broker.sh --once
```

The broker must remain running for continuous supervision. If it is absent or unhealthy, the
workspace must not claim continuous supervision.

CI includes an autonomous E2E-08 state-machine integration test that proves broker case opening,
Supervisor review, Lead wakeup, explicit Lead disposition, and semantic case closure without a
Human relay. A real installed workspace must still run the live Herdr E2E-08 operator scenario
before the deployment claims continuous supervision for that environment.
