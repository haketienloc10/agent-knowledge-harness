---
name: work-item-investigate
description: >
  Investigation scoping and clarification gate for a tracked Work Item. Use with
  $work-item when ownership, repository/module boundaries, authoritative sources or
  the first investigation target are uncertain, without asking the user for facts the agent can discover.
---

# Work Item investigation clarification

Use this skill when intake is sufficiently clear but the **investigation target or boundary** is not.

It is conditional. Do not run a clarification ceremony when the target, ownership and required evidence are already obvious from the current Work Item and repository context.

This skill scopes investigation; it does not replace `investigation.md` or the actual investigation.

## Core rule

Prefer **discovery over user questioning** for factual uncertainty.

Do not ask the user which repository/module/class owns a behavior when `repos.yaml`, source, tests, documentation, runtime configuration or existing Work Item evidence can establish it.

Ask the user only when investigation reaches a genuine product/domain ambiguity where multiple technically plausible behaviors remain and the repository cannot establish intended semantics.

## Clarification targets

Resolve or explicitly classify:

- symptom / behavior to trace;
- authoritative source of truth;
- repository/module/service ownership;
- investigation boundary;
- evidence needed to distinguish competing explanations;
- cross-repository dependency that materially changes scope;
- assumptions inherited from intake that require factual validation.

## Required assessment

### Known

State the minimum relevant facts already established.

### Unknowns to discover

List factual or technical unknowns the agent can investigate without user input.

### Proposed investigation target

Identify the best first boundary/entry point and why it is informative.

### Discovery path

Give a bounded sequence such as:

1. trace the relevant entry point;
2. identify authoritative ownership/data flow;
3. verify the observed behavior against tests/config/docs;
4. stop and reconcile scope if ownership crosses a new material boundary.

Do not expand into a full implementation plan.

### User decision needed

List only unresolved product/domain choices that cannot be established from authoritative evidence. Use `none` when no user decision is needed.

### Gate

Return exactly one:

- `ready` — investigation target/boundary is clear enough to proceed or the investigation conclusion is sufficient for planning.
- `needs_user_clarification` — evidence exposes a material product/domain ambiguity requiring user intent.
- `needs_discovery` — more factual/repository/evidence work is required and the agent can perform it without a user decision.
- `blocked` — a required source/system/dependency is inaccessible and prevents meaningful investigation.

## Boundary changes

When discovery identifies another repo/module:

- do not treat the new boundary as a requirement change by itself;
- update investigation scope when it is necessary to answer the existing requirement;
- return to intake only if the discovered boundary changes product scope, acceptance or user-visible behavior.

## Persistence boundary

Do not create clarification files or chronological investigation notes.

Return material scope/findings/questions to `$work-item`. QiQi reconciles them into `investigation.md` and `WORK_ITEM.md` as living current state. Preserve evidence/provenance only when it remains necessary to support a current finding or future acceptance assessment.
