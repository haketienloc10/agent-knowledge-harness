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
4. Call `work_item_history_read(...)` only when provenance/history is material to the
   current decision or when a full historical-array replacement requires the complete
   canonical collection.
5. If current Work Item conflicts with a required premise, stop the dependent action
   and surface/reconcile the conflict according to role authority.

`work_item_history_read` reads exactly one semantic collection per call. Its cursor is
opaque and bound to the whole Work Item revision, collection, and filters. If the Work
Item changes between pages, restart the history read from the current revision; never
mix pages from two revisions.

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

Every Work Item update uses optimistic concurrency:

```text
work_item_get -> latest revision/current state
→ read scoped complete history collection when a historical full-array replacement is needed
→ reconcile intended state
→ work_item_update(id, expected_revision, changes)
→ revision conflict: reread current snapshot/history as needed → reconcile → retry
```

Rules:

- Never silently last-write-wins over a newer revision.
- Nested repository objects merge by supplied fields.
- `current_requirements` and `next_actions` are current snapshot arrays and replace atomically.
- Historical semantic arrays (`questions`, `decisions`, `changes`, `blockers`, `handoffs`,
  `checkpoints`) also replace atomically until incremental mutation operations are available.
  **Never reconstruct them from `work_item_get`**, because its lifecycle fields are bounded
  subsets. Read the complete target collection through `work_item_history_read` first.
- Preserve every canonical array entry not intentionally removed.
- Explicit `null` is JSON merge-patch deletion; omitted fields mean no change.
- Do not patch immutable/derived fields such as `id`, `revision`, or `artifacts`.
- Unexpected/store failures are not evidence that a write succeeded.

Use the typed semantic shapes exposed by `WorkItemPatch`; do not encode status markers
inside strings or use semantic arrays as free-form notes. Canonical questions and
decisions require explicit lifecycle `status`; legacy missing statuses are migrated once
into explicit `open`/`active` state rather than remaining implicit runtime semantics.

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
when provenance or a full checkpoint-array replacement is actually needed.

Preserve existing material checkpoints and append a checkpoint when a substantive
session establishes a new milestone that a future reader needs to reconstruct major task
progression.

Checkpoint metadata may include:

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
| Investigation | current repo truth if understanding changes + checkpoint + question/blocker when needed |
| Planning | next action/handoff within authority + checkpoint when plan becomes continuation state |
| Implementation | current implemented repo truth + checkpoint; artifact not required |
| Verification | repository verification + checkpoint; summary/status only if conclusion changes |
| Review | review artifact when workflow requests it + checkpoint; preserve current implementation truth |
| Decision | persist decision/requirement effects within role authority |
| Report | report artifact when workflow requests it + checkpoint; preserve prior repo/history truth |
| Completion | final effective summary/status/checkpoint only within global completion authority |

### Implementation guardrail

Implementation **must reconcile the Work Item even when no artifact is created**.
Persist the current implemented outcome, relevant repo status/verification, and a
material implementation checkpoint when a new implementation milestone was established.
If checkpoint history must be replaced through the current update contract, hydrate the
complete checkpoint collection first via `work_item_history_read`.

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
- `next_actions[]`: concrete continuation actions with repo/owner target.

Default `work_item_get` exposes only `open_questions`, `active_decisions`,
`open_blockers`, and `pending_handoffs`. Resolved/superseded lifecycle records remain
canonical and audit-readable through scoped history.

When a user/customer answer resolves a material question and the current role owns the
reconciliation:

```text
read complete questions/decisions collection when replacement is required
→ question resolved
→ decision active when appropriate
→ current_requirements reconciled if semantics changed
→ changes[] appended if effective requirement/scope actually changed
→ blockers/next_actions reconciled where applicable
```

Supersede historical decisions rather than silently rewriting their provenance.

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
Item snapshot before a dependent orchestration decision. Read scoped history only when
that decision needs provenance or a historical collection must be replaced. Do not
silently assume repo persistence succeeded when returned material evidence is absent
from canonical state.

### Repository execution agent

Operationally, a repo agent may establish only current-repo truth/evidence plus material
repo-local checkpoint, blocker/question, and handoff allowed by its role policy. It does
not mark sibling repos done, mark overall Work Item done, or rewrite global state merely
to reflect local progress.

## Before final

For a substantive turn with a canonical Work Item:

1. Ensure decisions/actions used the latest bounded current Work Item state.
2. Read only the scoped history needed for provenance or an exact full-array replacement.
3. Persist material state established by this turn within role authority.
4. Preserve canonical atomic-array entries not intentionally removed; never derive a
   historical replacement from bounded lifecycle subsets.
5. Add/update verification and one material checkpoint when applicable.
6. Persist blocker/question/handoff/next action when materially required.
7. If a revision conflict occurs, restart any stale history pagination, reread/reconcile,
   and retry before claiming persistence.
8. Do not treat artifact creation as the canonical-state update.
9. If persistence failed, report that failure; do not claim the Work Item contains the
   missing state.

Work Item handling does not replace separate Shared Knowledge review/write rules when a
reusable conclusion was established.