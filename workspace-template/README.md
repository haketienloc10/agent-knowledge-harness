# QiQi Multi-repository Workspace Template

Template này đặt tại root của một local workspace chứa nhiều Git repository độc
lập. QiQi chỉ điều phối; mọi repo-local work đi qua một synchronous MCP tool.

## Thành phần

```text
AGENTS.md                         # Policy điều phối của QiQi
identity.md                       # Danh tính và giới hạn
repos.yaml                        # Registry repository
SYSTEM_MAP.md                     # Quan hệ/contract liên repo
KNOWLEDGE.md                      # Router tri thức cross-repo
instructions/model-routing.md     # Model + reasoning effort
.codex/config.toml                # Project-scoped MCP registration
mcp/qiqi_delegate/
├── pyproject.toml                # MCP runtime dependencies
└── server.py                     # delegate_repo_task
knowledge/                        # Durable cross-repo knowledge
.qiqi/tasks/                      # Working context
docs/WORKSPACE_SETUP.md           # Setup/takeover
scripts/qiqi-mcp-server.sh        # MCP STDIO launcher
scripts/workspace-check.sh        # Harness checker
```

## Execution Model

QiQi không quản lý coding-agent session, pane, waiter hoặc transcript.

Repo-local workflow chỉ có:

```text
QiQi
  ↓ delegate_repo_task(...)
MCP server
  ↓ one-shot codex exec
Repository
  ↓ terminal structured result
QiQi
```

`delegate_repo_task` là synchronous tool call. MCP server tự chờ child Codex kết
thúc và chỉ trả final result. Không có tool `status`, `wait`, `read`, `resume` hay
transcript.

## Ranh giới

- Workspace root giữ orchestration và tri thức cross-repo.
- Repository con giữ architecture, domain rule, implementation và verification.
- QiQi không tự đọc/sửa/chạy repo-local workflow.
- Child transcript không được đưa vào QiQi context.
- Một phiên QiQi chỉ có một active delegation tại một thời điểm.
- MCP failure không được fallback sang shell-based child agent.

## Sử dụng

1. Sao chép template vào workspace root.
2. Điền `repos.yaml`, `SYSTEM_MAP.md`, model routing và knowledge index.
3. Chuẩn bị MCP environment:

   ```bash
   uv sync --project mcp/qiqi_delegate
   ```

4. Kiểm tra harness:

   ```bash
   bash scripts/workspace-check.sh
   ```

5. Khởi động Codex tại workspace root. Project-scoped `.codex/config.toml` đăng ký
   MCP server `qiqi_delegate` và chỉ enable `delegate_repo_task`.
6. Làm theo `docs/WORKSPACE_SETUP.md` để chạy fresh-session test.

Không dùng template như monorepo wrapper và không chạy Git ở workspace root để
suy luận trạng thái repo con.
