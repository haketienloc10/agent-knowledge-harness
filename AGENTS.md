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
- Khi delegation thuộc product Work Item, TaskPacket identify canonical Work Item + revision; child đọc bounded current task state trực tiếp từ Work Item MCP và chỉ đọc scoped history khi cần provenance/reconciliation.
- Child chỉ investigation/implementation/verification trong current Git root; không tự sửa/delegate sibling repo và không tự mark overall Work Item done.
- QiQi sở hữu global Work Item orchestration: overall status/phase/summary, repo assignment, product/customer decisions, global next action và completion.
- Cross-repo remaining work được ghi thành Work Item handoff khi phù hợp rồi trả QiQi để điều phối consumer repo.
- Work Item update bắt buộc optimistic `expected_revision`; stale writer phải reread/reconcile. History pagination cũng bind exact whole Work Item revision và phải restart nếu revision đổi giữa pages.
- Shared reusable knowledge dùng progressive lifecycle `knowledge_search → exact scoped read → knowledge_write/knowledge_update`.
- Search card chỉ là candidate-routing surface; không dùng search card như full durable evidence và không lấy revision từ search.
- Existing knowledge update target phải exact-read ở sufficient semantic scope để lấy canonical evidence/provenance cần thiết + exact whole-document revision.
- Native final `agent_response` là semantic handoff; không dùng Markdown result artifact, viewport hoặc transcript parser làm transport fallback.
- `qiqi_delegate` SQLite chỉ giữ runtime/session ownership, không giữ semantic task state.
- Live owner source/test thắng stale reusable knowledge cho implementation hiện tại.
- Không đưa workflow DSL, event sourcing, RBAC, notification, UI hoặc Redmine sync vào Work Item MVP nếu chưa có evidence cần thiết.
- Không đưa vector DB/embedding/LLM retrieval vào Knowledge nếu chưa có evaluation chứng minh lexical progressive retrieval là bottleneck.

## Global Work Item contract

Public MVP tools:

```text
work_item_get(id)
work_item_history_read(id, collection, status?, repository?, cursor?, limit?)
work_item_list(status?, repository?, limit?)
work_item_create(id, title, summary?, status?, phase?, current_requirements?, repositories?)
work_item_update(id, expected_revision, mutation)
```

Canonical ID dùng dạng `<source>:<external-id>`, ví dụ `redmine:116655`.

Stored Work Item giữ full canonical snapshot + material history:

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

Public `work_item_get` không expose raw full document. Nó trả bounded current-state projection gồm current requirements/repos, `open_questions`, `active_decisions`, `open_blockers`, `pending_handoffs`, current `next_actions`, deterministic history counts và thin artifact metadata. Resolved/superseded/checkpoint history đọc exact một collection qua `work_item_history_read` khi thực sự cần.

History read giữ canonical array order; cursor opaque bind Work Item id + whole Work Item revision + collection + filters. Không silently mix pages từ hai revisions hoặc reuse cursor giữa hai Work Item. `status` filter chỉ dùng cho lifecycle collection; `repository` hiện chỉ dùng cho checkpoints; filter không hợp lệ phải fail validation.

Canonical question/decision lifecycle status là required. Legacy missing/null status chỉ được migrate một lần thành question=`open`, decision=`active`; runtime không dựa vào implicit default lâu dài.

Public mutation contract là `WorkItemMutation`:

```text
mutation.state
  = bounded current effective state only

mutation.operations
  = grouped typed incremental semantic mutations, <= 50 records total/call
```

`mutation.state` chỉ có title/status/phase/summary/current_requirements/repos/next_actions. Historical collections (`questions`, `decisions`, `changes`, `blockers`, `handoffs`, `checkpoints`) **không có public full-array replacement path**.

`mutation.operations` là direct typed object, không phải discriminated-union list và không có `{op,value}` envelope:

```text
decision_upsert[]
question_upsert[]
change_upsert[]
blocker_upsert[]
handoff_upsert[]
checkpoint_append[]
```

Caller omit group không dùng. Tối đa 50 semantic records tổng cộng across groups. Các group build một final candidate và commit all-or-nothing trong một exact whole Work Item revision; cross-group caller order **không** phải public semantics. Order bên trong từng group được giữ khi canonical ordering material, đặc biệt checkpoint append.

Duplicate stable-id target trong cùng mutation bị reject. Stale semantic mutation không được server auto-rebase, kể cả khi concurrent writer sửa record/collection khác.

Stable-id `upsert` là create hoặc monotonic lifecycle advance, không phải arbitrary historical rewrite. Question/decision/blocker/handoff không reverse lifecycle; requirement change chỉ đi theo controlled transition graph. Semantic identity/provenance đã establish không bị silently replace; checkpoint chỉ append, không có checkpoint rewrite/upsert public API.

Cross-record reference (`question.decision_id`, `decision.superseded_by`) validate trên final candidate document, nên one atomic mutation có thể create decision mới + supersede decision cũ + resolve question mà không phụ thuộc cross-group execution order. Invalid reference hoặc grouped mutation bất kỳ fail thì transaction rollback toàn bộ.

Successful `work_item_update` trả compact receipt `{updated,id,revision,changed}`, không trả full Work Item document. Caller chỉ reread bounded `work_item_get` khi dependent decision thật sự cần resulting current state.

Fresh-agent happy path phải construct mutation từ declared typed schema/`$work-item`, không probe schema bằng intentionally-invalid `work_item_update` calls. Old `operations:[{op,value}]` shape phải không representable qua public schema.

`phase` là descriptive state, không phải hard FSM. Loop `uat -> implementation -> unit_test -> it -> uat` là hợp lệ.

Work Item không phải transcript. Không lưu command-by-command activity hoặc hidden reasoning.

Question được resolve thành decision; nếu requirement/scope thực sự đổi thì reconcile `current_requirements` và ghi/advance `changes` bằng grouped typed mutation. Decision cũ bị thay không bị silent rewrite; advance `active -> superseded` + `superseded_by`.

SQLite user-scope dùng atomic transaction + optimistic revision. Storage vẫn one canonical `document_json`/whole Work Item revision; bounded reads và incremental mutation không tạo chunk/event store hoặc per-record revision model.

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

### Progressive disclosure invariant

```text
knowledge_search(limit <= 10)
→ bounded decision cards
→ chọn exact target
→ smallest sufficient exact read:
     knowledge_read | knowledge_read_metadata | knowledge_read_section
→ whole/partial mutation
```

Search card không chứa full content, sources, revision hoặc physical path. `knowledge_search` dùng để chọn candidate; material use/update phải exact-read sufficient scope.

- **MUST search** khi prior reusable knowledge có thể đổi interpretation, orchestration, implementation hoặc verification.
- **MAY search** khi query ngắn có thể giảm uncertainty/lặp investigation.
- **SKIP** cho mechanical/exact-local/status-only work nơi durable context không thể đổi action.
- **MUST review/mutate** cho substantive work có khả năng tạo/xác nhận reusable conclusion.
- `knowledge_write(entries=[])` chỉ dùng sau required review không có candidate.
- Trước create/update phải search existing concept; update existing target phải exact-read sufficient scope trước.

`knowledge_write` giữ create + intentional whole-document replacement. `knowledge_update` cho metadata-only, whole-content-only hoặc one-existing-section mutation mà caller không resend untouched document state.

Stable semantic section marker là optional address bên trong cùng canonical Markdown document. Section ID lowercase kebab-case, unique, marker đứng ngay trước H2-H6 heading; partial section update chỉ replace existing section body. Không có per-section revision/chunk store/implicit section create. Whole document vẫn có one SHA-256 revision và mọi mutation cạnh tranh trên revision đó.

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
3. QiQi `work_item_get` bounded current state trước orchestration và sau repo turn khi task thuộc Work Item; scoped history chỉ khi decision/provenance cần.
4. Work Item mutation dùng grouped typed incremental operations trong `$work-item`; workspace policy không duplicate operation mechanics.
5. TaskPacket identify Work Item + revision; external fact ngoài Work Item mà QiQi dùng cho semantics vẫn phải inline với provenance.
6. `SYSTEM_MAP.md` vẫn là live topology artifact; Work Item không thay System Map.
7. Workspace Knowledge policy phải dùng search-first/exact-scoped-read progressive disclosure; search không cấp revision.
8. Native result capture giữ exact final response, không fixed schema/viewport/transcript fallback.
9. Architecture/runtime/public MCP contract change phải cập nhật checker + docs + migration.

## Khi thay đổi Repository Template

1. Giữ Git-root boundary và cấm đọc/sửa sibling source/runtime state.
2. Work Item MCP là task-state tool exception; Knowledge MCP là reusable-context tool exception; cả hai không phải filesystem exception.
3. Nếu TaskPacket identify Work Item, child `work_item_get` bounded current state trước substantive work; scoped history only when needed; chỉ update evidence/state thuộc current repo bằng grouped typed incremental mutation trong authority.
4. Search cards chỉ dùng chọn knowledge document; material use/update phải exact-read sufficient semantic scope.
5. Live owner source/test thắng stale shared knowledge.
6. Cross-repo remaining work quay lại QiQi; child không tự sửa/delegate sibling repo.
7. Không thêm repo-local task store, knowledge store hoặc fixed result headings.

## Khi thay đổi Work Item Template

1. Giữ one canonical task store independent workspace/repo/CWD.
2. MVP API nhỏ: bounded get + scoped history read + list/create + one typed update tool.
3. `expected_revision` là mandatory mutation concurrency boundary; history cursor cũng bind exact whole Work Item revision.
4. Internal raw canonical document và public read models là boundary riêng: GET chỉ current projection; history read một collection/call.
5. Public update model phải tách `WorkItemStatePatch` khỏi semantic operations; historical collections không được quay lại full-array replacement schema.
6. `mutation.operations` phải là grouped typed object với five stable-id lifecycle upsert groups + checkpoint append group; không quay lại nested `{op,value}` union/list; max 50 semantic records tổng cộng/call.
7. Cross-group caller order không phải public semantics; mọi groups build one final candidate và cross-record refs validate trên final candidate. Preserve order bên trong group khi material.
8. Stable-id lifecycle monotonic, semantic identity/provenance không arbitrary rewrite, duplicate target reject.
9. Update success phải compact bounded receipt; mutation không hydrate full Work Item/history sau commit.
10. Concurrent writers từ cùng revision không được cùng commit; mutation engine không auto-rebase stale mutations; history pagination không mix revisions.
11. Validation reject malformed semantic objects, invalid collection filters và immutable metadata/provenance changes.
12. Không biến Work Item thành activity transcript, reusable knowledge store hoặc chunk/event store để phục vụ read/write projection.
13. Fresh-session smoke phải chứng minh QiQi và repo child continue từ bounded current state và grouped incremental update, chỉ history-read khi cần provenance, và successful happy path không dùng invalid schema-probing calls.

## Khi thay đổi Knowledge Template

1. Search và exact read là các stage riêng; search không trả revision/content.
2. Full read bounded; scoped metadata/section reads không hydrate untouched large content vào agent response.
3. Store vẫn one canonical Markdown document/concept với one SHA-256 revision; partial mutation không tạo persistence/revision model thứ hai.
4. `knowledge_update` phải reconstruct canonical full semantic payload server-side và reuse existing whole-document write/lock/index/revision path.
5. Stable section marker phải deterministic, unique và không cho implicit add/delete/reorder qua section replace.
6. Store independent workspace/repo/CWD; agent-facing schema không expose arbitrary filesystem path.
7. Retrieval deterministic/index-first; repo/domain context chỉ boost semantic match đã có.
8. Update dùng optimistic whole-document revision; external edit không silent overwrite.
9. `sources` bắt buộc cho durable fact; hypothesis chưa verified không persist như fact.
10. Tests cover thin search cards, scoped/full exact reads, partial/full update preservation, stale index/revision, concurrency và section validation.

## Migration

Public contract change phải có migration cho workspace/repo đã tồn tại. Migration framework dùng per-file `replace`, `merge`, `delete`, `manual_review`, pin exact `from_ref`/`to_ref`, preflight trước mutate và lưu migration state dưới `.qiqi/`.

Global Work Item migration phải đứng sau Knowledge progressive-disclosure migration hiện tại; không tự ghi user MCP config. Operator cài/refresh `work_item` user scope explicitly từ `work-item-template/` để fresh session discover bounded GET/history + grouped typed incremental update. Canonical DB lifecycle migration chạy trong Work Item core bằng `PRAGMA user_version`, không tạo task store thứ hai.

## Review tối thiểu

Review phải xác nhận:

- bốn nguồn truth không bị trộn;
- Global Work Item là canonical mutable task state duy nhất;
- QiQi và child dùng bounded current Work Item state mặc định và scoped exact history on demand;
- default GET không tăng tuyến tính theo accumulated resolved/checkpoint history;
- history cursor bind Work Item id/filter/revision deterministic và không mix revisions;
- historical full-array mutation không representable qua public schema;
- old `{op,value}` operation-list shape không representable qua public schema;
- grouped semantic mutation không hydrate/resend accumulated history;
- stable-id lifecycle/identity/provenance guards không cho silent historical rewrite;
- grouped mutations validate final candidate và không expose cross-group caller-order dependency;
- stale/concurrent Work Item update vẫn conflict trên whole Work Item revision;
- mutation success trả compact receipt, không full canonical document;
- fresh-agent happy path không cần intentionally-invalid schema discovery calls;
- Q&A/decision/requirement changes đủ để resume không hỏi lại;
- Knowledge search result thin, exact read bounded và revision chỉ đến từ exact read surface;
- Knowledge partial update preserve untouched canonical state và vẫn dùng one whole-document revision;
- native response round-trip không viewport/truncation dependency;
- docs/checkers/migration phản ánh cùng architecture;
- static/unit tests không được dùng để tuyên bố native CLI/user-MCP fresh-session smoke đã pass.
