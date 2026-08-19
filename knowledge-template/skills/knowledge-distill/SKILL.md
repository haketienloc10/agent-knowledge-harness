---
name: knowledge-distill
description: Distill reusable verified knowledge before writing to the shared Knowledge MCP.
---

# Knowledge Distillation

Use this procedure during finalization before `knowledge_write`.

1. Review what the work actually established from source, tests, runtime evidence, user decisions or trusted documents.
2. Do not persist working logs, task-specific status, obvious facts directly readable from current source, guesses, or unverified hypotheses.
3. Keep only non-trivial conclusions likely to help future work: invariant, contract, ownership, flow, constraint, stable verification behavior or durable decision.
4. Search existing shared knowledge first when the candidate may update an existing concept. Prefer update over duplicate create.
5. Choose semantic scope (`global`, `system`, `repo`, `domain`) for retrieval; current repository is not a permission boundary.
6. Produce a concise lowercase kebab-case `canonical_name` using canonical terminology. This is semantic identity, not a filename.
7. Build one nested `routing` object. Put `summary`, `when_to_read`, `keywords` and optional `aliases` inside `routing`; never flatten those fields at the entry top level.
8. Write `routing.summary`, `routing.when_to_read` and `routing.keywords` with concise canonical concepts, normally English. Preserve Vietnamese, legacy names, acronyms and project-specific variants in `routing.aliases` when useful.
9. `content` may use the language that preserves meaning best. Do not add a language metadata field.
10. Include provenance in `sources`. Do not write durable facts without evidence.
11. For create, omit both `id` and `expected_revision`. For update, use the exact `id` and `expected_revision` returned by `knowledge_read`; never guess identity, path or revision.
12. Never send `path`, `filename`, `directory`, `index_path` or any filesystem-routing field. Knowledge MCP owns materialization.
13. If a tool call fails validation, inspect the typed tool schema/error and correct the payload once; do not probe alternative shapes by trial and error.
14. If no durable candidate remains, call `knowledge_write(entries=[])` to record that finalization review completed without persistence.

If shared knowledge conflicts with live source/test in the owner repository, treat live source/test as authoritative for the current work and update the shared knowledge only after the new conclusion is verified.
