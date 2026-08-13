# AGENTS.md

Repo này phát triển hai template phối hợp trong multi-repository workspace:

- `workspace-template/`: QiQi Chief of Staff control plane, synchronous MCP
  delegation, task continuity và cross-repo knowledge;
- `repo-template/`: workflow tối thiểu cho execution agent trong từng Git
  repository con.

Repo không chứa tri thức nghiệp vụ thật của một workspace cụ thể.

## Nguyên tắc

- QiQi là Chief of Staff/coordinator, không phải coding agent của repo con.
- Mọi repo-local work từ QiQi đi qua đúng một MCP tool: `delegate_repo_task`.
- Mỗi tool call chỉ trả terminal structured result cùng native agent session ID;
  không expose progress, status, wait hoặc transcript.
- START và RESUME dùng cùng `delegate_repo_task`; native `session_id` là argument
  optional, không có separate resume tool.
- Agent/model/native flags và START/RESUME argv thuộc
  `workspace-template/instructions/agent-routing.yaml`, không hard-code trong QiQi
  prompt hoặc public MCP API.
- Các task độc lập trên resolved Git root khác nhau có thể được dispatch trong
  cùng delegation wave; cùng Git root hoặc cùng native session bị MCP chặn cứng.
- Dependency và shared mutable resource do QiQi lập kế hoạch; khi không chắc có
  conflict thì chạy tuần tự.
- Trong lúc delegation wave in-flight, QiQi áp dụng Delegation Silence: không phát
  user-visible progress commentary và không poll child state.
- Repository con sở hữu architecture, domain rule, implementation và
  verification nội bộ.
- Workspace sở hữu registry, topology, task context và tri thức cross-repo.
- Agent repo con không sửa workspace knowledge; nó chỉ trả cross-repo impact cho
  QiQi xử lý.
- Ưu tiên artifact nhỏ, source of truth rõ và evidence có thể kiểm tra.
- Không thêm daemon, watcher, status service hoặc observability primitive khi
  chưa có nhu cầu thực tế.

## Khi thay đổi Workspace Template

1. Giữ `AGENTS.md`, `identity.md`, agent routing, MCP server, setup guide, checker
   và README đồng bộ cùng execution contract.
2. Không thêm đường delegation thứ hai bằng shell hoặc session manager.
3. Không thêm `status`, `wait`, `read_transcript`, `list_runs` hoặc separate
   `resume` tool.
4. Child invocation phải non-interactive, không recursive delegation và không
   stream transcript về QiQi.
5. Repository phải được resolve từ `repos.yaml` và path phải là exact Git root.
6. Không cho nhiều registry entry cùng resolve về một Git root.
7. Route config sở hữu command/model/flags; MCP chỉ build argv, START/RESUME,
   extract native session ID và normalize result.
8. Native resume phải kiểm tra identity: session ID trả về phải khớp ID yêu cầu.
9. Concurrency guard phải resource-scoped: cùng resolved Git root hoặc cùng native
   session bị reject; không dùng global delegation lock.
10. Tool result contract phải đủ cho QiQi reconcile mà không tự vào repo kiểm tra.
11. Nếu thay đổi artifact bắt buộc, cập nhật checker và tài liệu setup cùng lúc.

## Khi thay đổi Repository Template

1. Giữ template tối thiểu và không tạo artifact optional rỗng.
2. Không đưa workspace orchestration, MCP server hoặc cross-repo knowledge store
   xuống repo con.
3. Bảo vệ Git-root boundary và cấm agent sửa repository anh em.
4. Repo-local knowledge phải cập nhật tại source of truth của repo sở hữu.
5. Cross-repo impact được trả về QiQi; repo agent không promote workspace
   knowledge trực tiếp.
6. Final result contract phải tương thích với `delegate_repo_task`.

## Kiểm tra

Review tối thiểu phải xác nhận:

- workspace template chỉ expose `delegate_repo_task` cho repo-local execution;
- `instructions/agent-routing.yaml` định nghĩa agent/route/start/resume mà không
  cần sửa public tool schema;
- Codex và Claude adapter đều normalize về cùng final result contract;
- native session ID được trả về và resume identity được kiểm tra;
- independent Git roots có thể active đồng thời;
- same Git root và same native session conflict đều bị reject;
- không còn global `_delegate_lock`;
- Delegation Silence có trong workspace policy;
- transcript không trở thành tool result;
- checker chỉ kiểm tra harness/CLI contract, không chạy test hoặc sửa source sản
  phẩm;
- ranh giới workspace/repo-local knowledge không bị phá vỡ;
- README phản ánh đúng cách cài cả workspace và repo template.
