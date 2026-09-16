---
name: work-item-intake
description: >
  Clarification gate for a tracked Work Item intake. Use with $work-item before
  investigation when request meaning, scope, constraints, acceptance criteria or
  domain terminology must be made explicit without drifting into implementation.
---

# Work Item intake clarification

Use this skill as the **mandatory semantic gate** for a new tracked Work Item and for a requirement change that materially changes task meaning.

The goal is not to investigate code. The goal is to establish an effective requirement that is clear enough for investigation to proceed without guessing product intent.

## Core rule

**Clarify meaning, not mechanics.**

Ask the user only for information that represents intent, product/domain semantics, acceptance, scope, constraints, irreversible choice, or another decision that cannot be established authoritatively by repository/document discovery.

Do not ask the user to choose a repository, module, class, implementation pattern, test command or other technical fact when the agent can discover it.

## Classify uncertainty

Classify every material unknown before deciding whether to ask:

1. **Requirement unknown** — only the user/product owner can decide. Ask the user.
2. **Domain/terminology unknown** — state the current interpretation and source. If authoritative docs/repository/reference material can resolve it, prefer discovery before asking.
3. **Implementation unknown** — do not ask the user. Hand it to investigation.
4. **Safe reversible assumption** — state the assumption explicitly and continue when a wrong assumption is cheap to detect and reverse.

Never silently convert an unknown product requirement into an implementation assumption.

## Required assessment

Present a concise assessment using these semantic sections when material:

### Understanding

- What the agent believes the user wants.
- Expected outcome / externally visible behavior.

### Known scope

- In scope.
- Out of scope only when it prevents a likely misunderstanding.
- Material constraints.

### Terms / concepts

For any important ambiguous term:

- term;
- current interpretation;
- evidence/source for that interpretation when available;
- whether clarification is still needed.

Do not create a glossary for ordinary terms that are already clear.

### Material ambiguities

List only ambiguities that could change requirement, acceptance, scope or externally visible behavior.

### Proposed acceptance

Express concrete acceptance criteria sufficient to decide later whether the task is done. Do not invent unavailable product expectations.

### Discovery handoff

List factual/module/repository questions that investigation should answer without asking the user.

### Gate

Return exactly one gate state:

- `ready` — requirement meaning, material scope and acceptance are clear enough; remaining unknowns are implementation/discovery facts.
- `needs_user_clarification` — a material intent/product/domain decision requires the user.
- `needs_discovery` — an authoritative factual/domain lookup should happen before the requirement can be finalized, and no user decision is currently required.
- `blocked` — progress is impossible because a required external dependency/source is unavailable.

## Ready criteria

`ready` requires all of the following:

- objective is understandable;
- material scope is bounded enough to investigate;
- acceptance is concrete enough to assess later;
- no unresolved ambiguity can materially change product intent;
- remaining technical/module unknowns can be delegated to investigation.

Knowing the exact repository/module is **not** required for intake readiness.

## Persistence boundary

This skill does not create files and does not mutate the canonical dossier directly.

Return the assessment to `$work-item`. QiQi reconciles only material current truth into `WORK_ITEM.md` and, when useful, `intake.md`. Do not persist the question/answer chronology, conversation transcript, discarded wording, or routine reasoning.
