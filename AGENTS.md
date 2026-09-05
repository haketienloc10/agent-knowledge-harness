# AGENTS.md

Repo này phát triển bốn phần phối hợp nhưng giữ boundary độc lập:

- `workspace-template/`: QiQi Chief of Staff control plane + synchronous Herdr repo delegation;
- `repo-template/`: policy tối thiểu cho execution agent trong từng Git repo con;
- `work-item-template/`: user-scoped Global Work Item MCP giữ canonical mutable product-task state ở QiQi/orchestration side;
- `knowledge-template/`: user-scoped Shared Knowledge MCP + durable reusable knowledge store.

Repo không chứa product task thật hoặc tri thức nghiệp vụ thật của một workspace cụ thể.

## Bốn nguồn truth

```text
Global Work Item MCP   = mutable product-task truth (QiQi side)
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

Không nhân bản một loại truth sang nơi khác để tạo source of truth thứ hai.

## Nguyên tắc chung

- QiQi là coordinator/orchestrator, không phải coding agent của repo con.
- Mọi repo-local work từ QiQi đi qua `delegate_repo_task`.
- TaskPacket là **smallest sufficient repo-local problem contract** và **immutable semantic snapshot cho một delegated turn**.
- Child-facing TaskPacket không cần original `user_request`, Work Item ID/revision hoặc normal `verification` command.
- QiQi distill material user/product/Work Item/Knowledge/cross-repo semantics; material semantics phải survive distillation.
- Work Item chỉ thuộc QiQi/orchestration side. Child không `work_item_get`/`work_item_update` để hiểu hoặc persist repo-local assignment.
- Child sở hữu current-repo discovery/investigation/implementation/verification strategy; không tự sửa/delegate sibling repo.
- QiQi sở hữu global Work Item reconciliation, stale detection/materiality, dependency waves và semantic completion.
- Shared Knowledge có thể dùng ở child layer cho reusable repo/domain implementation knowledge khi stable policy cho phép, nhưng **không** để reconstruct TaskPacket semantics bị thiếu.
- Self-sufficient chỉ nói về task meaning; authorized runtime/log/API/DB/browser/infra evidence vẫn hợp lệ khi task/policy cho phép.
- Native final `agent_response` là semantic handoff; runtime `settled | failed | blocked` chỉ là lifecycle truth, không phải semantic completion.
- `qiqi_delegate` SQLite chỉ giữ runtime/session ownership, không semantic task state.
- Live owner source/test thắng stale reusable Knowledge cho implementation hiện tại.
- Architecture/runtime/public MCP contract change phải cập nhật code + tests/checkers + docs + migration cùng lúc.

## TaskPacket contract

Public `delegate_repo_task` semantic input:

```text
repository                 runtime routing arg
route                      runtime routing arg
objective                  required
scope[]                    required
acceptance_criteria[]      required
out_of_scope[]?            optional
context?                   optional
  trusted_facts[]?         {fact, source}
  claims_to_investigate[]? {claim, source}
constraints[]?             optional
known_unknowns[]?          optional
session_id?                runtime continuity arg
```

Không có child-facing:

```text
user_request
work_item_ref / work_item_revision
required_context legacy shape
verification as normal coordinator-prescribed command list
QiQi bookkeeping identifiers không có execution meaning
```

### Field semantics

- `objective`: one concise repo-local outcome, hiểu được không cần project/task history.
- `scope`: semantic/domain surface child inspect/change/design; QiQi không cần biết exact file/class.
- `out_of_scope`: explicit adjacent work không được làm.
- `trusted_fact`: execution premise child MAY rely on; MVP `{fact, source}`. Trusted-for-execution không đồng nghĩa independently verified truth.
- `claim_to_investigate`: proposition child MUST NOT assume; establish/contradict/unresolved khi nằm trong delegated scope.
- `known_unknown`: uncertainty child MUST NOT silently assume away; không bắt buộc resolve nếu scope/acceptance không yêu cầu.
- `constraints`: hard execution/product/system boundaries.
- `acceptance_criteria`: WHAT must be demonstrated. Child discover HOW theo repo/stable policy. Exact method/command chỉ contractual khi method itself là requirement.

Một proposition không được vừa trusted premise vừa claim cần verify.

### Task-semantic closed world

Child MUST NOT dùng Work Item, Shared Knowledge, sibling repository hoặc hidden QiQi/orchestration state để reconstruct objective/scope/product decision/constraint/acceptance bị thiếu.

Missing material semantics là coordinator-contract failure/blocker. Child surface exact missing input; QiQi repair/resume/redelegate.

Child MAY dùng:

```text
current repo
stable execution policy/environment
allowed Shared Knowledge cho reusable implementation/domain knowledge
authorized runtime/log/API/DB/browser/infra evidence
```

khi task/policy cho phép.

### Completeness + minimality

`smallest sufficient` được đánh giá bằng:

- **completeness**: context-naive child hiểu WHAT/WHERE boundary/WHICH premises/WHEN acceptable mà không cần hidden orchestration state;
- **minimality**: datum task-specific chỉ thuộc packet nếu bỏ nó có thể làm child hiểu sai assignment hoặc QiQi accept sai result.

Character/token count là safety/performance metric phụ; không truncate material semantics để đạt payload target.

### Immutable snapshot + stale result

TaskPacket không mutate sau START. Canonical state có thể đổi trong khi child chạy; QiQi đánh giá materiality.

- non-material change: child may settle, QiQi reconcile against latest truth;
- material change: stale result **MUST NOT become current truth**.

Cancel/interrupt/resume/redelegate/reconcile là mechanism tùy runtime capability. Không biến interrupt thành invariant nếu runtime không hỗ trợ.

## qiqi_delegate contract

Settled/failed return:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled | failed",
  "agent_response": "<exact native final assistant message>"
}
```

Blocked continuity return:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "blocked",
  "agent_response": null,
  "blocker_type": "agent_blocked"
}
```

Runtime state mô tả execution lifecycle, không semantic completion. Không thêm child-authored `completed | partial | blocked` semantic status envelope.

Session ownership persist ngay khi native identity known. Capture fail closed: không fallback screen/scrollback/transcript. Exact native `session_id` phải được giữ khi đã biết.

Renderer chỉ emit populated task-specific sections; stable runtime/repository policy nằm ở stable layer, không lặp trong mỗi TaskPacket prompt.

## Global Work Item contract

Public MVP tools:

```text
work_item_get(id)
work_item_history_read(id, collection, status?, repository?, cursor?, limit?)
work_item_list(status?, repository?, limit?)
work_item_create(id, title, summary?, status?, phase?, current_requirements?, repositories?)
work_item_update(id, expected_revision, mutation)
```

Canonical ID dạng `<source>:<external-id>`, ví dụ `redmine:116655`.

Work Item là canonical mutable state **của QiQi/orchestration layer**. Repository child không cần Work Item để hiểu/hoàn thành TaskPacket.

`work_item_get` trả bounded current-state projection. Resolved/superseded/checkpoint history đọc exact one collection qua `work_item_history_read` khi provenance material. Cursor bind Work Item id + whole revision + collection + filters; revision đổi giữa pages thì restart.

Public mutation:

```text
mutation.state
  = bounded current effective state only

mutation.operations
  = grouped typed incremental semantic mutations, <= 50 records total/call
```

`mutation.state` chỉ có title/status/phase/summary/current_requirements/repos/next_actions. Historical collections không có public full-array replacement path.

`mutation.operations` direct typed groups:

```text
decision_upsert[]
question_upsert[]
change_upsert[]
blocker_upsert[]
handoff_upsert[]
checkpoint_append[]
```

Không có `{op,value}` envelope. Các groups build one final candidate và commit all-or-nothing dưới one exact Work Item revision; cross-group caller order không phải public semantics. Stable-id lifecycle monotonic, identity/provenance không silent rewrite, checkpoint append-only.

Successful update trả compact receipt `{updated,id,revision,changed}`. Stale writer phải reread/reconcile; server không auto-rebase.

### `$work-item` skill

`$work-item` là user-scoped QiQi/orchestration-side operational protocol.

Apply khi:

- canonical Work Item đã identify/selected;
- user explicitly yêu cầu tạo/dùng Work Item;
- trước QiQi `work_item_*` call.

Generic ticket/task không tự động trở thành Work Item. Repository child không apply `$work-item` như TaskPacket execution prerequisite.

After child returns, QiQi đọc exact native response, reread latest Work Item khi dependent decision cần current truth, reconcile evidence + stale materiality, persist canonical changes và quyết định semantic completion.

## Shared Knowledge contract

Public tools:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_read_metadata(ids)
knowledge_read_section(id, section_id)
knowledge_write(entries)
knowledge_update(id, expected_revision, changes)
```

Progressive disclosure:

```text
knowledge_search(limit <= 10)
→ bounded decision cards
→ choose exact target
→ smallest sufficient exact read:
     knowledge_read | knowledge_read_metadata | knowledge_read_section
→ whole/partial mutation
```

Search card không chứa full content/sources/revision/path. Material use/update phải exact-read sufficient scope.

Ở QiQi layer, durable Knowledge có thể ảnh hưởng TaskPacket semantics và material premise phải được distill vào packet. Ở child layer, Knowledge chỉ legitimate cho reusable implementation/domain concern phát sinh trong execution khi stable policy cho phép; không phải fallback cho incomplete TaskPacket.

`knowledge_write` dùng create/intentional whole replacement. `knowledge_update` dùng metadata/content/one-existing-section partial mutation nhưng vẫn cạnh tranh trên one whole-document SHA-256 revision. Stable section marker chỉ là address trong cùng canonical Markdown document, không tạo per-section revision/chunk store.

## Greenfield authority

Child MAY tự chọn reversible technical decision không materially đổi:

- observable product semantics;
- external/public contract;
- security/compliance semantics;
- significant cost/operational envelope.

Decision vượt boundary phải surface về QiQi/user thay vì invent product truth.

## Khi thay đổi Workspace Template

1. Giữ QiQi orchestration, dependency waves và Delegation Silence.
2. `.codex/config.toml` chỉ project-scope `qiqi_delegate`; Work Item/Knowledge là user/global scope.
3. QiQi sở hữu Work Item read/reconciliation; child-facing TaskPacket không Work Item ID/revision.
4. QiQi distill semantic problem contract; material semantics survive distillation.
5. Shared Knowledge boundary là task-semantic closed world, không blanket execution-information ban.
6. Stable runtime/repo boilerplate không render lặp per TaskPacket.
7. Native result capture giữ exact final response; runtime lifecycle tách semantic completion.
8. Architecture/runtime/public MCP contract change phải cập nhật checker + docs + migration.

## Khi thay đổi Repository Template

1. Giữ exact Git-root boundary và cấm sibling source/runtime state.
2. Child bắt đầu từ immutable TaskPacket + current repo/stable policy.
3. Missing task semantics không recover từ Work Item/Knowledge/sibling state.
4. Work Item không phải child execution dependency.
5. Shared Knowledge MAY dùng cho reusable repo/domain implementation knowledge khi policy cho phép.
6. Live owner source/test thắng stale Shared Knowledge cho current implementation.
7. Child tự chọn verification HOW và report actual commands/checks/results.
8. Cross-repo remaining work quay lại QiQi; child không tự sửa/delegate sibling repo.
9. Không thêm repo-local task store, knowledge store hoặc rigid semantic result status.

## Khi thay đổi Work Item Template

1. Giữ one canonical task store independent workspace/repo/CWD và owned by QiQi orchestration.
2. Bounded GET + scoped history + list/create + one typed update tool.
3. `expected_revision` là mandatory mutation concurrency boundary; history cursor bind exact whole revision.
4. Public read projection tách raw canonical document.
5. Public update model tách `WorkItemStatePatch` khỏi semantic operations; historical collections không full-array replace.
6. Grouped typed operations + checkpoint append; không `{op,value}` union/list; max 50 records/call.
7. Cross-group refs validate final candidate; stable lifecycle/provenance monotonic.
8. Update success compact receipt; no post-commit full hydration.
9. Work Item MCP/server/skill docs không được instruct repository child dereference Work Item để hiểu TaskPacket.
10. Fresh-session smoke phải chứng minh QiQi read/update/reconcile canonical state trong khi child không cần Work Item.

## Khi thay đổi Knowledge Template

1. Search và exact read là stages riêng; search không trả revision/content.
2. Scoped reads không hydrate untouched large content.
3. Store vẫn one canonical Markdown document/concept + one SHA-256 revision.
4. Partial mutation reconstruct canonical payload server-side và reuse whole-document write/lock/index/revision path.
5. Stable section marker deterministic/unique; section replace không implicit add/delete/reorder.
6. Agent-facing schema không expose arbitrary filesystem path.
7. Update optimistic whole-document revision; external edit không silent overwrite.
8. `sources` bắt buộc cho durable fact; unverified hypothesis không persist như fact.

## Migration

Public contract change phải có migration cho workspace/repo đã tồn tại. Migration framework dùng per-file `replace`, `merge`, `delete`, `manual_review`, pin exact `from_ref`/`to_ref`, preflight trước mutate và lưu migration state dưới `.qiqi/`.

TaskPacket 0.2.x là coordinated public schema change: migrate workspace/repo policy + qiqi_delegate code/checkers/docs cùng nhau; mở fresh sessions sau migration để discover tool schema mới. Migration không tự sửa user MCP registration.

## Review tối thiểu

Review phải xác nhận:

- bốn nguồn truth không bị trộn;
- Work Item chỉ thuộc QiQi side và không leak thành child task dependency;
- TaskPacket semantically self-sufficient nhưng không cấm legitimate implementation/runtime evidence;
- `user_request`/normal `verification`/Work Item ref không còn child-facing contract;
- trusted fact / claim / known unknown semantics không bị trộn;
- stale result không được promote thành current truth;
- runtime state không bị dùng như semantic completion;
- Shared Knowledge không reconstruct missing task semantics;
- owner source/test thắng stale reusable Knowledge;
- checkers/tests/docs/migration pin đúng contract mới.
