---
name: knowledge-distill
description: Use immediately before any Shared Knowledge finalization review or knowledge_write. Distill verified reusable conclusions from investigation, implementation, tests, runtime evidence, or decisions; separate established facts from inference and uncertainty; never turn an unverified task or bug premise into durable knowledge.
---

# Knowledge Distillation

Use this procedure whenever current policy requires a durable knowledge review and
before every `knowledge_write`, including an empty review.

The output of this skill is a set of **durable conclusions supported by evidence**,
not a summary of the task that happened to lead to them.

## Core rule

**Persist what the work established, not what the task assumed.**

A bug report, ticket title, user suspicion, attempted fix, search query, or working
hypothesis is investigation input. It becomes durable knowledge only if evidence
actually establishes it.

If an investigation does **not** confirm its original bug hypothesis but does
establish a reusable boundary, invariant, negative finding, diagnostic rule,
ownership fact, contract, operational constraint, or missing-observability fact,
persist that verified conclusion under its own semantic identity. Do not create a
bug-named entry and bury the real knowledge inside it.

## Procedure

### 1. Build an evidence ledger

Before naming a candidate, reconstruct what the work actually established. Separate:

- **verified source/code facts**: properties established by current owner source,
  configuration, schema, or static control/data flow;
- **verified test/runtime observations**: behavior directly observed in tests, logs,
  traces, commands, or runtime artifacts;
- **trusted decisions/contracts**: explicit user, architecture, specification, or
  decision evidence that is authoritative for the conclusion;
- **inferences**: conclusions reasonably implied by multiple facts but not directly
  observed;
- **remaining uncertainty**: relevant questions the evidence did not resolve.

Do not collapse these categories merely to make the final knowledge shorter.

### 2. Extract durable candidates from the evidence, not the task title

For each possible candidate, ask:

- Would this change a future implementation, investigation, verification, design,
  ownership, or operational decision?
- Is it non-trivial enough that rereading current source is not the cheapest path?
- Is it expected to survive beyond this task/branch/session?
- Does the evidence establish the candidate strongly enough to persist it?

Useful durable candidates include verified invariants, system/repo boundaries,
contracts, flow properties, ownership, compatibility constraints, diagnostic
interpretation rules, recurring operational behavior, stable verification behavior,
and durable decisions.

A **negative investigation result** is useful only when it rules out or narrows a
stable boundary. `Could not reproduce bug X` by itself is task status, not durable
knowledge. `Within one verified service lifecycle, code can emit at most one command`
may be durable because it changes how future duplicate-event evidence is interpreted.

### 3. Calibrate every claim to its evidence

**Compression must not increase certainty.** Distillation may shorten evidence but
must never make a stronger claim than the sources establish.

In particular:

- distinguish static code-path properties from runtime delivery guarantees;
- distinguish one observed execution from all possible executions;
- distinguish absence of evidence from evidence of absence;
- use words such as `always`, `never`, `exactly once`, `at most one`, `guarantees`,
  or `impossible` only when the cited boundary genuinely proves them;
- preserve materially relevant uncertainty instead of silently resolving it.

If a conclusion is partly inferred, state the inference as such or phrase the exact
boundary the evidence supports.

### 4. Choose semantic identity from the durable conclusion

Choose `scope`, `canonical_name`, and title from **what is known**, not from the
incident/ticket wording that initiated investigation.

- Use `global`, `system`, `repo`, or `domain` according to where the conclusion is
  reusable; current repository is not a permission boundary.
- `canonical_name` is concise lowercase kebab-case canonical terminology.
- `scope.id` uses the same lowercase convention, with `.` or `-` as the only
  separators (for example `search-air`, `payment.retry`). Never use `_`, `/`, or a
  filesystem-style path.
- Do not make ticket IDs, temporary branch names, or an unverified bug hypothesis
  the semantic identity. Keep useful ticket/legacy terms in aliases or provenance.

### 5. Search existing knowledge using the candidate meaning

Before create/update, call `knowledge_read` for the **candidate conclusion**, using
canonical concepts plus useful project/legacy/original-language aliases.

Do not search only the original task wording. Prefer updating an existing concept
over creating a duplicate. For update, use the exact returned `id` and
`expected_revision` and re-distill if the revision conflicts.

### 6. Make provenance strong enough to audit the claims

Every material durable claim must be traceable to `sources`.

For repository evidence, prefer an immutable commit/revision in `ref`. A moving
branch-only ref is weaker provenance; use it only when an immutable revision cannot
be established and keep the resulting certainty appropriately bounded.

Use source notes to identify the relevant behavior/boundary when that helps a future
reader verify the conclusion. A source note is a compact provenance pointer, not an
evidence dump or file-by-file investigation log. Put detailed evidence in `content`
and use additional source entries only when they represent genuinely distinct
provenance. Do not persist guesses or unsupported hypotheses as facts merely because
a source was attached.

### 7. Preserve fact, implication, and uncertainty in content

Content should make the reusable conclusion easy to consume without overstating it.
When a candidate contains mixed certainty, structure or word it so a future reader
can distinguish:

- what is established;
- what diagnostic/design implication follows;
- what remains unresolved and would require runtime or owner evidence.

Headings such as `Established`, `Diagnostic implication`, and `Remaining uncertainty`
are optional; the distinction is mandatory when materially relevant.

Do not write a chronological investigation diary. Keep only evidence needed to
understand and audit the durable conclusion.

### 8. Make routing describe future retrieval, not current task status

Build one nested `routing` object:

- `summary`: state the most important reusable distinction/boundary, including a
  critical counterexample or limitation when omitting it would cause future
  misinterpretation;
- `when_to_read`: future situations where this knowledge can change a decision;
- `keywords`: concise canonical concepts, normally English;
- `aliases`: multilingual, legacy, acronym, ticket, symbol, and project terms useful
  for retrieval.

Do not flatten routing fields at the entry top level.

### 9. Build the typed write payload

- Create: omit `id` and `expected_revision`.
- Update: use exact `id` + `expected_revision` returned by `knowledge_read`.
- Never provide `path`, `filename`, `directory`, `index_path`, `index`, or any other
  filesystem-routing field.
- `content` may use Vietnamese, English, or mixed language. Do not create a
  `language` field.
- Knowledge MCP owns ID/path/render/index/locking/revision/persistence mechanics.

### 10. Run payload readiness before calling knowledge_write

After semantic distillation is complete, convert each surviving candidate into the
current typed `knowledge_write` payload and inspect the tool schema before the call.
The typed schema is authoritative for required fields and hard field limits if they
change.

**`routing.summary` is a retrieval abstract, not overflow storage for the
investigation.** Keep only the smallest durable distinction that helps a future
agent decide whether to read the document. Put supporting evidence, ruled-out
hypotheses, caveats, detailed reasoning, and materially relevant uncertainty in
`content`.

#### Summary and source-note budget gate

Write `content` first. Draft `routing.summary` and `sources[].note` last.

A good `routing.summary` normally contains one reusable boundary or decision in one
or two short sentences. For the current schema, **do not call `knowledge_write`
until the summary is 300 characters or less**. Each `sources[].note` should be a
compact provenance pointer and must be 600 characters or less before the call.
These are conservative preflight budgets below the schema's hard limits.

When the execution environment can count characters, measure these fields
**deterministically** before the tool call (`len(...)` or an equivalent exact count);
do not estimate by eye. If exact counting is unavailable, use a stricter fallback:
summary about 200 characters or less and each source note about 400 characters or
less.

Do not mechanically truncate an oversized field. Rewrite `routing.summary` as:

`durable conclusion + critical boundary`

For an oversized source note, keep only:

`stable provenance location + exact behavior/boundary verified there`

Move evidence enumeration, implementation walkthroughs, long source/method lists,
ruled-out branches, and detailed uncertainty into `content`. Keep only an uncertainty
qualifier that is essential to prevent future misinterpretation.

Every persisted entry must include a non-empty `sources` list. Metadata compression
must not delete provenance or uncertainty merely to satisfy a field limit.

Before the call, verify at minimum:

1. the candidate describes what the evidence established, not the task premise;
2. `routing` is nested and `routing.summary` passes the deterministic summary budget;
3. `sources` is present and non-empty, each source note passes its budget, and
   provenance remains sufficient to audit material claims;
4. detailed evidence and uncertainty live in `content`, not in routing/source-note
   metadata;
5. create/update identity and revision follow the current typed schema;
6. no filesystem-owned or unsupported fields are present;
7. `scope.id` and `canonical_name` use only lowercase letters/numbers with `.` or
   `-` separators (no `_`, no `/`).

If validation still fails, inspect the typed schema/error, repair only the fields
named by that error, re-run the deterministic length preflight, and retry once. Do
not probe alternative payload shapes by trial and error, and do not weaken or
silently truncate the durable claim merely to make validation pass.

### 11. Decide whether to write

Write only candidates that survive the quality gates above.

Reject candidates that are merely:

- task status, working logs, or a report of actions performed;
- an obvious fact cheaply readable from current source;
- a ticket/bug premise that was not verified;
- an unverified hypothesis or root-cause guess;
- a temporary implementation detail with no expected reuse;
- `bug not reproduced` without a durable boundary learned from that result.

If policy required a review but no durable candidate remains, call
`knowledge_write(entries=[])`. If policy allowed the entire write review to be
skipped, do not call an empty write as ceremony.

## Example: investigation premise differs from durable knowledge

Suppose the task is “investigate duplicate price-difference mail.” Investigation
does not prove which component duplicated a physical email, but it verifies that:

- one service lifecycle reaches the mail trigger at most once after processing its
  internal loop;
- downstream delivery lacks an end-to-end logical correlation/deduplication key;
- repeated internal log blocks alone therefore do not prove multiple submissions;
- runtime correlation across request entry, spool/file creation, and SMTP delivery
  is still required to locate physical duplication.

Do **not** create knowledge whose identity claims `duplicate-mail-bug` was found.
Persist the verified reusable concept instead, for example an
`...-idempotency-boundary` or `...-duplicate-mail-diagnostic-boundary`, with the
unresolved physical duplication point preserved as uncertainty.

## Conflict with live truth

If shared knowledge conflicts with current owner source/test or stronger live owner
evidence, live owner evidence wins for the current work. Re-distill and update the
shared knowledge only after the replacement conclusion is verified.
