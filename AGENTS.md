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
- Mọi repo-local work từ QiQi đi qua đúng một MCP tool:
  `delegate_repo_task(repository, task, route, session_id?)`.
- QiQi là handoff broker duy nhất của **live execution evidence** giữa repositories:
  producer result được QiQi đọc/chắt lọc rồi truyền vào downstream task prompt.
- Shared durable knowledge đi qua `knowledge_read` / `knowledge_write` và có thể
  được QiQi hoặc execution agent đọc trực tiếp; current repo chỉ là ranking hint,
  không phải permission boundary của knowledge.
- Knowledge MCP là conditional context/persistence path, không phải ceremony bắt
  buộc cho mọi turn: agent read khi prior durable knowledge có khả năng thay đổi
  quyết định/cách làm, và review/write cho substantive work có khả năng tạo reusable
  conclusion.
- Trước create/update knowledge candidate, agent phải search existing concept để
  dedupe và ưu tiên update; `entries=[]` chỉ dùng khi một required knowledge review
  đã diễn ra nhưng không còn durable candidate.
- Child agent không tự đọc sibling repository source hoặc sibling result artifact.
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

`workspace-template/mcp/qiqi_delegate` vẫn chỉ sở hữu execution/session/result
handoff. START/RESUME dùng cùng tool, success return chỉ có native `session_id` và
workspace-relative `result_path`; QiQi phải đọc artifact trước bước tiếp theo.

Current result headings vẫn giữ compatibility:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

`### Repo-local Knowledge` là legacy label trong result protocol. Dưới architecture
mới, repo policy dùng section này để ghi Shared Knowledge MCP IDs create/update,
`None`, hoặc persistence failure; nó không yêu cầu repo-local knowledge document.
`### Cross-repo Impact` tiếp tục là live execution-impact signal cho QiQi.

Không đổi qiqi result protocol trong cùng migration Knowledge MCP trừ khi có quyết
định compatibility riêng.

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
  hưởng repo-local implementation và không ảnh hưởng orchestration/task prompt.
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
4. Live producer result vẫn phải đi qua QiQi vào consumer prompt; không thay bằng
   việc child tự đọc sibling result/source.
5. `SYSTEM_MAP.md` vẫn là live workspace topology artifact, không tự động chuyển
   vào Shared Knowledge Store.
6. Workspace `AGENTS.md` phải giữ conditional Knowledge MCP decision rule; không
   biến read/write thành thao tác vô điều kiện cho mọi turn.
7. Nếu thay đổi artifact/runtime bắt buộc, cập nhật checker + docs trong cùng PR.

## Khi thay đổi Repository Template

1. Giữ Git-root boundary và cấm sửa/đọc sibling repository source.
2. Knowledge MCP là tool exception, không phải filesystem exception.
3. Agent hiểu task trước rồi áp dụng Knowledge MCP decision rule; non-trivial không
   tự động đồng nghĩa phải query nếu durable context không thể thay đổi cách làm.
4. Live owner source/test thắng shared knowledge khi conflict; verified reusable
   conclusion mới phải update shared knowledge khi thích hợp.
5. Substantive work phải knowledge review/write; trivial/mechanical/report-only work
   có thể skip. Required review không có candidate mới dùng `entries=[]`.
6. Cross-repo Impact vẫn phải handoff nếu repository khác cần work, kể cả durable
   knowledge đã được persist.
7. Không thêm knowledge directory/index riêng vào repo template.

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

- qiqi_delegate public execution contract không bị knowledge service reinterpret;
- QiQi vẫn broker live upstream → downstream handoff và evidence reuse vẫn trực tiếp
  answer khi result hiện có đủ;
- child không tự đọc sibling source/result;
- Knowledge MCP user/global registration không phụ thuộc repo CWD;
- Knowledge MCP chỉ expose read/write tools và không expose filesystem decisions;
- root/workspace/repo AGENTS giữ conditional usage policy và không bắt read/write
  như ceremony ở task trivial;
- direct human Markdown edit + reindex/check hoạt động;
- stale revision/index bị reject rõ;
- content language không ảnh hưởng identity/path và không có `language` field;
- legacy workspace `knowledge/` store không còn trong workspace template;
- docs/checkers phản ánh đúng architecture hiện tại, không giữ knowledge lifecycle cũ.
