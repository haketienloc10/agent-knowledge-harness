# AGENTS.md

Repo này phát triển hai template phối hợp trong multi-repository workspace:

- `workspace-template/`: QiQi control plane, synchronous MCP delegation, task
  continuity và cross-repo knowledge;
- `repo-template/`: workflow tối thiểu cho execution agent trong từng Git
  repository con.

Repo không chứa tri thức nghiệp vụ thật của một workspace cụ thể.

## Nguyên tắc

- QiQi là coordinator, không phải coding agent của repo con.
- Mọi repo-local work từ QiQi đi qua đúng một synchronous MCP tool:
  `delegate_repo_task`.
- MCP tool chỉ trả terminal structured result; không expose progress, status,
  wait, resume hoặc transcript.
- Repository con sở hữu architecture, domain rule, implementation và
  verification nội bộ.
- Workspace sở hữu registry, topology, task context và tri thức cross-repo.
- Agent repo con không sửa workspace knowledge; nó chỉ trả cross-repo impact cho
  QiQi xử lý.
- Ưu tiên artifact nhỏ, source of truth rõ và evidence có thể kiểm tra.
- Không thêm daemon, watcher, session manager hoặc observability primitive khi
  chưa có nhu cầu thực tế.

## Khi thay đổi Workspace Template

1. Giữ `AGENTS.md`, `identity.md`, MCP server, setup guide, checker và README đồng
   bộ cùng execution contract.
2. Không thêm đường delegation thứ hai bằng shell hoặc session manager.
3. Không thêm `status`, `wait`, `read_transcript`, `resume` hoặc `list_runs` vào
   MCP server nếu chưa thay đổi policy có chủ đích.
4. Child run phải one-shot, không recursive delegation và không stream transcript
   về QiQi.
5. Repository phải được resolve từ `repos.yaml` và path phải là exact Git root.
6. Tool result contract phải đủ cho QiQi reconcile mà không tự vào repo kiểm tra.
7. Nếu thay đổi artifact bắt buộc, cập nhật checker và tài liệu setup cùng lúc.

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
- child Codex dùng one-shot non-interactive run và structured final output;
- transcript không trở thành tool result;
- checker chỉ kiểm tra harness, không chạy test hoặc sửa source sản phẩm;
- ranh giới workspace/repo-local knowledge không bị phá vỡ;
- README phản ánh đúng cách cài cả workspace và repo template.
