# Autonomous SLP Supervisor Runtime

This document describes the runtime implemented by issue #97 phases 1–3.

## Runtime topology

```text
Herdr named session: qiqi-delegate-<workspace-hash> by default

workspace: slp-control
├── lead        # persistent technical Lead at workspace root
└── supervisor  # persistent governance agent in isolated control cwd
```

The Lead and Supervisor are independent Herdr agents. Supervisor is not a child of Lead.

The persistent control-plane default model for both agents is `gpt-5.6-luna`.
The persisted control-plane identity includes Herdr session + Lead model + Supervisor model; if
that identity changes, the runtime closes the stale `slp-control` workspace and recreates the
agents instead of silently reusing sessions launched with an older model.

Persisted Herdr topology is also validated before reuse. If the saved workspace or either
saved pane no longer exists (for example after a Herdr restart or manual workspace close), the
runtime clears the stale control-plane row and recreates `slp-control` automatically. A missing
persisted pane must not require operator cleanup. Prompt-ready named agents are reused only when
their reported Herdr pane matches the persisted control-plane pane; a same-name agent on another
pane fails closed instead of receiving Lead/Supervisor traffic.

Initial control-plane creation persists the provisional workspace/pane topology before fixed-name
agents start. If startup later fails, the runtime closes that provisional workspace and clears the
row only after Herdr confirms cleanup. If cleanup itself fails, the provisional row remains durable
so the next retry can recover or close the exact workspace instead of losing the only locator for
orphaned fixed-name agents.


## Sources of truth

```text
work-items/                         current product-task truth
repo source/tests                   implementation truth
.qiqi/state/qiqi_delegate.sqlite3   runtime/session + SLP semantic truth
Herdr events                        transient wakeup/lifecycle transport only
```

Herdr lifecycle/status events are never used to infer technical acceptance, Work Item state,
Peer response semantics, or case closure.

## Supervision epoch

`supervisor_broker_state.supervision_floor_seq` is a durable, immutable lower bound for semantic
history owned by continuous Supervisor governance.

On first broker enablement, the broker records the current `slp_events` tail as both the initial
cursor and the supervision floor. Therefore an established workspace can enable SLP without
retroactively auditing hundreds or thousands of historical Peer turns. A workspace that starts the
broker before any work naturally gets floor `0` and supervises all subsequent events.

When an older workspace upgrades to the floor-aware schema, existing broker state is baselined at
the current semantic tail. Any already-open R5 case whose source `peer.response` is at or below
that floor is administratively closed before further review/delivery. The semantic ledger and
historical turns are preserved; only continuous governance scope changes.

The floor never moves during ordinary broker restart. `last_processed_seq` remains the moving
replay cursor, while `supervision_floor_seq` remains the epoch boundary.

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
- normative `rule_contract` for the exact deterministic R1-R5 predicate and its bounded
  `issue_when` facts;
- Work Item id + revision when present;
- Lead-brief locator by captured turn id;
- Peer-response locator by captured turn id;
- current disposition state, hydrated from `lead_dispositions` for the exact Peer turn when one exists;
- candidate identity when present;
- deterministic rule facts.

The packet intentionally does not contain raw Peer responses, TaskPacket bodies, transcripts,
terminal output, source trees, or Work Item filesystem paths.

Rule ids are not opaque to the Supervisor. The packet carries the deterministic meaning:

- R1: actual Peer response exists without an explicit Lead disposition for that exact turn;
- R2: downstream dependency was consumed before explicit ACCEPT of the upstream Peer turn; the
  case/audit locators attach to that upstream source turn while consumer identity remains supporting
  governance context;
- R3: active writable ownership claims overlap in the same repository; the packet includes bounded
  exact overlap pairs so the Supervisor can evaluate the normative predicate without repo access;
- R4: REOPEN_REQUEST / DEPENDENCY_REQUEST / BLOCKED remains unresolved;
- R5: every unreconciled Peer response after the durable `supervision_floor_seq` that belongs to
  an older material Work Item revision gets a stale-candidate case. One unresolved stale turn has
  at most one active R5 case; a later Work Item revision does not duplicate that review. After the
  case is explicitly reconciled/closed, a still-live candidate may become stale again on a later
  material revision. A terminal superseded/abandoned reconciliation is not reopened.

Supervisor evaluates the bounded packet against that exact contract. It must not reinterpret a
rule from perceived severity, implementation quality, or technical outcome. A prior disposition
on an older revision does not by itself make an R5 candidate current.

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
- Work Item `revision` changes only for a material requirement/acceptance/scope change; state,
  phase, evidence, disposition, report reconciliation, waiting, or done transitions do not bump it;
- after an actual material revision change, canonical Work Item mutation must call
  `record_work_item_revision` immediately;
- direct Peer signals are recorded with `record_peer_signal`; bounded signal details are carried
  into R4 governance facts without copying the raw Peer response. A deferred explicit signal later
  closes through `record_peer_signal_resolution` for that exact turn + signal, preserving the
  historical `defer` disposition;
- a native runtime-blocked R4 case is tied to its exact native session and closes when that same
  session later produces a captured Peer response; explicit semantic BLOCKED signals still require
  normal Lead reconciliation;
- direct downstream consumption uses `record_dependency_consumed`;
- TaskGraph downstream execution records dependency consumption at dispatch, before final-response
  transport can fail;
- an R2 consume-before-ACCEPT case is historical and is not erased by a later ACCEPT. After Lead
  has explicitly remediated the affected downstream premise, it records
  `record_dependency_consumption_resolution(consumption_event_seq, reason)` for the exact
  violating consumption event; that separate event closes the case while preserving history;
- every direct/TaskGraph repository delegation uses the existing repository ownership lock and
  emits conservative `write_scope.claimed/released` events with scope `["*"]`. Pre-dispatch
  failures release a claim because no Peer workspace was started. After dispatch, the durable claim
  is released only when Herdr workspace shutdown is confirmed; if shutdown fails or the process
  crashes, the claim remains active and subsequent writers fail closed. After an operator/Lead
  verifies the old writer is terminated or intentionally abandoned,
  `release_write_scope_claim(claim_id, repository, reason)` records an explicit recovery release
  instead of auto-expiring ownership. If a semantic Peer result was already captured and persisted
  before cleanup failed, delegation still returns that exact result plus durable recovery locators.
  Unconfirmed workspace shutdown returns `cleanup_state=workspace_close_unconfirmed`; a confirmed
  shutdown whose `write_scope.released` persistence fails returns
  `cleanup_state=write_claim_release_unconfirmed`. Both include the durable `write_claim_id`,
  `write_claim_repository`, workspace locator, and recovery action; neither cleanup failure
  discards the candidate or turns it into an executor exception;
- explicit Lead `accept` also emits `candidate.accepted`; any explicit Work Item id/revision
  passed with a disposition must exactly match the canonical locator captured in that turn's
  TaskPacket or the write fails closed;
- pre-semantic-ledger workspaces are upgraded idempotently: any canonical row already present in
  `turns` but missing its `peer.response` ledger event is backfilled exactly once for durable
  historical provenance. First Supervisor enablement baselines at the current semantic tail, so
  those pre-epoch rows are not retroactively replayed as new R1/R5 governance work;
- TaskGraph `replan` / `block` decisions require explicit `owner` and
  `return_checkpoint`; both are persisted in the exact Lead disposition reason;
- R5 stale candidates do not close merely because another current-revision Peer response appears.
  R5 only considers Peer responses strictly after `supervision_floor_seq`, and later Work Item
  revisions coalesce onto the same active R5 case for an unresolved stale turn instead of opening
  repeated reviews. Lead records exact stale-candidate reconciliation with
  `record_candidate_reconciliation`, which emits `candidate.reconciled` without rewriting the
  stale turn's historical disposition.

The current `["*"]` claim mirrors the actual qiqi_delegate same-repository serialization
boundary. It is intentionally conservative and does not replace Lead's finer-grained write-scope
planning.

## Herdr wakeup contract

The broker uses raw `events.subscribe` only as a wakeup stream. On startup/reconnect it first
drains durable SQLite truth, opens the Herdr subscription, waits for the explicit
`subscription_started` acknowledgement, then performs a second full durable drain before waiting
for lifecycle wakeups. This closes the commit-to-subscribe race: any wakeup created during the
second drain is already buffered by the active subscription. Topology change or event loss causes
reconnect and the same durable replay sequence. A transient Supervisor/control-plane failure is
isolated from other cases and retried with backoff; each retry failure is written to stderr and
persisted in `supervisor_broker_state` as `health_status=retrying` with the latest error/time.
A completed full durable drain clears the error and marks the broker `healthy`.

Supervisor responses are captured through the native Stop hook. The broker does not use
`pane.read` or `agent.read` as semantic input.

Confirmed Supervisor findings are delivered to Lead with Herdr `agent prompt` without treating
prompt acknowledgement as completion. Immediately before each Lead wakeup, the runtime replays
durable semantic events again, then writes a short SQLite delivery reservation under
`BEGIN IMMEDIATE`. Reservation succeeds only when the broker cursor has consumed the latest durable
semantic sequence and the case remains deliverable. The transaction commits before Herdr is called,
so Lead can write semantic evidence while handling the wakeup. A closure committed before
reservation therefore suppresses the obsolete wakeup; a closure committed afterward is durably
ordered after notification selection. Undelivered reservations are cleared when the broker
singleton runtime restarts, so a crash between reservation and transport does not strand delivery.
R2 wakeups carry the exact `consumption_event_seq` in the deterministic runtime locator. R3
wakeups likewise carry the exact repository and every overlapping durable `write_claim_id`. Lead
therefore does not have to rely on model-authored evidence text to recover the keys required by
`record_dependency_consumption_resolution` or `release_write_scope_claim`.

## Operations

Start the autonomous broker:

```bash
bash scripts/qiqi-supervisor-broker.sh
```

Process one full autonomous drain and exit (all bounded event/review/delivery batches are drained,
not just one batch):

```bash
bash scripts/qiqi-supervisor-broker.sh --supervise-once
```

Process only durable deterministic rules without starting control-plane agents:

```bash
bash scripts/qiqi-supervisor-broker.sh --once
```

The broker must remain running for continuous supervision. The Python broker entrypoint takes a
non-blocking process-lifetime file lock derived from the exact state DB
(`qiqi_delegate.sqlite3.supervisor-broker.lock` by default); a second broker for the same DB exits
instead of allowing duplicate Supervisor/Lead prompts. This also protects direct Python invocation,
not only the shell launcher. If the broker is absent or unhealthy, the workspace
must not claim continuous supervision.

CI includes an autonomous E2E-08 state-machine integration test that proves broker case opening,
Supervisor review, Lead wakeup, explicit Lead disposition, and semantic case closure without a
Human relay.

A real installed workspace must also run the live Herdr scenario before that environment claims
continuous supervision:

```bash
bash scripts/e2e-autonomous-supervisor.sh <repository-name>
```

The live script prompts Lead once with a read-only Peer fixture and never prompts Supervisor.
Unless `QIQI_HERDR_SESSION` is explicitly supplied, it derives the same
`qiqi-delegate-<workspace-hash>` session as the production broker so the installed-workspace gate
exercises workspace isolation rather than a legacy global session. The fixture has no requirement
change, so its initial Work Item revision remains stable while
status/evidence move through waiting, Lead disposition, and done. It passes only when persisted
evidence shows an `issue` finding was delivered to Lead and the case later reached `CLOSED`
through an explicit `lead_disposition`. The chosen repository
must already be registered in `repos.yaml`, and native Herdr/Codex/QiQi integrations must be
healthy.
