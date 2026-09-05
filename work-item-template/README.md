# Global Work Item MCP

Global Work Item MCP là source of truth duy nhất cho **mutable product-task state ở QiQi/orchestration layer**.

Repository execution child **không cần Work Item ID/revision** và không cần `work_item_get`/`work_item_update` để hiểu hoặc hoàn thành repo-local TaskPacket. QiQi đọc/reconcile Work Item trước và sau delegation.

```text
Global Work Item MCP   = mutable product-task truth (QiQi side)
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
TaskPacket              = immutable delegated-turn task semantics
```

## Mục tiêu MVP

Giữ continuity cho product task qua nhiều turn/phase/repository mà không biến Work Item thành execution dependency, transcript hoặc project-management product.

MVP cố ý không có workflow DSL, event sourcing, RBAC, notification, Redmine sync, automatic phase transition hoặc web dashboard. Human CLI là read-only observer của canonical store.

## Canonical identity

Mỗi product task có stable ID dạng:

```text
<source>:<external-id>
```

Ví dụ `redmine:116655`.

## Ownership boundary

```text
User
  ↓
QiQi ↔ Work Item
  │
  │ semantically self-sufficient TaskPacket
  ▼
Child Agent
  │
  │ exact native evidence/result
  ▼
QiQi ↔ Work Item
```

QiQi sở hữu:

- current requirements/product decisions;
- overall status/phase/summary;
- repository assignment/dependency waves;
- blockers/questions/handoffs/next actions ở global task layer;
- stale detection/materiality;
- reconciliation của native child response;
- semantic completion.

Child sở hữu repo-local discovery/investigation/implementation/verification strategy nhưng không dereference Work Item để reconstruct task meaning.

## Progressive disclosure: snapshot và history

`work_item_get(id)` là bounded current-state projection:

```text
id / revision / title / status / phase / summary
current_requirements / repos / next_actions
open_questions / active_decisions / open_blockers / pending_handoffs
thin artifact metadata
history counts
```

Nó không mặc định hydrate resolved questions, superseded decisions, accepted/rejected changes, resolved blockers/handoffs hoặc checkpoint records.

Material history đọc riêng:

```text
work_item_history_read(
  id,
  collection,
  status?,
  repository?,
  cursor?,
  limit?
)
```

Mỗi call chỉ đọc một semantic collection:

```text
questions | decisions | changes | checkpoints | blockers | handoffs
```

Cursor bind Work Item id + exact whole revision + collection + filters. Revision đổi giữa pages → restart; không mix revisions.

## Grouped typed incremental mutation

`work_item_update` nhận:

```text
WorkItemMutation
  state       = bounded current-state patch
  operations  = grouped typed semantic mutations
```

`mutation.state` chỉ patch current effective fields:

```text
title / status / phase / summary
current_requirements
repos
next_actions
```

Historical collections không có public full-array replacement path.

`mutation.operations` là grouped typed object:

```text
decision_upsert[]
question_upsert[]
change_upsert[]
blocker_upsert[]
handoff_upsert[]
checkpoint_append[]
```

Không có `{op,value}` envelope. Omit unused groups. Tối đa 50 semantic records tổng cộng/call. Tất cả groups build one final candidate và commit all-or-nothing dưới one exact Work Item revision. Stale writer conflict; server không auto-rebase.

Stable-id lifecycle monotonic; identity/provenance established không silently rewrite. Checkpoints append-only.

Successful `work_item_update` trả compact receipt:

```json
{
  "updated": true,
  "id": "redmine:116655",
  "revision": 42,
  "changed": ["repos.backend-api", "decisions:d7", "checkpoints"]
}
```

Receipt là commit confirmation, không phải refreshed snapshot.

## `$work-item` operational skill

Operational protocol ship tại:

```text
work-item-template/skills/work-item/SKILL.md
```

Skill này là **QiQi/orchestration-side protocol**:

- canonical Work Item đã identify/selected → QiQi apply `$work-item`;
- user explicitly yêu cầu tạo/dùng Work Item → QiQi apply `$work-item`;
- trước QiQi `work_item_*` call → apply `$work-item`;
- generic ticket/task/incident không tự động tạo/chọn Work Item.

Repository child không apply `$work-item` như prerequisite cho TaskPacket execution.

## TaskPacket relation

QiQi distill Work Item/user/Knowledge/cross-repo state thành immutable repo-local problem contract:

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

Không đưa child-facing:

```text
user_request
Work Item id/revision
normal verification command
Work Item phase/status/global next_actions
```

Material semantics phải survive distillation. Nếu child cần Work Item dereference để hiểu objective/boundaries/premises/acceptance thì TaskPacket chưa đủ.

## Immutable snapshot và stale result

TaskPacket là immutable semantic snapshot cho một delegated turn. Canonical Work Item có thể đổi trong khi child chạy; child không chase mutable global state.

QiQi đánh giá materiality. Với material change, stale execution result **MUST NOT become current truth**. Cancel/interrupt/resume/redelegate/reconcile là mechanism tùy runtime capability.

## Native result reconciliation

`settled | failed | blocked` chỉ là runtime lifecycle truth. Không thêm semantic status thứ hai.

QiQi đọc exact native response rồi:

1. reread latest Work Item khi dependent decision cần current truth;
2. reconcile evidence với TaskPacket acceptance + latest requirements;
3. persist canonical facts/checkpoints/blockers/handoffs/next actions trong authority;
4. quyết định semantic completion/next wave/RESUME/redelegate/user question.

## Questions, decisions, changes, blockers, handoffs

- `questions[]`: product/external ambiguity lifecycle;
- `decisions[]`: material decisions;
- `changes[]`: requirement/scope evolution;
- `blockers[]`: material progress blockers;
- `handoffs[]`: explicit remaining work chuyển repo/owner;
- `next_actions[]`: current continuation actions.

Lifecycle transitions phải monotonic; historical statement đổi thì thêm successor/transition phù hợp thay vì rewrite provenance.

## Optional task artifacts

Artifacts lưu detail lớn cho explicit intake/investigation/plan/review/report workflows. Chúng không thay canonical continuation state.

Public MCP read flow:

```text
work_item_artifact_list
→ work_item_artifact_get manifest
→ work_item_artifact_read bounded section chunks
```

Artifact revision độc lập Work Item revision. Append/finalize không advance Work Item revision. Completed artifact immutable trong MVP. Nếu artifact cũ conflict current Work Item state, Work Item thắng.

Xem `ARTIFACTS.md` cho artifact API/lifecycle chi tiết.

## Storage và concurrency

SQLite dùng whole-document optimistic revision + atomic transaction. Work Item không trở thành per-record/event/chunk store chỉ để phục vụ progressive reads/writes.

Default DB:

```text
~/.local/share/agent-work-items/work-items.sqlite3
```

## Verification

```bash
bash scripts/work-item-template-check.sh
bash scripts/install-user-mcp.sh
```

Sau public MCP/skill change, mở fresh QiQi session và xác nhận schema mới được discover. Acceptance smoke phải chứng minh QiQi read/update/reconcile canonical state trong khi repository child thực thi TaskPacket mà không cần Work Item dependency.
