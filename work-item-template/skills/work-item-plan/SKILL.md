---
name: work-item-plan
description: >
  Planning decision gate for a tracked Work Item. Use with $work-item when the
  implementation approach, affected boundaries, trade-offs, risks or verification
  strategy are materially non-obvious and must be made explicit before implementation.
---

# Work Item planning decision gate

Use this skill after investigation when implementation should not begin until the current approach and material decisions are explicit.

It is conditional. Skip it when the approach is straightforward, reversible, consistent with existing architecture and already supported by sufficient evidence.

## Core rule

**Agent-owned technical choices should stay agent-owned.**

Choose and justify a normal implementation detail when evidence is sufficient and the choice is reversible or governed by existing repository conventions.

Ask the user only when the decision changes product behavior, public/external contract, data semantics, compatibility expectations, operational risk, irreversible migration/destructive action, or another material trade-off that cannot be derived from current requirements.

Do not ask the user to choose between implementation styles merely because several are possible.

## Required assessment

### Proposed solution

Describe the current implementation approach at the level needed to make execution coherent. Avoid line-by-line coding plans.

### Why this approach

Tie the approach to verified findings, current requirements and repository/system constraints.

### Affected boundaries

List material repositories/modules/APIs/schemas/jobs or operational surfaces that implementation must touch or preserve.

### Alternatives

Keep only alternatives whose rejection rationale remains material for avoiding a repeated bad direction or for explaining a meaningful trade-off. Omit routine alternatives.

### Verification strategy

State how acceptance will be demonstrated, including compatibility/regression checks where material.

### Risks

List only material risks and the mitigation/verification that addresses them.

### User decision needed

Use `none` unless a material product/contract/irreversible trade-off remains.

### Gate

Return exactly one:

- `ready` — approach, affected boundaries, material risks and verification strategy are sufficient for implementation.
- `needs_user_clarification` — a material trade-off or product/contract decision requires user intent.
- `needs_discovery` — additional technical/evidence work is needed before selecting a responsible approach, and the agent can perform it without a user decision.
- `blocked` — implementation planning cannot proceed because a required external dependency/decision/source is unavailable.

## Change control

If planning reveals that the current requirement/acceptance itself must change, return to the intake gate rather than silently rewriting product intent.

If planning reveals only a factual gap, return to investigation/discovery without asking the user.

## Persistence boundary

Do not create plan-history, decision-session or clarification files.

Return the current approach/decision/risk/verification material to `$work-item`. QiQi reconciles it into `plan.md`, `WORK_ITEM.md` Decisions/Next Actions and other existing living state only when material.
