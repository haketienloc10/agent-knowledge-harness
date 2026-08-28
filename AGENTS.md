# AGENTS.md

Repo này phát triển bốn phần phối hợp nhưng giữ boundary độc lập:

- `workspace-template/`: QiQi Chief of Staff control plane + synchronous Herdr repo delegation;
- `repo-template/`: policy tối thiểu cho execution agent trong từng Git repo con;
- `work-item-template/`: user-scoped Global Work Item MCP giữ canonical mutable product-task state;
- `knowledge-template/`: user-scoped Shared Knowledge MCP + durable reusable knowledge store.

Repo không chứa product task thật hoặc tri thức nghiệp vụ thật của một workspace cụ thể.

## Bốn nguồn truth

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

Không nhân bản một loại truth sang nơi khác để tạo source of truth thứ hai.

## Nguyên tắc chung

- QiQi là coordinator, không phải coding agent của repo con.
- Mọi repo-local work từ QiQi đi qua `delegate_repo_task`.
- TaskPacket giữ original `user_request`, repo-local objective, scope, required context + provenance, constraints, acceptance, verification và known unknowns.
- Khi delegation thuộc product Work Item, TaskPacket identify canonical Work Item + revision; child đọc current task state trực tiếp từ Work Item MCP.
- Child chỉ investigation/implementation/verification trong current Git root; không tự sửa/delegate sibling repo và không tự mark overall Work Item done.
- QiQi sở hữu global Work Item orchestration: overall status/phase/summary, repo assignment, product/customer decisions, global next action và completion.
- Cross-repo remaining work được ghi thành Work Item handoff khi phù hợp rồi trả QiQi để điều phối consumer repo.
- Work Item update bắt buộc optimistic `expected_revision`; stale writer phải reread/reconcile.
- Shared reusable knowledge dùng progressive lifecycle `knowledge_search → knowledge_read → knowledge_write`.
- Search card chỉ là candidate-routing surface; không dùng search card như full durable evidence và không lấy revision từ search.
- Existing knowledge update target phải full-read để lấy semantic payload + exact revision.
- Native final `agent_response` là semantic handoff; không dùng Markdown result artifact, viewport hoặc transcript parser làm transport fallback.
- `qiqi_delegate` SQLite chỉ giữ runtime/session ownership, không giữ semantic task state.
- Live owner source/test thắng stale reusable knowledge cho implementation hiện tại.
- Không đưa workflow DSL, event sourcing, RBAC, notification, UI hoặc Redmine sync vào Work Item MVP nếu chưa có evidence cần thiết.
- Không đưa vector DB/embedding/LLM retrieval vào Knowledge nếu chưa có evaluation chứng minh lexical progressive retrieval là bottleneck.

## Global Work Item contract

Public MVP tools:

```text
work_item_get(id)
work_item_list(status?, repository?, limit?)
work_item_create(id, title, summary?, status?, phase?, current_requirements?, repositories?)
work_item_update(id, expected_revision, changes)
```

Canonical ID dùng dạng `<source>:<external-id>`, ví dụ `redmine:116655`.

Một Work Item giữ snapshot hiện tại và material history:

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

`phase` là descriptive state, không phải hard FSM. Loop `uat -> implementation -> unit_test -> it -> uat` là hợp lệ.

Work Item không phải transcript. Không lưu command-by-command activity hoặc hidden reasoning.

Question được resolve thành decision; nếu requirement/scope thực sự đổi thì reconcile `current_requirements` và ghi `changes[]`. Decision cũ bị thay không bị silent rewrite; mark `superseded` + `superseded_by`.

SQLite user-scope dùng atomic transaction + optimistic revision. Arrays trong update replace nguyên tử; nested objects merge theo JSON merge-patch semantics.

## Shared Knowledge contract

Public tools:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_write(entries)
```

### Progressive disclosure invariant

```text
knowledge_search(limit <= 10)
→ bounded decision cards
→ chọn 1–2 exact IDs
knowledge_read(ids)
→ full semantic content + sources + routing + revision
```

Search card không chứa full content, sources, revision hoặc physical path. `knowledge_search` dùng để chọn candidate; material use/update phải full-read exact target.

- **MUST search** khi prior reusable knowledge có thể đổi interpretation, orchestration, implementation hoặc verification.
- **MAY search** khi query ngắn có thể giảm uncertainty/lặp investigation.
- **SKIP** cho mechanical/exact-local/status-only work nơi durable context không thể đổi action.
- **MUST review/write** cho substantive work có khả năng tạo/xác nhận reusable conclusion.
- `knowledge_write(entries=[])` chỉ dùng sau required review không có candidate.
- Trước create/update phải search existing concept; update existing target phải full-read trước.

Knowledge MCP sở hữu ID/path/index/locking/revision/persistence. Agent không truyền filename/path/directory và không tạo field `language`.

## qiqi_delegate contract

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

Session ownership persist ngay khi native identity known. Capture fail closed: không fallback screen/scrollback/transcript. Exact native `session_id` phải được giữ khi đã biết.

## Khi thay đổi Workspace Template

1. Giữ QiQi orchestration, dependency waves và Delegation Silence.
2. `.codex/config.toml` chỉ project-scope `qiqi_delegate`; `work_item` và `knowledge` là user/global scope.
3. QiQi read/reconcile canonical Work Item trước orchestration và sau repo turn khi task thuộc Work Item.
4. TaskPacket identify Work Item + revision; external fact ngoài Work Item mà QiQi dùng cho semantics vẫn phải inline với provenance.
5. `SYSTEM_MAP.md` vẫn là live topology artifact; Work Item không thay System Map.
6. Workspace Knowledge policy phải dùng search-first/exact-read progressive disclosure.
7. Native result capture giữ exact final response, không fixed schema/viewport/transcript fallback.
8. Architecture/runtime/public MCP contract change phải cập nhật checker + docs + migration.

## Khi thay đổi Repository Template

1. Giữ Git-root boundary và cấm đọc/sửa sibling source/runtime state.
2. Work Item MCP là task-state tool exception; Knowledge MCP là reusable-context tool exception; cả hai không phải filesystem exception.
3. Nếu TaskPacket identify Work Item, child `work_item_get` trước substantive work và chỉ update evidence/state thuộc current repo.
4. Search cards chỉ dùng chọn knowledge document; material use/update phải full-read exact target.
5. Live owner source/test thắng stale shared knowledge.
6. Cross-repo remaining work quay lại QiQi; child không tự sửa/delegate sibling repo.
7. Không thêm repo-local task store, knowledge store hoặc fixed result headings.

## Khi thay đổi Work Item Template

1. Giữ one canonical task store independent workspace/repo/CWD.
2. MVP API nhỏ: get/list/create/update.
3. `expected_revision` là mandatory concurrency boundary.
4. Schema giữ current requirements + material questions/decisions/changes, repo state, blockers, handoffs, next actions và checkpoints.
5. Validation reject malformed semantic objects và immutable metadata changes.
6. Concurrent writers từ cùng revision không được cùng commit.
7. Không biến Work Item thành activity transcript hoặc reusable knowledge store.
8. Fresh-session smoke phải chứng minh QiQi và repo child thấy cùng database.

## Khi thay đổi Knowledge Template

1. Search và exact read là hai stage riêng; search không trả revision/content.
2. Full read bounded và đủ semantic fields để safe read→write round trip.
3. Store independent workspace/repo/CWD; agent-facing schema không expose arbitrary filesystem path.
4. Retrieval deterministic/index-first; repo/domain context chỉ boost semantic match đã có.
5. Update dùng optimistic revision; external edit không silent overwrite.
6. `sources` bắt buộc cho durable fact; hypothesis chưa verified không persist như fact.
7. Tests cover thin search cards, exact-read bounds/round trip, stale index/revision, concurrency và validation.

## Migration

Public contract change phải có migration cho workspace/repo đã tồn tại. Migration framework dùng per-file `replace`, `merge`, `delete`, `manual_review`, pin exact `from_ref`/`to_ref`, preflight trước mutate và lưu migration state dưới `.qiqi/`.

Global Work Item migration phải đứng sau Knowledge progressive-disclosure migration hiện tại; không tự ghi user MCP config. Operator cài `work_item` user scope explicitly từ `work-item-template/`.

## Review tối thiểu

Review phải xác nhận:

- bốn nguồn truth không bị trộn;
- Global Work Item là canonical mutable task state duy nhất;
- QiQi và child cùng đọc Work Item nhưng child chỉ execute current Git root;
- Q&A/decision/requirement changes đủ để resume không hỏi lại;
- stale/concurrent Work Item update không silent overwrite;
- Knowledge search result thin, exact read bounded và revision chỉ đến từ full read;
- native response round-trip không viewport/truncation dependency;
- docs/checkers/migration phản ánh cùng architecture;
- static/unit tests không được dùng để tuyên bố native CLI/user-MCP fresh-session smoke đã pass.
