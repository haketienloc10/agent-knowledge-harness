# AGENTS.md

Repo này phát triển hai template phối hợp trong multi-repository workspace:

- `workspace-template/`: QiQi Chief of Staff control plane, synchronous Herdr-backed
  MCP delegation, task continuity và cross-repo knowledge;
- `repo-template/`: workflow tối thiểu cho execution agent trong từng Git
  repository con.

Repo không chứa tri thức nghiệp vụ thật của một workspace cụ thể.

## Nguyên tắc

- QiQi là Chief of Staff/coordinator, không phải coding agent của repo con.
- Mọi repo-local work từ QiQi đi qua đúng một MCP tool: `delegate_repo_task`.
- Public tool signature là `delegate_repo_task(repository, task, route, session_id?)`.
- `task` semantics và execution prompt thuộc QiQi; MCP không reinterpret task.
- Với START, dòng không rỗng đầu tiên của `task` là English task title ngắn; MCP
  derive readable `<english-task-slug>` từ dòng này cho final result filename.
- RESUME không rename artifact; nó giữ exact `result_path` được START tạo.
- MCP chỉ append result-handoff protocol cần cho durable Markdown artifact.
- Success return chỉ gồm native `session_id` và workspace-relative `result_path`.
- QiQi phải đọc `result_path` trước khi quyết định bước tiếp; không RESUME chỉ để
  yêu cầu agent lặp lại report.
- START và RESUME dùng cùng tool; native `session_id` là optional argument, không
  có separate resume tool.
- `workspace-template/instructions/model-routing.md` chỉ sở hữu policy chọn exact
  route; không duplicate model ID hoặc native CLI flags.
- `workspace-template/instructions/agent-routing.yaml` là canonical runtime route
  registry duy nhất MCP load và sở hữu agent/model/native flags + START/RESUME argv.
- Routing examples nằm dưới `workspace-template/docs/examples/`, chỉ dùng làm tài
  liệu tham khảo và không phải runtime input.
- MCP chạy real interactive Codex/Claude qua Herdr; Herdr lifecycle là internal
  implementation detail, không phải public orchestration API của QiQi.
- Không expose progress/status/wait/read/transcript/list-runs tool.
- Independent Git roots có thể chạy đồng thời; trong cùng `qiqi_delegate` server
  process, cùng resolved Git root hoặc cùng native session bị reject.
- Dependency/shared mutable resource do QiQi lập kế hoạch; khi không chắc conflict
  thì chạy tuần tự.
- Trong delegation wave, QiQi áp dụng Delegation Silence và không poll child state.
- Repository con sở hữu architecture/domain/implementation/verification nội bộ.
- Workspace sở hữu registry/topology/task context/result handoff/cross-repo knowledge.
- Repo agent không promote workspace knowledge trực tiếp; nó chỉ báo cross-repo
  impact trong result artifact.
- Ưu tiên artifact nhỏ, source of truth rõ và evidence có thể kiểm tra.

## Contract Result Artifact

Mỗi native session có một durable artifact:

```text
.qiqi/runs/<repo>-<english-task-slug>-<native-session-id>.md
```

`<english-task-slug>` được derive từ dòng không rỗng đầu tiên của START `task`,
được QiQi viết thành English title ngắn, ưu tiên ASCII. Phần instruction còn lại
có thể dùng ngôn ngữ khác. START tạo pending artifact rồi promote sau khi native
identity có sẵn. RESUME append `Task N / Result N` vào exact artifact của session.

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

Tool return không duplicate nội dung report; caller đọc `result_path` để reconcile.

## Khi thay đổi Workspace Template

1. Giữ `AGENTS.md`, `identity.md`, `README.md`, setup guide, model routing, agent
   routing, MCP server và checker đồng bộ cùng execution contract.
2. Giữ đúng một public MCP tool; không thêm delegation path thứ hai bằng shell,
   daemon hoặc session manager.
3. Không thêm public `status`, `wait`, `read`, `read_transcript`, `list_runs` hay
   separate `resume` tool.
4. Giữ full interactive agent TUI bên trong Herdr; không thay bằng hidden child
   runner chỉ để lấy output máy đọc.
5. QiQi phải sở hữu task semantics; MCP footer chỉ sở hữu result handoff.
6. START task title phải giữ English result-slug convention; không thêm translator
   hoặc đổi public MCP schema chỉ để đặt filename.
7. Repository phải resolve từ `repos.yaml` và path phải là exact Git root.
8. Không cho nhiều registry entry cùng resolve về một Git root.
9. `instructions/agent-routing.yaml` là canonical runtime registry duy nhất; route
   registry sở hữu command/model/flags và runtime placeholders `{model}`,
   `{session_id}`, `{result_dir}`, `{route_args}`.
10. `instructions/model-routing.md` chỉ mô tả khi nào QiQi chọn exact route; không
    copy machine configuration vào policy này.
11. Routing examples phải nằm dưới `docs/examples/`, ghi rõ documentation-only và
    không được coi là route khả dụng nếu chưa copy/adapt vào canonical registry.
12. Native resume phải kiểm tra identity: ID report lại phải khớp ID yêu cầu.
13. Concurrency guard phải resource-scoped trong một `qiqi_delegate` server
    process: same Git root hoặc same native session bị reject ngay; không global
    delegation lock và không silently queue same-repo calls.
14. Tool success chỉ trả `session_id` + `result_path`; QiQi đọc artifact thay vì
    mở RESUME turn chỉ để lấy report.
15. Nếu thay đổi artifact/runtime bắt buộc, cập nhật checker + docs trong cùng PR.
16. Herdr integration install là setup concern; MCP chỉ preflight selected adapter
    ở trạng thái `current`.
17. Không thêm lại Codex hook-trust bypass nếu không có quyết định mới rõ ràng.

## Khi thay đổi Repository Template

1. Giữ template tối thiểu và không tạo artifact optional rỗng.
2. Không đưa workspace orchestration, Herdr control plane hoặc cross-repo knowledge
   store xuống repo con.
3. Bảo vệ Git-root boundary và cấm agent sửa repository anh em.
4. Cho phép đúng một exception ngoài Git root: exact `.qiqi/runs/...md` result
   artifact được MCP handoff trong prompt của turn hiện tại.
5. Repo-local knowledge cập nhật tại source of truth của repo sở hữu.
6. Cross-repo impact được báo qua result artifact; repo agent không promote
   workspace knowledge trực tiếp.
7. Final result contract phải dùng Markdown headings mà MCP validator yêu cầu.

## Review tối thiểu

Review phải xác nhận:

- workspace template chỉ expose `delegate_repo_task`;
- public signature không đổi ngoài quyết định có chủ đích;
- QiQi-owned prompt + MCP-owned result footer boundary được giữ;
- START task first line tạo readable English result slug và RESUME giữ cùng path;
- `model-routing.md` chỉ là exact-route policy;
- `agent-routing.yaml` là canonical runtime routing source of truth duy nhất;
- routing examples chỉ nằm trong `docs/examples/` và không bị hiểu là active routes;
- Codex/Claude đều chạy interactive qua Herdr;
- native session ID được lấy qua Herdr integration và RESUME identity được kiểm tra;
- START/RESUME dùng durable session artifact và RESUME append cùng path;
- success return chỉ có `session_id` + `result_path`;
- caller policy yêu cầu đọc artifact và cấm report-only RESUME;
- same Git root/native session conflict bị reject trong cùng server process;
- different independent Git roots vẫn có thể active đồng thời;
- Claude stalled-prompt recovery không paste prompt lần hai;
- transcript không trở thành tool result;
- checker kiểm đúng contract hiện tại, không giữ assertion của architecture cũ;
- README/setup/examples phản ánh đúng routing và Herdr requirements;
- workspace/repo-local knowledge boundary không bị phá vỡ.