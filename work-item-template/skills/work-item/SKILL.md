---
name: work-item
description: >
  Operational protocol for Global Work Item MCP. Apply when a canonical Work Item has
  already been selected or identified, when the user explicitly asks to create/use a
  Work Item, or before calling any `work_item_*` tool. Do not decide that a generic
  ticket, bug report, incident, or coding task should become a Work Item.
---

# Global Work Item Operational Protocol

This skill contains the **on-demand read/write/reconciliation protocol** for Global
Work Item MCP. Role authority still comes from the active `AGENTS.md`; this skill must
not widen QiQi or repository-agent authority.

## Activation boundary

Global Work Item remains explicit opt-in task state.

- Apply this skill when a canonical Work Item is already identified/selected.
- Apply this skill when the user explicitly asks to create or use a Work Item.
- Apply this skill before any `work_item_*` tool call in the current turn.
- Do **not** create/select a Work Item merely because a prompt contains a Redmine/Jira/
  GitHub issue, bug report, incident, pasted task, or generic coding request.
- If role policy does not authorize creation, do not create one; hand the decision back
  to the authorized orchestrator/user.

If Work Item MCP is unavailable for an ongoing canonical Work Item, do not reconstruct
canonical task truth from conversation memory or create a local Markdown fallback.

## Canonical truth boundary

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

Work Item is not an activity transcript, reusable Knowledge store, source-code truth,
or runtime/session store.

## Read or create

### Existing Work Item

Before substantive planning, implementation, review, status, handoff, RESUME/START
follow-up, or completion decision that depends on a Work Item:

1. `work_item_get(id)`.
2. Treat the returned `revision` plus bounded current-state projection as the latest
   canonical decision state; do not expect resolved/superseded/checkpoint history in
   the default read.
3. Reconcile any supplied TaskPacket/user context against that current state before acting.
4. Call `work_item_history_read(...)` only when exact provenance/history is material to
   the current decision. Mutation no longer requires hydrating a full historical array.
5. If current Work Item conflicts with a required premise, stop the dependent action
   and surface/reconcile the conflict according to role authority.

`work_item_history_read` reads exactly one semantic collection per call. Its cursor is
opaque and bound to Work Item id, whole Work Item revision, collection, and filters. If
the Work Item changes between pages, restart the history read from the current revision;
never mix pages from two revisions.

### Explicit new Work Item

Create only after explicit user/orchestrator selection of the Work Item workflow.

1. Determine a stable canonical ID only when source + external ID are unambiguous.
2. Call `work_item_get(id)` first so repeated intake does not reset an existing task.
3. If found, continue from the existing current-state projection and reconcile genuinely
   new source material; read scoped history only if the current decision needs it.
4. If not found and creation is within role authority, `work_item_create(...)` from
   material current facts/requirements only.
5. Do not promote unsupported hypotheses, suggested fixes, or ticket comments into
   verified facts/decisions.

If a stable ID is required but cannot be determined safely, ask only for the missing
identity instead of inventing one.

## Update mechanics

Every Work Item update uses one typed `WorkItemMutation` plus optimistic concurrency:

```text
work_item_get -> latest revision/current state
→ build current-state patch + smallest grouped semantic mutations
→ work_item_update(id, expected_revision, mutation)
→ revision conflict: reread → reconcile → retry
```

A mutation has two separate roles:

```text
mutation.state
  = current effective fields only

mutation.operations
  = grouped typed mutation of semantic lifecycle/history records
```

Either branch may be omitted when unused. Do not send an empty `state` object merely as
boilerplate.

### Current-state patch

`mutation.state` may patch only:

```text
title / status / phase / summary
current_requirements
repos
next_actions
```

Rules:

- Nested repository objects merge by supplied fields.
- `current_requirements` and `next_actions` are bounded current-state arrays; these
  arrays replace atomically.
- Explicit `null` keeps JSON merge-patch deletion semantics for state fields where the
  canonical model permits it; omitted fields mean no change.
- Historical semantic collections are intentionally **not** public full-array replacement
  fields in `mutation.state`.

### Grouped semantic operations

`mutation.operations` is a typed object whose field names are the operation meaning
itself. There is **no `op` discriminator and no `value` wrapper**:

```json
{
  "operations": {
    "blocker_upsert": [
      {"id": "b1", "status": "resolved"}
    ],
    "checkpoint_append": [
      {"repo": "backend", "summary": "Focused verification passed."}
    ]
  }
}
```

Available groups:

```text
decision_upsert[]
question_upsert[]
change_upsert[]
blocker_upsert[]
handoff_upsert[]
checkpoint_append[]
```

Use only groups needed by the material change; omit empty groups. The declared MCP schema
for each group exposes its record fields directly, so construct a valid mutation from the
schema instead of probing it with intentionally incomplete/invalid `work_item_update`
calls.

Rules:

- At most 50 semantic records total may be sent across all groups in one call.
- All groups commit all-or-nothing under one whole Work Item revision and build one final
  candidate document.
- Cross-group ordering is **not** part of the public contract. Cross-record references are
  validated against the final candidate, so related decision/question transitions may be
  grouped in the same atomic call without relying on heterogeneous caller order.
- List order inside a group is preserved where canonical ordering matters, including
  checkpoint append order.
- Do not target the same stable-id record twice in one mutation; reconcile it into one
  deterministic record mutation.
- A stale writer always conflicts, even when it targets a different collection/record.
  The server never auto-rebases semantic mutations.
- Existing stable-id records keep semantic identity/provenance. Upsert means create or
  monotonic lifecycle advance, not arbitrary historical rewrite.
- Existing provenance/evidence extensions are additive: do not silently replace an
  established value.

Lifecycle contract:

```text
question:  open -> resolved                 # resolved never reopens
decision:  active -> superseded             # superseded never reactivates
blocker:   open -> resolved                 # recurring blocker gets a new id
handoff:   pending -> resolved              # recurring handoff gets a new id

change:
  proposed -> accepted | rejected | superseded
  accepted -> superseded
  rejected/superseded are terminal
```

Identity/provenance rules:

- `questions[].question` is immutable after create. Resolution may add write-once
  `answer` and/or `decision_id`.
- `decisions[].summary` is immutable after create. Supersession adds write-once
  `superseded_by`.
- `changes[].type` and `changes[].summary` are immutable after create.
- `blockers[].summary` is immutable after create.
- `handoffs[].from`, `handoffs[].to`, and `handoffs[].summary` are immutable after create.
- `checkpoints[]` is append-only through `checkpoint_append`; there is no checkpoint
  upsert/rewrite operation.

If a historical statement was wrong or later changed, add the proper new semantic record
or lifecycle transition rather than rewriting provenance.

### Compact mutation receipt

A successful `work_item_update` returns only a bounded receipt such as:

```json
{
  "updated": true,
  "id": "redmine:116655",
  "revision": 42,
  "changed": ["repos.backend", "decisions:d7", "questions:q3", "checkpoints"]
}
```

The receipt is confirmation of the committed mutation, not a new snapshot. Reread
`work_item_get(id)` only when the next decision actually needs resulting current state.
Do not expect mutation success to hydrate the full Work Item document.

## Current snapshot vs material history

Keep these roles stable across sessions:

```text
work_item_get:
  summary / repos / verification / status / phase / current_requirements / next_actions
  open_questions / active_decisions / open_blockers / pending_handoffs
    = bounded current effective decision state

work_item_history_read:
  questions / decisions / changes / checkpoints / blockers / handoffs
    = exact scoped canonical history/provenance

artifact
  = optional detailed material; never a replacement for Work Item reconciliation
```

`work_item_get.history` is deterministic metadata/counts only. It is not a prose summary
and does not return checkpoint records. If a fresh session cannot continue from
`summary`, `repos[repo].summary`, current requirements, and current lifecycle state,
repair those current snapshots rather than depending on default history hydration.

### Repository summary

`repos[repo].summary` is the **current effective repo truth after all work known so
far**: implemented outcome, verified boundary, and remaining repo work when material.
It is not a narrative of the latest review/investigation/report/session or command log.

### Verification

`repos[repo].verification` contains concrete verification evidence currently established
for that repository. Update it when verification materially changes; do not fill it with
plans or unexecuted checks.

### Checkpoints

`checkpoints[]` is accumulated material phase/milestone history. It is not returned by
`work_item_get`; read it through `work_item_history_read(collection="checkpoints", ...)`
only when provenance is materially needed.

Append a checkpoint when a substantive session establishes a new milestone that a future
reader needs to reconstruct major task progression. Checkpoint metadata may include:

```text
kind        = optional free-form descriptive milestone label
artifact_id = optional detailed artifact reference
```

Useful `kind` examples: `investigation`, `implementation`, `verification`, `review`,
`decision`, `report`, `completion`. `kind` is descriptive only, not an enum/FSM.

Do not create command-by-command, test-by-test, or session transcript checkpoints.

## Material session reconciliation

Every substantive Work Item session that establishes material task state must leave
canonical continuation state **before final**. Artifact creation never substitutes for
this reconciliation.

Generic mapping:

| Session | Canonical effect when material |
|---|---|
| Investigation | current repo truth + checkpoint + question/blocker when needed |
| Planning | next action/handoff within authority + checkpoint when plan becomes continuation state |
| Implementation | current implemented repo truth + checkpoint; artifact not required |
| Verification | repository verification + checkpoint; summary/status only if conclusion changes |
| Review | review artifact when workflow requests it + checkpoint; preserve current implementation truth |
| Decision | persist decision/question/requirement effects within role authority |
| Report | report artifact when workflow requests it + checkpoint; preserve prior repo/history truth |
| Completion | final effective summary/status/checkpoint only within global completion authority |

### Implementation guardrail

Implementation **must reconcile the Work Item even when no artifact is created**.
Persist current implemented outcome and verification through `mutation.state`; append one
material implementation checkpoint through `mutation.operations.checkpoint_append` when a
new milestone was established. Do not read/resend historical checkpoints for this common
path.

### Review guardrail

Review detail belongs in a review artifact when the workflow requires one; material
review findings belong in checkpoints. Change `repos[repo].summary` only when review
actually changes current effective repo truth (for example, a resulting code/test fix or
new verified boundary). If review merely confirms current implementation, preserve the
implementation-oriented summary instead of replacing it with `Review code...` narrative.

### Report guardrail

A report artifact is presentation/detail. Preserve implementation/review checkpoints and
current repo truth. Global summary/status/phase/next-action reconciliation remains owned
by the role authorized for overall task orchestration.

Investigation, planning, and verification use the same generic snapshot/history boundary;
do not introduce a hard workflow machine or event log.

## Questions, decisions, changes, blockers, handoffs

Use semantic fields only for their intended material meaning:

- `questions[]`: external/product ambiguity lifecycle, not generic notes.
- `decisions[]`: material decisions explaining current task interpretation/behavior.
- `changes[]`: requirement/scope evolution only, not implementation progress.
- `blockers[]`: conditions materially preventing progress.
- `handoffs[]`: explicit remaining work transferred to another repo/owner.
- `next_actions[]`: concrete current continuation actions with repo/owner target.

Default `work_item_get` exposes only `open_questions`, `active_decisions`,
`open_blockers`, and `pending_handoffs`. Resolved/superseded lifecycle records remain
canonical and audit-readable through scoped history.

When a user/customer answer resolves a material question and the current role owns the
reconciliation, prefer one atomic grouped mutation:

```text
operations.decision_upsert = [new active decision, old decision -> superseded if needed]
operations.question_upsert = [open question -> resolved]
operations.change_upsert   = [effective requirement/scope change when one occurred]
operations.blocker_upsert / handoff_upsert when applicable
state.current_requirements / next_actions when current state changed
```

Because references validate on the final candidate document, the new decision and the
question/decision transitions may be in the same call without depending on cross-group
execution order.

A repository execution agent does not use these mechanics to exceed current-repo
authority; product/customer decisions and global orchestration remain with QiQi when
role policy says so.

## Artifact boundary

Artifacts are optional detailed material derived from an exact Work Item revision.

- Create artifacts only when the user/workflow explicitly requires intake,
  investigation, plan, review, or report detail.
- Normal implementation/progress bookkeeping does not require an artifact.
- Artifact writes have independent artifact revision and must not advance Work Item
  revision/state.
- Current Work Item state wins if a historical artifact conflicts with newer canonical
  state.
- Finalizing/creating an artifact does not satisfy material-session Work Item update.

Follow artifact MCP bounds/cursor/revision contracts exposed by the tool schema.

## Role application

Always obey the active `AGENTS.md` authority boundary.

### QiQi/orchestrator

Operationally, QiQi normally owns overall `status`, `phase`, `summary`, repo assignment,
global `next_actions`, product/customer decision reconciliation, cross-repo coordination,
and final completion. After repo delegation returns, reread the bounded current Work
Item snapshot before a dependent orchestration decision when returned evidence may have
changed canonical state. Read scoped history only when that decision needs provenance.
Do not silently assume repo persistence succeeded when returned material evidence is
absent from canonical state.

### Repository execution agent

Operationally, a repo agent may establish only current-repo truth/evidence plus material
repo-local checkpoint, blocker/question, and handoff allowed by its role policy. It does
not mark sibling repos done, mark overall Work Item done, or rewrite global state merely
to reflect local progress.

## Before final

For a substantive turn with a canonical Work Item:

1. Ensure decisions/actions used the latest relevant bounded Work Item state.
2. Read scoped history only when exact provenance is materially needed.
3. Persist current effective fields through `mutation.state` within role authority.
4. Persist semantic lifecycle/history changes with the smallest direct groups under
   `mutation.operations`; never reconstruct or resend a historical collection for a local
   record change, and never probe the schema by submitting intentionally invalid mutations.
5. Add/update verification and append one material checkpoint when applicable.
6. Persist blocker/question/handoff/next action when materially required.
7. If a revision conflict occurs, reread current state, reconcile the intended mutation,
   and retry; do not expect server-side rebase.
8. Treat the compact mutation receipt as commit confirmation, not as a refreshed snapshot.
9. Do not treat artifact creation as the canonical-state update.
10. If persistence failed, report that failure; do not claim the Work Item contains the
    missing state.

Work Item handling does not replace separate Shared Knowledge review/write rules when a
reusable conclusion was established.
