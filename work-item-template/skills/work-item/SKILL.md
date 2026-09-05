---
name: work-item
description: >
  Operational protocol for Global Work Item MCP on the QiQi/orchestration side.
  Apply when a canonical Work Item has already been selected or identified, when
  the user explicitly asks to create/use a Work Item, or before QiQi calls any
  `work_item_*` tool. Do not make Work Item a repository-child execution dependency.
---

# Global Work Item Operational Protocol

Global Work Item MCP is the **canonical mutable product-task state owned by the
QiQi/orchestration layer**. Repository execution agents receive an immutable,
semantically self-sufficient TaskPacket and do not need Work Item ID/revision or
`work_item_get`/`work_item_update` to understand or complete repo-local work.

## Activation boundary

- Apply this skill when a canonical Work Item is already identified/selected.
- Apply when the user explicitly asks QiQi to create or use a Work Item.
- Apply before any QiQi `work_item_*` call in the current turn.
- Do **not** create/select a Work Item merely because a prompt contains a ticket,
  bug report, incident, pasted task, or generic coding request.
- Do **not** put Work Item identity/revision into child-facing TaskPacket semantics.

If Work Item MCP is unavailable for an ongoing canonical task, do not reconstruct
canonical truth from conversation memory or create a local Markdown fallback.

## Canonical truth boundary

```text
Global Work Item MCP   = mutable product-task truth (QiQi side)
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
TaskPacket              = immutable delegated-turn task semantics
```

Work Item is not an activity transcript, reusable Knowledge store, source-code truth,
runtime/session store, or child execution-context dependency.

## Read or create

### Existing Work Item

Before an orchestration/planning/status/completion decision that depends on a Work Item:

1. `work_item_get(id)`.
2. Treat returned `revision` + bounded current-state projection as latest canonical state.
3. `work_item_history_read(...)` only when exact provenance/history is material.
4. Reconcile user/product/Knowledge/native-child evidence against current canonical state.
5. Build repo-local TaskPacket from the **current material semantics**, not from a Work
   Item reference that child must dereference.

History cursors are bound to Work Item id, whole revision, collection and filters. If
revision changes between pages, restart; never mix pages from two revisions.

### Explicit new Work Item

1. Determine stable canonical ID only when source + external ID are unambiguous.
2. `work_item_get(id)` first so repeated intake does not reset an existing task.
3. If found, reconcile genuinely new source material.
4. If not found and creation is authorized, `work_item_create(...)` from material
   current facts/requirements only.
5. Do not promote unsupported hypotheses/comments into verified decisions.

## Update mechanics

Every update uses one typed `WorkItemMutation` plus optimistic concurrency:

```text
work_item_get -> latest revision/current state
→ build current-state patch + smallest grouped semantic mutations
→ work_item_update(id, expected_revision, mutation)
→ revision conflict: reread → reconcile → retry
```

`mutation.state` contains current effective fields only:

```text
title / status / phase / summary
current_requirements
repos
next_actions
```

`mutation.operations` is a grouped typed object:

```text
decision_upsert[]
question_upsert[]
change_upsert[]
blocker_upsert[]
handoff_upsert[]
checkpoint_append[]
```

There is no `{op,value}` envelope. Omit unused groups. At most 50 semantic records total
may be sent per call. All groups build one final candidate and commit all-or-nothing
under one exact Work Item revision. Stale writers conflict; server does not auto-rebase.

Stable-id lifecycle records advance monotonically. Existing identity/provenance is not
silently rewritten. Checkpoints are append-only.

Successful update returns a compact receipt; reread `work_item_get` only when the next
QiQi decision needs resulting current state.

## TaskPacket delegation boundary

QiQi must distill a **smallest sufficient repo-local problem contract** before delegation.

Child-facing TaskPacket contains:

```text
objective                    required
scope[]                      required
acceptance_criteria[]        required
out_of_scope[]?              optional
context.trusted_facts[]?     {fact, source}
context.claims_to_investigate[]? {claim, source}
constraints[]?               optional
known_unknowns[]?            optional
```

It does **not** contain normal child-facing:

```text
user_request
work_item_id / work_item_revision
verification command
Work Item phase/status/global next_actions
QiQi bookkeeping identifiers
```

Material semantics must survive distillation even when original wording/history is
removed. If child would need Work Item dereference to understand objective, boundaries,
premises or acceptance, the TaskPacket is incomplete.

## Immutable snapshot and stale handling

A TaskPacket is an immutable semantic snapshot for one delegated turn. Child does not
chase mutable Work Item state after START.

When canonical state changes while child runs, QiQi evaluates materiality:

- non-material change: child may settle; reconcile result against latest truth;
- material change: the stale execution result **MUST NOT become current truth**.

QiQi chooses cancel/interrupt/resume/redelegate/reconcile according to runtime capability.
The required outcome is stale-result containment, not a specific interrupt mechanism.

## Native child response reconciliation

Runtime state (`settled`, `failed`, `blocked`, session/turn lifecycle) is execution
lifecycle truth only. It is **not semantic completion truth**.

After a native child response returns:

1. Read the exact/native response completely.
2. Reread latest Work Item when a dependent orchestration/completion decision needs
   current canonical truth.
3. Reconcile evidence against TaskPacket acceptance + latest requirements/decisions.
4. Persist Work Item facts/checkpoints/blockers/handoffs/next actions within QiQi authority.
5. Decide semantic completion, next wave, RESUME/redelegate, or user question.

Do not add a second child-authored semantic status such as `completed | partial | blocked`.
QiQi is the semantic interpreter/reconciliation layer.

## Current snapshot vs material history

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

If a fresh QiQi session cannot continue from current snapshot fields, repair current
state rather than depending on default history hydration.

## Questions, decisions, changes, blockers, handoffs

Use semantic fields only for material meaning:

- `questions[]`: external/product ambiguity lifecycle;
- `decisions[]`: material decisions explaining current task interpretation;
- `changes[]`: requirement/scope evolution;
- `blockers[]`: conditions materially preventing progress;
- `handoffs[]`: explicit remaining work transferred to another repo/owner;
- `next_actions[]`: current continuation actions.

When a user/customer answer resolves a material question, prefer one atomic grouped
mutation for related decision/question/change/current-requirement effects.

## Artifact boundary

Artifacts are optional detailed material derived from an exact Work Item revision.

- Create only when user/workflow explicitly requires intake, investigation, plan,
  review or report detail.
- Artifact writes have independent artifact revision and do not advance Work Item state.
- Current Work Item state wins if historical artifact conflicts with newer canonical state.
- Artifact creation/finalization does not replace canonical Work Item reconciliation.

## Before final QiQi response

For a substantive canonical-task turn:

1. Ensure dependent decisions used latest relevant bounded Work Item state.
2. Read scoped history only when exact provenance is materially needed.
3. Reconcile returned repo evidence into canonical state within QiQi authority.
4. Persist semantic lifecycle changes with smallest grouped operations.
5. On revision conflict, reread/reconcile/retry; do not assume server rebase.
6. Treat mutation receipt as commit confirmation, not refreshed snapshot.
7. If persistence fails, report it; do not claim canonical state contains missing data.
8. Apply separate Shared Knowledge review/write rules for reusable conclusions.
