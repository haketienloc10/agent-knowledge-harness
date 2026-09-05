---
name: work-item
description: >
  Operational protocol for Global Work Item MCP on the QiQi/orchestration side.
  Apply when a canonical Work Item is selected/identified, when the user asks to
  create/use one, or before any QiQi `work_item_*` call. Do not make Work Item a repository-child execution dependency.
---

# Global Work Item Operational Protocol

Global Work Item MCP is canonical mutable product-task truth on the QiQi/orchestration side.
Repository children receive immutable, semantically self-sufficient TaskPackets and do
not need Work Item identity/revision.

## Activation

- Apply when a canonical Work Item is selected/identified, when the user explicitly
  requests create/use, and before any QiQi `work_item_*` call.
- Generic tickets/bugs/incidents do not automatically become Work Items.
- Never put Work Item ID/revision into child-facing TaskPacket semantics.
- If MCP is unavailable for an ongoing canonical task, do not reconstruct canonical
  truth from conversation memory or local Markdown.

## Common low-churn path

For a normal single-repo task with an exact canonical ID:

```text
work_item_get(id)
→ if absent: work_item_create(...)
→ delegate from that exact snapshot/revision
→ reconcile exact native child response
→ work_item_update(expected_revision=<delegated revision>, mutation=...)
→ on revision conflict: reread → reconcile → retry
```

Fast-path rules:

- Exact ID known → do **not** call `work_item_list` before `work_item_get(id)`.
- A successful `work_item_create` response is the authoritative current snapshot and
  revision for an immediately dependent delegation; do not immediately reread it.
- Preserve the exact revision that produced the delegated TaskPacket.
- After child return, prefer optimistic CAS: build the candidate reconciliation from
  immutable TaskPacket + exact native response and call `work_item_update` with that
  delegated `expected_revision`.
- Update success proves the canonical revision stayed unchanged through commit.
- Revision conflict means stale risk: get latest state, evaluate materiality, reconcile,
  then retry only if still valid.
- Reread first only when the dependent decision is not guarded by that same revisioned
  mutation, when no mutation will be attempted, or after conflict.
- Read history only when exact provenance is material.

This preserves stale-result containment without redundant reads.

## Current state, history, update

`work_item_get(id)` returns bounded current state + whole revision.
`work_item_history_read(...)` is only for material exact provenance. History cursors
bind ID + exact revision + collection + filters; revision change between pages means
restart, never mix revisions.

Every write uses one typed `WorkItemMutation` with optimistic concurrency.

`mutation.state` current fields:

```text
title / status / phase / summary / current_requirements / repos / next_actions
```

`mutation.operations` optional groups:

```text
decision_upsert[]
question_upsert[]
change_upsert[]
blocker_upsert[]
handoff_upsert[]
checkpoint_append[]
```

At most 50 semantic records total may be sent per call. Groups form one final candidate
and commit all-or-nothing under one exact revision. Server does not auto-rebase.
Successful update returns a compact receipt; reread only if a later decision needs a
fresh snapshot. Stable lifecycle IDs advance monotonically; checkpoints are append-only.
Do not reconstruct/resend untouched history.

## TaskPacket delegation boundary

QiQi distills the smallest sufficient repo-local problem contract.

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

Material semantics must survive distillation. If child would need Work Item dereference
to reconstruct objective/scope/product decisions/premises/constraints/acceptance, the
TaskPacket is incomplete.

## Immutable snapshot and native result

TaskPacket is an immutable semantic snapshot for one delegated turn; child does not
chase mutable Work Item state after START.

Runtime state (`settled`, `failed`, `blocked`, session/turn lifecycle) is execution
lifecycle truth only. It is **not semantic completion truth**. QiQi reads the complete
native response; QiQi is the semantic interpreter/reconciliation layer.

A materially stale execution result **must not become current truth**. Prefer the
delegated-revision CAS fast path in the uncontended case; conflict forces latest-state
reconciliation before promotion. Do not add a second child-authored semantic status
such as `completed | partial | blocked`.

## Semantic records and artifacts

Use questions/decisions/changes/blockers/handoffs/next_actions only for material
meaning. Prefer one atomic grouped mutation when one answer changes related fields.

Artifacts are optional detail from an exact Work Item revision, only when user/workflow
requires detailed intake/investigation/plan/review/report material. Artifact revisions
are independent and current Work Item state wins over stale artifacts. Artifact creation/finalization does not replace canonical Work Item reconciliation.

## Shared Knowledge boundary

Work Item state is not Shared Knowledge. Only reusable verified conclusions (stable
invariant, contract, ownership/diagnostic rule, recurring operational behavior) are
durable candidates.

Routine repo-specific completion, a one-off code fix, or ordinary test-pass evidence
does **not** by itself require Shared Knowledge review. Do not read `$knowledge-distill`
or call `knowledge_write(entries=[])` merely to record such a review. Use Knowledge
policy only when a plausible reusable conclusion exists or a higher-level workflow
explicitly requires durable review.

## Before final QiQi response

1. Reconcile exact native response against immutable TaskPacket.
2. Persist required canonical state with the smallest grouped revisioned mutation.
3. Prefer delegated-revision CAS; on revision conflict: reread → reconcile → retry.
4. If no revisioned write guards a dependent completion decision, read latest bounded
   state before claiming current completion.
5. Read history only for material provenance.
6. Treat compact receipt as commit confirmation, not refreshed snapshot.
7. If persistence fails, report it; do not claim missing data is canonical.
8. Apply separate Shared Knowledge rules only for reusable conclusions or explicitly
   required durable review.
