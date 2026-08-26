---
name: ticket-work-item
description: >
  Explicit entry point for processing a real ticket as a canonical Global Work Item.
  Use only when the user explicitly invokes `$ticket-work-item` or explicitly asks to
  use the ticket Work Item workflow. Do not auto-apply merely because a prompt contains
  a ticket, bug report, Redmine issue, Jira issue, GitHub issue, incident, or pasted task.
---

# Ticket Work Item Entry Point

Treat the text supplied with this invocation as the original ticket input.

This skill is only an explicit entry point. The workspace `AGENTS.md` remains the
canonical policy for Work Item ownership, QiQi orchestration, repository delegation,
Shared Knowledge, native result handoff, revision conflict handling, and completion.
Do not duplicate or weaken those rules here.

## Start

1. Determine the canonical Work Item ID from the ticket when possible.
2. Prefer an explicit ID supplied by the user. Otherwise infer a stable source ID such
   as `redmine:<number>`, `jira:<key>`, or `github:<owner>/<repo>#<number>` only when
   the source and identifier are unambiguous.
3. If a reliable canonical ID cannot be determined, ask only for the missing ticket ID
   before creating persistent Work Item state.
4. Call `work_item_get` for the canonical ID.
5. If the Work Item exists, continue from its latest canonical revision; do not rebuild
   task truth from conversation memory.
6. If it does not exist, create it from the material ticket information, then continue
   from the created canonical document.

## Interpret the ticket

Separate material information into:

- current effective requirements;
- incident evidence or facts already supported by supplied evidence;
- hypotheses, comments, proposed fixes, or suggestions not yet verified;
- open questions;
- active decisions that are actually settled;
- requirement or scope changes when effective scope changed.

Do not promote an AI-generated analysis, proposed solution, ticket comment, historical
assumption, or plausible root-cause theory into a verified fact or decision without
supporting evidence.

Preserve the original ticket meaning, constraints, acceptance expectations, and
material provenance.

## Choose the next useful work

Follow the latest Work Item plus workspace `AGENTS.md` and choose the next useful phase
from evidence. A common path is:

```text
investigation → planning → implementation → unit test → IT/UAT → rework/reverify
```

This is descriptive, not a strict state machine. Move backward or repeat phases when
new evidence requires it.

Investigate before implementation when root cause, ownership, scope, compatibility, or
solution correctness is not sufficiently established. Do not implement a ticket's
suggested fix merely because it is written in the ticket.

## Orchestration

QiQi owns workspace-level orchestration and overall Work Item state according to
`AGENTS.md`.

For repository-local work:

1. Identify the responsible repository using workspace topology and available evidence.
2. Delegate through `delegate_repo_task` with the canonical Work Item identity and
   revision in `required_context`.
3. Require the repository agent to read the latest Work Item before substantive work.
4. Let the repository agent establish conclusions from current-repo source/test/runtime
   evidence and update only the task state it has authority to establish.
5. After delegation returns, read the full native response and reread the latest Work
   Item before deciding the next step.

A child agent does not become a cross-repository orchestrator. If it discovers work in
another repository, persist a Work Item handoff with material evidence and let QiQi
choose and delegate the consumer repository.

## Questions and decisions

If an external or product ambiguity cannot be resolved from the canonical Work Item,
allowed durable knowledge, or owner-repository evidence:

1. persist a material open question in the Work Item;
2. record what it affects and whether it blocks work;
3. ask the user/customer only for the unresolved decision.

When an answer arrives, reconcile the canonical state rather than keeping the answer
only in conversation:

- resolve the question;
- create/update the active decision when appropriate;
- reconcile `current_requirements`;
- add a requirement/scope change when effective requirements actually changed;
- update blockers and next actions atomically where practical.

Supersede historical decisions instead of silently rewriting their provenance.

## Persist material continuation state

Use exact `expected_revision` and update only material task continuity such as:

- `current_requirements`;
- `questions`;
- `decisions`;
- `changes`;
- repository progress and verification evidence;
- `blockers`;
- `handoffs`;
- `checkpoints`;
- `next_actions`;
- overall summary/status/phase when QiQi owns the change.

Do not use the Work Item as a command transcript, activity log, or hidden-reasoning
store.

On revision conflict:

```text
reread → reconcile → retry
```

Never silently overwrite newer canonical task state.

## Shared Knowledge boundary

Task-specific mutable state stays in the Work Item. Reusable, verified conclusions that
matter beyond the ticket may use Shared Knowledge according to workspace policy.

When Shared Knowledge is relevant, follow the current progressive-disclosure flow:

```text
knowledge_search → knowledge_read → knowledge_write
```

Do not store ticket progress, temporary blockers, ticket Q&A, or next actions as Shared
Knowledge.

## Completion and user report

Do not mark a Work Item done merely because code changed. Completion requires sufficient
evidence that the current effective requirements are satisfied and relevant verification
is complete.

At meaningful stopping points, report concisely:

- current conclusion;
- main evidence;
- Work Item status/phase;
- blocker or open question, if any;
- next action.

Normal Work Item bookkeeping should remain QiQi's responsibility; do not make the user
manually maintain canonical fields that QiQi can reconcile itself.
