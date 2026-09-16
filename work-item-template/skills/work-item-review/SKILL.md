---
name: work-item-review
description: >
  Acceptance clarification gate for a tracked Work Item. Use with $work-item before
  completion/reporting to assess each acceptance criterion against actual evidence,
  identify unresolved deviations and determine whether user acceptance is required.
---

# Work Item acceptance review gate

Use this skill as the **mandatory completion gate** before a tracked Work Item is marked done or treated as ready for final reporting.

Implementation being present, a child agent saying "done", or tests passing in isolation do not establish Work Item completion.

## Core rule

Separate these concepts:

- **implemented** — code/config/data change exists;
- **verified** — relevant evidence demonstrates actual behavior;
- **accepted** — current acceptance criteria are satisfied or an explicit authorized deviation is accepted.

Do not collapse them into one status.

## Required assessment

### Acceptance assessment

For every material current acceptance criterion, record:

- criterion;
- actual evidence;
- assessment: `satisfied | not-satisfied | unresolved`;
- next action when not satisfied or unresolved.

Do not mark a criterion satisfied based only on implementation intent or an agent assertion.

### Deviations

List behavior that differs from the current requirement/plan and explain whether it is:

- an implementation defect to fix;
- a verified equivalent outcome;
- a material product/contract deviation requiring user acceptance.

### Missing evidence

Identify verification that has not actually been performed. Do not fabricate test, deployment, branch, commit or environment evidence.

### Blocking questions

List only questions whose answer changes completion/acceptance. Use `none` when there are none.

### Gate

Return exactly one:

- `ready` — all material acceptance criteria are satisfied/accepted with actual evidence and no blocking question remains.
- `needs_user_clarification` — completion depends on explicit user acceptance of a material deviation or unresolved product/domain expectation.
- `needs_discovery` — more verification, remediation or objective evidence work is required and can proceed without a user decision.
- `blocked` — required verification/evidence cannot currently be obtained because an external dependency/environment is unavailable.

For `needs_discovery`, state the exact next agent action: verify, reproduce, fix, gather evidence, or re-investigate.

## Requirement drift

Review against the **current** Work Item revision, not an obsolete delegated revision or original request wording.

If review exposes a changed requirement rather than a failed implementation, return to intake reconciliation. If review exposes a factual contradiction, return to investigation. If it exposes an implementation gap, return to implementation/verification.

## Reporting boundary

`ready` means the Work Item can proceed to required final reporting/completion assessment. It does not authorize fabricating any report field not supported by stored current state/evidence.

## Persistence boundary

Do not create review-session/history files.

Return the assessment to `$work-item`. QiQi reconciles current acceptance evidence/gaps into `review.md` and `WORK_ITEM.md`. Retain only material evidence and unresolved completion state.
