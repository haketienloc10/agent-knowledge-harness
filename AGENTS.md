# AGENTS.md

Repo này phát triển ba template phối hợp nhưng giữ boundary độc lập:

- `workspace-template/`: QiQi Chief of Staff control plane và synchronous
  Herdr-backed repo delegation;
- `repo-template/`: workflow tối thiểu cho execution agent trong từng Git
  repository con;
- `knowledge-template/`: Shared Knowledge Store + user-scoped Knowledge MCP độc lập
  với current workspace/repository.

Repo không chứa tri thức nghiệp vụ thật của một workspace cụ thể.

## Nguyên tắc

- QiQi là Chief of Staff/coordinator, không phải coding agent của repo con.
- Mọi repo-local work từ QiQi đi qua đúng một MCP tool: `delegate_repo_task`.
- Input delegation là TaskPacket có cấu trúc, giữ original `user_request`, repo-local
  `objective`, scope, required context + provenance, constraints, acceptance,
  verification và known unknowns.
- Execution agent không chia sẻ hidden conversation/workspace/sibling context của
  QiQi. External fact nào QiQi đã dùng để quyết định task semantics phải được inline
  vào `required_context`; child Knowledge MCP không thay thế required input.
- Output semantic của delegation là exact native final `agent_response` được MCP
  capture qua native Stop hook; không ép fixed headings và không dùng agent-written
  Markdown result artifact làm transport.
- MCP-owned SQLite giữ runtime session/turn ownership; QiQi/child không đọc/sửa
  database này trực tiếp.
- QiQi là handoff broker duy nhất của **live execution evidence** giữa repositories:
  producer response được QiQi đọc/reconcile rồi relevant fact/evidence được truyền
  vào downstream `required_context`.
- Shared durable knowledge đi qua `knowledge_read` / `knowledge_write` và có thể
  được QiQi hoặc execution agent đọc trực tiếp; current repo chỉ là ranking hint,
  không phải permission boundary của knowledge.
- Knowledge MCP là conditional context/persistence path, không phải ceremony bắt
  buộc cho mọi turn.
- Trước create/update knowledge candidate, agent phải search existing concept để
  dedupe và ưu tiên update; `entries=[]` chỉ dùng khi một required knowledge review
  đã diễn ra nhưng không còn durable candidate.
- Child agent không tự đọc sibling repository source hoặc sibling runtime/result
  history.
- Product/workspace repositories giữ live source/test/topology truth; Shared
  Knowledge Store giữ reusable distilled knowledge. Khi conflict ở owner repo,
  live source/test hiện tại thắng.
- Agent không sở hữu knowledge filename/path/directory. Agent submit semantic
  knowledge; Knowledge MCP sở hữu ID/path/render/index/locking/revision/persistence.
- Human được phép sửa Shared Knowledge Markdown trực tiếp nếu tuân thủ schema rồi
  chạy `knowledge check`/`knowledge reindex`.
- Knowledge routing metadata dùng canonical concepts (thường English), aliases có
  thể multilingual; content tự do và không có field `language`.
- Không đưa vector DB, embedding, translation hoặc LLM vào Knowledge MCP MVP.
- Ưu tiên artifact nhỏ, source of truth rõ và evidence có thể kiểm tra.

## qiqi_delegate contract

`workspace-template/mcp/qiqi_delegate` sở hữu execution lifecycle, native session,
result capture, runtime state và cleanup. START/RESUME dùng cùng tool.

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

Success trả:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled | failed",
  "agent_response": "<exact native final assistant message>"
}
```

QiQi phải đọc toàn bộ `agent_response` trước bước tiếp theo và đánh giá completion
bằng TaskPacket + evidence. Một agent response không bị ép tự khai `Outcome` hoặc
các heading implementation-specific.

Native response transport phải **fail closed**: nếu Stop hook không trả final
message hợp lệ, không fallback sang terminal screen, pane scrollback, transcript
parsing hay một report Markdown khác.

`.qiqi/state/qiqi_delegate.sqlite3` là MCP-owned runtime state. `.qiqi/runs/` chỉ
có thể được dùng như legacy ownership-import bridge cho session tạo trước migration;
new turn không dùng Markdown artifact làm transport/history.

## Shared Knowledge contract

Public MVP tools:

```text
knowledge_read(keywords, context?, limit?)
knowledge_write(entries)
```

Store là Markdown + generated `INDEX.md` với namespaces:

```text
global/
systems/
repos/
domains/
```

Identity:

```text
<scope-kind>:<scope-id>:<canonical-name>
```

Create không nhận filesystem path. Update bắt buộc exact ID + optimistic revision.
Detail document là canonical metadata source; `INDEX.md` là generated routing
projection. Human direct edit làm index stale cho tới khi reindex; read phải fail
rõ thay vì silently dùng stale index.

Knowledge write phải giữ cross-process lock, atomic file replace, revision conflict
check và bounded document size. Semantic merge/dedupe vẫn thuộc agent/skill, không
thuộc MCP core.

### Usage decision invariant

Template policy phải phân biệt rõ:

- **MUST read** khi prior reusable knowledge có khả năng đổi interpretation,
  orchestration, implementation hoặc verification: domain rule/invariant,
  architecture/ownership/decision, API/event/schema/auth/security contract,
  deployment/runtime constraint, recurring issue/pitfall hoặc explicit request dùng
  shared knowledge.
- **MAY read** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp.
- **SKIP read** cho typo/format/comment-only, exact local lookup, report/status-only
  từ evidence đã đủ, hoặc mechanical work nơi durable context không thể đổi hành
  động hợp lý.
- QiQi không cần duplicate repo-agent knowledge query nếu knowledge chỉ có thể ảnh
  hưởng repo-local implementation và không ảnh hưởng orchestration/TaskPacket.
- Nếu QiQi đã dùng một returned knowledge fact làm required premise cho delegation,
  fact đó phải được inline vào `required_context` với Knowledge ID/revision hoặc
  provenance phù hợp; không buộc child tìm lại premise.
- **MUST review/write** cho substantive work có khả năng tạo/xác nhận reusable
  conclusion; trivial/mechanical/report-only work được skip write hoàn toàn.
- `knowledge_write(entries=[])` không phải no-op ritual; chỉ dùng sau required review
  khi không có durable candidate.
- Trước mọi create/update candidate phải search existing concept và ưu tiên update
  để tránh duplicate.

## Khi thay đổi Workspace Template

1. Giữ QiQi task semantics, evidence-reuse gate, delegation waves và Delegation
   Silence không bị knowledge lifecycle làm loãng.
2. `workspace-template/.codex/config.toml` chỉ sở hữu project-scoped
   `qiqi_delegate`; không thêm project-specific Knowledge MCP store.
3. Shared Knowledge MCP phải được cài ở user/global scope để workspace agent và
   Herdr-launched child agents dùng cùng service independent CWD.
4. Live producer result vẫn phải đi qua QiQi vào downstream `required_context`;
   không thay bằng việc child tự đọc sibling source/runtime state.
5. `SYSTEM_MAP.md` vẫn là live workspace topology artifact, không tự động chuyển
   vào Shared Knowledge Store.
6. Workspace `AGENTS.md` phải giữ conditional Knowledge MCP decision rule; không
   biến read/write thành thao tác vô điều kiện cho mọi turn.
7. Structured TaskPacket phải giữ original user request và closed-world context
   boundary; không quay lại opaque prompt-only contract.
8. Native result capture phải giữ exact final response, không fixed result schema,
   viewport scraping hay transcript parsing fallback.
9. Nếu thay đổi execution/runtime bắt buộc, cập nhật checker + docs trong cùng PR.

## Khi thay đổi Repository Template

1. Giữ Git-root boundary và cấm sửa/đọc sibling repository source.
2. Knowledge MCP là tool exception, không phải filesystem exception.
3. Agent hiểu task trước rồi áp dụng Knowledge MCP decision rule; non-trivial không
   tự động đồng nghĩa phải query nếu durable context không thể thay đổi cách làm.
4. Live owner source/test thắng shared knowledge khi conflict; verified reusable
   conclusion mới phải update shared knowledge khi thích hợp.
5. Substantive work phải knowledge review/write; trivial/mechanical/report-only work
   có thể skip. Required review không có candidate mới dùng `entries=[]`.
6. Cross-repo impact vẫn phải được handoff trong native final response nếu
   repository khác cần work, kể cả durable knowledge đã persist.
7. Repo policy không được yêu cầu agent ghi QiQi result artifact hoặc fixed result
   headings.
8. Không thêm knowledge directory/index riêng vào repo template.

## Khi thay đổi Knowledge Template

1. Giữ store độc lập với current workspace/repo và không infer root từ CWD.
2. Agent-facing write schema không expose filename/path/directory/index path.
3. Identity và canonical path phải deterministic từ semantic scope/name.
4. `INDEX.md` được generate từ detail metadata; không tạo hai source of truth.
5. Human-authored Markdown là first-class workflow; checker/reindex dùng cùng core
   với MCP.
6. Retrieval deterministic/index-first; context repo/domain chỉ boost ranking.
7. Update dùng optimistic revision; human external edit không được silent overwrite.
8. Không thêm `language` field; routing aliases xử lý multilingual terminology.
9. `sources` bắt buộc cho durable knowledge; guess/hypothesis chưa verified không
   được persist như fact.
10. Unit/integrity tests phải bao phủ create/update, stale index, concurrent revision,
    canonical path/traversal, multilingual alias, empty review và batch failure.
11. Agent-facing schema/error phải đủ discoverable để normal usage không phụ thuộc
    repeated trial-and-error.

## Review tối thiểu

Review phải xác nhận cả ba lớp:

- qiqi_delegate public contract dùng structured TaskPacket và exact native final
  response;
- QiQi vẫn broker live upstream → downstream handoff và evidence reuse vẫn trực tiếp
  answer khi result hiện có đủ;
- material finding/evidence/caveat của single-agent response không bị QiQi summarize
  mất chỉ vì format;
- child không tự đọc sibling source/runtime result state;
- native handoff dài hơn viewport vẫn round-trip và missing hook fail closed;
- runtime SQLite được gitignore và không trở thành semantic truth store;
- Knowledge MCP user/global registration không phụ thuộc repo CWD;
- Knowledge MCP chỉ expose read/write tools và không expose filesystem decisions;
- root/workspace/repo AGENTS giữ conditional usage policy và không bắt read/write
  như ceremony ở task trivial;
- direct human Markdown edit + reindex/check hoạt động;
- stale revision/index bị reject rõ;
- content language không ảnh hưởng identity/path và không có `language` field;
- legacy workspace `knowledge/` store không còn trong workspace template;
- docs/checkers phản ánh đúng architecture hiện tại.
