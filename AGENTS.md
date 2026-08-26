# AGENTS.md

Repo này phát triển bốn template/phần phối hợp nhưng giữ boundary độc lập:

- `workspace-template/`: QiQi Chief of Staff control plane + synchronous Herdr repo
  delegation;
- `repo-template/`: workflow tối thiểu cho execution agent trong từng Git repo con;
- `work-item-template/`: user-scoped Global Work Item MCP giữ canonical mutable
  product-task state;
- `knowledge-template/`: Shared Knowledge Store + user-scoped Knowledge MCP độc lập
  với current workspace/repository.

Repo không chứa tri thức nghiệp vụ hoặc task state thật của một workspace cụ thể.

## Bốn nguồn truth

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

Không nhân bản một loại truth sang nơi khác để tạo source of truth thứ hai.

## Nguyên tắc

- QiQi là Chief of Staff/coordinator, không phải coding agent của repo con.
- Mọi repo-local work từ QiQi đi qua đúng một MCP tool: `delegate_repo_task`.
- Input delegation là TaskPacket có cấu trúc, giữ original `user_request`, repo-local
  `objective`, scope, required context + provenance, constraints, acceptance,
  verification và known unknowns.
- Khi delegation thuộc product Work Item, QiQi truyền canonical Work Item identity +
  revision trong `required_context`; child đọc current task state trực tiếp từ
  user-scoped Work Item MCP thay vì QiQi copy toàn bộ history.
- Execution agent không chia sẻ hidden conversation/workspace/sibling runtime/source
  context của QiQi. Work Item MCP và Knowledge MCP là explicit tool exceptions,
  không phải filesystem/sibling-repo exceptions.
- Child chỉ investigation/implementation/verification trong current Git root. Nó có
  thể update canonical Work Item bằng current-repo evidence + material
  blocker/question/checkpoint/handoff, nhưng không tự sửa/delegate sibling repo hoặc
  mark overall product task done.
- QiQi sở hữu overall Work Item orchestration: phase/status/summary, repo assignment,
  global next action, user/customer Q&A reconciliation và completion.
- Cross-repo remaining work được persist thành Work Item handoff khi phù hợp rồi trả
  QiQi để điều phối consumer repo.
- Work Item update bắt buộc optimistic `expected_revision`; stale writer phải
  reread/reconcile, không last-write-wins.
- Output semantic của repo turn là exact native final `agent_response` được capture
  qua Stop hook; không ép fixed headings và không dùng agent-written Markdown result
  artifact làm transport.
- Nếu Herdr báo blocked trước native final response, MCP preserve native session
  ownership và trả structured blocked continuity result; không bịa `agent_response`
  từ screen/transcript.
- `qiqi_delegate` SQLite chỉ giữ runtime session/turn ownership; không giữ semantic
  task state.
- Shared durable knowledge đi qua `knowledge_read` / `knowledge_write`; current repo
  chỉ là ranking hint, không permission boundary.
- Task-specific status/Q&A/change/blocker không tự động trở thành Shared Knowledge.
- Trước create/update knowledge candidate phải search existing concept, dedupe và
  ưu tiên update; `entries=[]` chỉ dùng sau required review không còn candidate.
- Product repo live source/test giữ implementation truth. Khi conflict với stale
  reusable knowledge, live owner evidence thắng cho task hiện tại.
- Agent không sở hữu knowledge filename/path/directory. Knowledge MCP sở hữu
  ID/path/render/index/locking/revision/persistence.
- Không đưa workflow DSL, event sourcing, RBAC, notification, UI hoặc Redmine sync
  vào Work Item MVP khi chưa có evidence cần thiết.
- Không đưa vector DB, embedding, translation hoặc LLM vào Knowledge MCP MVP.

## Global Work Item contract

Public MVP tools:

```text
work_item_get(id)
work_item_list(status?, repository?, limit?)
work_item_create(id, title, summary?, status?, phase?, current_requirements?, repositories?)
work_item_update(id, expected_revision, changes)
```

Canonical identity dùng `<source>:<external-id>`, ví dụ `redmine:116655`.

Một Work Item giữ:

```text
status / phase / summary
current_requirements
questions
decisions
changes
repos
blockers
handoffs
next_actions
checkpoints
revision
```

`phase` là descriptive state, không phải hard FSM. Product workflow có thể loop
`uat -> implementation -> unit_test -> it -> uat` khi bug/change xuất hiện.

Snapshot hiện tại:

```text
summary/current_requirements/status/phase/repos/blockers/next_actions
```

Material history giải thích snapshot:

```text
questions/decisions/changes/checkpoints
```

Không lưu terminal transcript, hidden reasoning hoặc command-by-command activity.

Question được resolve thành decision; nếu semantics/scope thật sự đổi thì reconcile
`current_requirements` và ghi `changes[]`. Decision cũ bị thay không bị xóa; mark
`superseded` + `superseded_by`.

Persistence là user-scoped SQLite qua explicit `WORK_ITEM_DB_PATH`, independent CWD.
SQLite dùng atomic transaction + optimistic revision; arrays trong update replace
nguyên tử, nested object merge theo JSON merge-patch semantics.

## qiqi_delegate contract

`workspace-template/mcp/qiqi_delegate` sở hữu Herdr execution lifecycle, native
session, Stop-hook capture, runtime state và cleanup. START/RESUME dùng cùng tool.

Public structured input:

```text
repository
route
user_request
objective
scope
out_of_scope
required_context
constraints
acceptance_criteria
verification
known_unknowns
session_id?
```

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

Session ownership phải persist ngay khi native identity được biết, trước
blocked/result-capture handling. Native response transport fail closed: không
fallback terminal screen, scrollback, transcript parsing hoặc report Markdown.

`.qiqi/state/qiqi_delegate.sqlite3` là workspace MCP runtime state. `.qiqi/runs/`
chỉ là legacy ownership-import bridge. Canonical task state nằm trong Global Work
Item MCP.

## Shared Knowledge contract

Public MVP tools:

```text
knowledge_read(keywords, context?, limit?)
knowledge_write(entries)
```

Store là Markdown + generated `INDEX.md` với namespaces `global/`, `systems/`,
`repos/`, `domains/`. Create không nhận filesystem path. Update bắt buộc exact ID +
optimistic revision. Human direct edit làm index stale tới khi reindex.

### Usage decision invariant

- **MUST read** khi prior reusable knowledge có thể đổi interpretation,
  orchestration, implementation hoặc verification.
- **MAY read** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp.
- **SKIP read** cho mechanical/exact local/status-only work nơi durable context không
  thể đổi action.
- **MUST review/write** cho substantive work có khả năng tạo/xác nhận reusable
  conclusion; trivial/mechanical/report-only work được skip.
- `knowledge_write(entries=[])` chỉ dùng sau required review không có candidate.
- Trước create/update phải search existing concept và ưu tiên update.

## Khi thay đổi Workspace Template

1. Giữ QiQi task semantics, dependency waves và Delegation Silence.
2. `.codex/config.toml` chỉ sở hữu project-scoped `qiqi_delegate`; không thêm
   project-scoped `work_item` hoặc `knowledge`.
3. Work Item MCP + Knowledge MCP phải user/global scope để QiQi và Herdr child cùng
   thấy services independent CWD.
4. QiQi phải read/reconcile canonical Work Item trước orchestration và sau repo turn
   khi task thuộc Work Item.
5. TaskPacket phải identify Work Item + revision trong `required_context`; external
   fact ngoài Work Item mà QiQi dùng cho semantics vẫn phải inline với provenance.
6. `SYSTEM_MAP.md` vẫn là live topology artifact; Work Item không thay system map.
7. Native result capture giữ exact final response, không fixed schema/viewport/
   transcript fallback.
8. Blocked state preserve native session continuity trước cleanup.
9. Workspace không tạo task truth thứ hai ngoài Global Work Item MCP.
10. Architecture/runtime change bắt buộc cập nhật checker + docs + migration.

## Khi thay đổi Repository Template

1. Giữ Git-root boundary và cấm đọc/sửa sibling source/runtime state.
2. Work Item MCP là task-state tool exception; Knowledge MCP là reusable-context tool
   exception; cả hai không phải filesystem exception.
3. Nếu TaskPacket identify Work Item, agent phải `work_item_get` trước substantive
   work và update material current-repo state trước finalization khi phù hợp.
4. Agent không mark sibling repo/overall Work Item done; cross-repo work quay lại
   QiQi qua canonical handoff + native response.
5. Live owner source/test thắng stale shared knowledge.
6. Substantive reusable work phải knowledge review/write; trivial work được skip.
7. Không thêm repo-local task store hoặc knowledge store/index.
8. Không thêm fixed result headings hoặc agent-written QiQi result artifact.

## Khi thay đổi Work Item Template

1. Giữ one canonical task store independent workspace/repo/CWD.
2. MVP API nhỏ: get/list/create/update; không tạo tool cho từng micro-transition nếu
   chưa cần.
3. `expected_revision` là mandatory concurrency boundary cho update.
4. Schema phải giữ current requirements + material questions/decisions/changes,
   repo state, blockers, handoffs, next actions và checkpoints.
5. Validation phải reject malformed semantic objects và immutable metadata changes.
6. SQLite writes atomic; concurrent writers từ cùng revision không được cùng commit.
7. Không biến Work Item thành activity transcript hoặc reusable knowledge store.
8. User/customer decision history không bị silent rewrite; supersede thay vì xóa.
9. Unit tests cover CRUD/filter, semantic state, stale/concurrent writers và
   validation.
10. Fresh-session smoke phải chứng minh QiQi và repo child thấy cùng database.

## Khi thay đổi Knowledge Template

1. Giữ store độc lập với workspace/repo và không infer root từ CWD.
2. Agent-facing write schema không expose filename/path/directory/index path.
3. Identity/canonical path deterministic từ semantic scope/name.
4. `INDEX.md` generate từ detail metadata; không tạo hai source of truth.
5. Human-authored Markdown là first-class workflow; checker/reindex dùng cùng core.
6. Retrieval deterministic/index-first; repo/domain context chỉ boost ranking.
7. Update dùng optimistic revision; external edit không silent overwrite.
8. Không thêm `language`; aliases xử lý multilingual terminology.
9. `sources` bắt buộc; guess/hypothesis chưa verified không persist như fact.
10. Unit/integrity tests cover create/update, stale index/revision, concurrency,
    canonical path/traversal, multilingual aliases, empty review và batch failure.

## Migration

Execution/task-state contract change phải có migration cho workspace/repo đã tồn
tại. Migration Work Item update workspace/repo policy/checker/docs nhưng **không**
tự ghi user MCP config; operator cài `work_item` user scope explicitly từ
`work-item-template/`.

Repo `AGENTS.md` dùng 3-way merge để không mặc nhiên xóa product-specific
instructions; template-owned checker/docs dùng replace với backup behavior của
migration framework.

## Review tối thiểu

Review phải xác nhận:

- bốn nguồn truth không bị trộn;
- Global Work Item là canonical mutable task state duy nhất;
- QiQi và child cùng đọc Work Item, nhưng child chỉ execute current Git root;
- Q&A/decision/requirement change được giữ đủ để resume không hỏi lại;
- stale Work Item update bị reject và concurrent writer không silent overwrite;
- cross-repo remaining work quay lại QiQi, child không tự sửa sibling;
- public `qiqi_delegate` input vẫn là structured TaskPacket;
- native response round-trip không viewport/truncation dependency;
- blocked START giữ `session_id` và RESUME ownership;
- Knowledge MCP user/global registration independent CWD và usage vẫn conditional;
- docs/checkers/migration phản ánh cùng architecture;
- unit/static tests không được dùng để tuyên bố native CLI/user-MCP fresh-session
  smoke đã pass.
