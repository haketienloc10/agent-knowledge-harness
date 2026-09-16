# AGENTS.md — agent-knowledge-harness contributor contract

Repo này ship template/policy/runtime, không chứa task thật của một workspace cụ thể.

## Current architecture

```text
workspace-template/   QiQi orchestration + qiqi_delegate
repo-template/        child execution policy
work-item-template/   filesystem Work Item lifecycle skill/templates
knowledge-template/   reusable Shared Knowledge MCP
```

Current truth boundaries:

```text
workspace/work-items/  = mutable/current task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

Work Item không dùng MCP/SQLite. Không reintroduce `work_item_get/update/history`, global Work Item DB hoặc child-deny filesystem boundary.

## Work Item invariants

- Work Item là current-state dossier, không phải work history.
- QiQi là canonical writer; child có thể đọc mounted Work Item nhưng trả evidence qua native response.
- Không persist turn logs, command chronology hoặc routine progress.
- Multi-turn investigation/plan/review rewrite living current state.
- Requirement change rewrite effective current requirement; prior investigation được reconcile finding-by-finding, không auto discard.
- `revision` dùng stale detection giữa delegation và reconciliation, không phải database CAS.
- Final report derive từ persisted current state/evidence, không từ hidden conversation memory.

## Delegation invariants

TaskPacket vẫn phải semantically sufficient cho repo-local assignment. Work Item bổ sung durable continuity nhưng không phải fallback cho packet thiếu objective/scope/acceptance.

Child không sửa sibling repo, `.qiqi/state` hoặc canonical Work Item. QiQi reconcile native child evidence và quyết định global completion.

## Shared Knowledge

Chỉ verified reusable invariant/contract/behavior mới persist Knowledge. Task-specific mutable state, routine completion và working hypothesis ở Work Item/repo execution layer.

## Validation

Sau thay đổi contract chạy các checker/workflow tương ứng. Public workspace/repo contract change phải có migration mới; không rewrite historical migration definitions.
