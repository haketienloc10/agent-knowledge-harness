# AGENTS.md

Repo này phát triển hai template phối hợp trong multi-repository workspace:

- `workspace-template/`: QiQi Chief of Staff control plane, synchronous Herdr-backed
  MCP delegation, shared Knowledge MCP client/runtime setup và result handoff;
- `repo-template/`: workflow tối thiểu cho execution agent trong từng Git
  repository con.

Repo không chứa dữ liệu nghiệp vụ thật của một workspace cụ thể.

## Nguyên tắc

- QiQi là Chief of Staff/coordinator, không phải coding agent của repo con.
- Mọi repo-local execution từ QiQi đi qua đúng một MCP tool: `delegate_repo_task`.
- Public execution signature là `delegate_repo_task(repository, task, route, session_id?)`.
- Shared durable knowledge đi qua MCP riêng với đúng hai public tools:
  `knowledge_read(keywords, context?, limit?)` và `knowledge_write(entries)`.
- Knowledge Store độc lập với workspace, repository và caller CWD; location đến từ
  `QIQI_KNOWLEDGE_ROOT` và MCP được đăng ký ở user scope để QiQi/child cùng thấy.
- Agent submit semantic knowledge, không submit `filename`, storage `path`,
  `directory` hoặc `index_path`; Knowledge MCP sở hữu canonical ID/path, mkdir,
  Markdown rendering, locking, optimistic revision và `INDEX.md` update.
- Knowledge document không có field `language`; routing metadata dùng canonical
  concepts, aliases có thể đa ngôn ngữ và content dùng ngôn ngữ tùy ý.
- Detail document metadata là canonical source; `INDEX.md` chỉ là materialized
  read-routing index và có thể regenerate từ detail documents.
- Shared knowledge là durable reusable context, không mạnh hơn live owner-repo
  source/test. Khi mâu thuẫn được xác minh ở owner repo, live source/test thắng.
- `task` semantics và execution prompt thuộc QiQi; delegation MCP không reinterpret task.
- QiQi là handoff broker duy nhất giữa các repository cho live execution result:
  upstream result được QiQi đọc, chắt lọc rồi truyền vào downstream task prompt.
- Knowledge MCP là broker của durable reusable knowledge; repo agent được query
  shared knowledge nhưng không tự đọc sibling repository source hoặc sibling result.
- Với START, dòng không rỗng đầu tiên của `task` là English task title ngắn; MCP
  derive readable `<english-task-slug>` từ dòng này cho final result filename.
- RESUME không rename artifact; nó giữ exact `result_path` được START tạo.
- Delegation MCP chỉ append result-handoff protocol cần cho durable Markdown artifact.
- Success return chỉ gồm native `session_id` và workspace-relative `result_path`.
- QiQi phải đọc `result_path` trước khi quyết định bước tiếp; không RESUME chỉ để
  yêu cầu agent lặp lại report.
- START và RESUME dùng cùng tool; native `session_id` là optional argument, không
  có separate resume tool.
- `workspace-template/instructions/model-routing.md` chỉ sở hữu policy chọn exact
  route; không duplicate model ID hoặc native CLI flags.
- `workspace-template/instructions/agent-routing.yaml` là canonical runtime route
  registry duy nhất delegation MCP load và sở hữu agent/model/native flags +
  START/RESUME argv.
- Routing examples nằm dưới `workspace-template/docs/examples/`, chỉ dùng làm tài
  liệu tham khảo và không phải runtime input.
- Delegation MCP chạy real interactive Codex/Claude qua Herdr; Herdr lifecycle là
  internal implementation detail, không phải public orchestration API của QiQi.
- Không expose progress/status/wait/read/transcript/list-runs execution tool.
- Independent Git roots có thể chạy đồng thời; trong cùng `qiqi_delegate` server
  process, cùng resolved Git root hoặc cùng native session bị reject.
- Dependency/shared mutable resource do QiQi lập kế hoạch; khi không chắc conflict
  thì chạy tuần tự.
- Trong delegation wave, QiQi áp dụng Delegation Silence và không poll child state.
- Repository con sở hữu architecture/domain/implementation/verification nội bộ.
- Workspace sở hữu registry/topology/orchestration/result handoff.

## Contract Result Artifact

Mỗi native session có một durable artifact:

```text
.qiqi/runs/<repo>-<english-task-slug>-<native-session-id>.md
```

Newest result bắt buộc có headings theo thứ tự:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

`Outcome` là `completed` hoặc `blocked`.

`### Repo-local Knowledge` hiện là compatibility heading của result protocol, không
phải repo-local knowledge store cũ. Repo policy dùng nó làm audit ngắn cho shared
knowledge review/update (`None` hoặc shared knowledge IDs/revisions).
`### Cross-repo Impact` là outbound **execution** handoff cho QiQi; không dùng nó
làm knowledge transport.

## Workflow Hai chiều

```text
QiQi knowledge_read + workspace context
→ self-contained task prompt cho repo A
→ repo A knowledge_read + work + knowledge_write
→ repo A terminal result
→ QiQi reconcile live Cross-repo Impact
→ relevant live fact/evidence trong prompt repo B
→ repo B knowledge_read + work + knowledge_write
→ repo B terminal result
→ QiQi reconcile + orchestration-level knowledge review/write
```

Child agents không handoff trực tiếp cho nhau. `.qiqi/runs/` là live execution
handoff về QiQi, không phải shared mailbox. Durable reusable knowledge đi qua
Knowledge MCP.

## Khi thay đổi Shared Knowledge

1. Giữ Knowledge MCP là server riêng với đúng `knowledge_read` + `knowledge_write`;
   không nhét knowledge tools vào `qiqi_delegate`.
2. Store root phải đến từ `QIQI_KNOWLEDGE_ROOT`, không derive từ CWD, `repos.yaml`
   hoặc current Git root.
3. Knowledge MCP registration cho Codex/Claude thuộc user scope; không thêm nó vào
   workspace project `.codex/config.toml` nơi chỉ expose `qiqi_delegate`.
4. Không thêm `language` field. Routing metadata/canonical names dùng canonical
   terminology; aliases có thể đa ngôn ngữ; body tự do ngôn ngữ.
5. Không expose filesystem-placement fields trong semantic create/update contract.
   Core phải reject unsupported fields thay vì silently ignore.
6. Human edit là first-class: canonical detail Markdown có thể sửa trực tiếp rồi
   `reindex`/`check`; `INDEX.md` không phải canonical metadata source.
7. Update phải dùng `id` + `expected_revision`; stale writes bị reject.
8. Shared store write phải dùng cross-process locking và atomic replacement.
9. Retrieval MVP deterministic/lexical từ INDEX metadata; không thêm vector DB,
   embedding, translation hoặc LLM trong MCP khi chưa có requirement mới.
10. Live owner-repo source/test luôn có thể supersede stale shared knowledge.
11. Cập nhật `docs/KNOWLEDGE_STORE.md`, Knowledge MCP tests/checker và agent policies
    trong cùng thay đổi khi public contract đổi.

## Khi thay đổi Workspace Template

1. Giữ `AGENTS.md`, `identity.md`, `README.md`, setup guides, model routing, agent
   routing, MCP servers và checkers đồng bộ cùng workflow.
2. Giữ đúng một public **execution** MCP tool; không thêm delegation path thứ hai
   bằng shell, daemon hoặc session manager.
3. Không thêm public execution `status`, `wait`, `read`, `read_transcript`,
   `list_runs` hay separate `resume` tool.
4. Giữ full interactive agent TUI bên trong Herdr; không thay bằng hidden child
   runner chỉ để lấy output máy đọc.
5. QiQi phải sở hữu task semantics và live cross-repo handoff context; execution
   MCP footer chỉ sở hữu result handoff.
6. START task title phải giữ English result-slug convention.
7. Repository phải resolve từ `repos.yaml` và path phải là exact Git root.
8. Không cho nhiều registry entry cùng resolve về một Git root.
9. `instructions/agent-routing.yaml` là canonical runtime execution registry duy nhất.
10. Native resume phải kiểm tra identity: ID report lại phải khớp ID yêu cầu.
11. Concurrency guard phải resource-scoped trong một `qiqi_delegate` server process.
12. Tool success chỉ trả `session_id` + `result_path`; QiQi đọc artifact thay vì
    mở RESUME turn chỉ để lấy report.
13. Nếu thay đổi artifact/runtime bắt buộc, cập nhật checker + docs trong cùng PR.

## Khi thay đổi Repository Template

1. Giữ template tối thiểu và không tạo artifact optional rỗng chỉ để chứa knowledge.
2. Không đưa workspace orchestration hoặc Herdr control plane xuống repo con.
3. Bảo vệ Git-root boundary và cấm agent sửa repository anh em.
4. Cho phép đúng một filesystem exception ngoài Git root: exact `.qiqi/runs/...md`
   result artifact được MCP handoff cho turn hiện tại. Shared knowledge được truy
   cập qua MCP, không direct filesystem traversal.
5. Upstream live result phải đến từ QiQi task prompt; child không tự đọc sibling
   result artifact hoặc sibling repository source.
6. Repo agent phải `knowledge_read` đầu work turn và `knowledge_write` trước finalize,
   kể cả `entries=[]` khi không có durable update.
7. Cross-repo impact được báo qua result artifact với fact, affected boundary,
   evidence và next action nếu rõ; repo agent không trực tiếp orchestration repo khác.

## Review tối thiểu

Review phải xác nhận:

- `qiqi_delegate` vẫn chỉ expose `delegate_repo_task`;
- Knowledge MCP expose đúng `knowledge_read` + `knowledge_write`;
- shared store độc lập CWD/repo và user-scope setup được document;
- agent không chọn storage path/directory/filename;
- `language` field không tồn tại;
- human edit + reindex/check hoạt động;
- revision conflict, canonical-path validation và unsupported storage field có test;
- QiQi-owned prompt + MCP-owned result footer boundary được giữ;
- QiQi broker live result; Knowledge MCP broker durable reusable knowledge;
- child không tự đọc sibling repository hoặc sibling result;
- START/RESUME/result/concurrency/Delegation Silence invariants không regression;
- README/setup/checkers phản ánh đúng cả execution và shared knowledge lifecycle.
