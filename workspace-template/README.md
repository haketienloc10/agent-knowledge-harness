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
instructions/agent-routing.yaml   # Agent/model/flags + START/RESUME argv
instructions/model-routing.md     # Policy profile → route
.codex/config.toml                # Project-scoped MCP registration
mcp/qiqi_delegate/
├── pyproject.toml                # MCP runtime dependencies
└── server.py                     # delegate_repo_task
knowledge/                        # Durable cross-repo knowledge
.qiqi/tasks/                      # Working context + native session IDs
docs/WORKSPACE_SETUP.md           # Setup/takeover
scripts/qiqi-mcp-server.sh        # MCP STDIO launcher
scripts/workspace-check.sh        # Harness checker
```

## Execution Model

QiQi không quản lý pane, waiter, process hay transcript. QiQi chỉ giữ native
session ID khi cần tiếp tục conversation của execution agent.

Repo-local workflow chỉ có:

```text
QiQi
  ↓ delegate_repo_task(repository, task, route, session_id?)
MCP server
  ↓ START hoặc RESUME một non-interactive agent invocation
Codex / Claude Code
  ↓ repository work
  ↓ terminal structured result + native session_id
QiQi
```

`delegate_repo_task` là synchronous tool call. MCP server tự chờ child invocation
kết thúc và chỉ trả terminal result. Không có tool `status`, `wait`, `read`,
separate `resume` hay transcript.

## Routing

`instructions/agent-routing.yaml` là machine config. Agent entry định nghĩa CLI
grammar (`command`, `start_args`, `resume_args`, prompt transport); route entry
định nghĩa agent, model và native flags riêng của route.

Template có adapter Codex và Claude Code:

- Codex route mặc định dùng `codex exec --yolo` và native `exec resume`;
- Claude route mặc định dùng `claude -p --permission-mode auto` và native
  `--resume`.

QiQi chỉ chọn route. Muốn đổi model/flag thì sửa routing registry, không sửa MCP
public API.

## START và RESUME

```text
session_id absent  → START
session_id present → RESUME native session đó
```

Tool trả ID thật của Codex/Claude Code. Khi RESUME, MCP yêu cầu agent trả lại đúng
ID đã được yêu cầu; fallback sang session mới bị coi là lỗi.

Có thể đổi route/model/flags khi resume trong cùng agent nếu CLI hỗ trợ. Chuyển
Codex ↔ Claude phải START mới và handoff context, không resume chéo ID.

## Ranh giới

- Workspace root giữ orchestration và tri thức cross-repo.
- Repository con giữ architecture, domain rule, implementation và verification.
- QiQi không tự đọc/sửa/chạy repo-local workflow.
- Child stdout/stderr không được đưa vào QiQi context.
- Một phiên QiQi chỉ có một active delegation tại một thời điểm.
- MCP failure không được fallback sang shell-based child agent.

## Sử dụng

1. Sao chép template vào workspace root.
2. Điền `repos.yaml`, `SYSTEM_MAP.md`, `instructions/agent-routing.yaml`, model
   routing và knowledge index.
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
6. Làm theo `docs/WORKSPACE_SETUP.md` để chạy START/RESUME smoke test cho các agent
   đã cấu hình.

Không dùng template như monorepo wrapper và không chạy Git ở workspace root để
suy luận trạng thái repo con.
