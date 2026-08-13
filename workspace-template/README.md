# QiQi Multi-repository Workspace Template

Template này đặt tại root của một local workspace chứa nhiều Git repository độc
lập. QiQi giữ vai trò Chief of Staff kỹ thuật; mọi repo-local work đi qua MCP tool
`delegate_repo_task`.

## Thành phần

```text
AGENTS.md                         # Policy Chief of Staff của QiQi
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

Repo-local workflow:

```text
QiQi — Chief of Staff
  ↓ dependency planning
  ↓ delegation wave
MCP delegate_repo_task calls
  ↓ START hoặc RESUME non-interactive invocation
Codex / Claude Code tại các Git root độc lập
  ↓ terminal structured result + native session_id
QiQi
  ↓ reconcile wave / dependency / next decision
```

Mỗi `delegate_repo_task` call là synchronous: call chỉ resolve khi child
invocation terminally complete. Tuy nhiên nhiều call có thể active đồng thời khi
chúng nhắm tới **các resolved Git root khác nhau**, không dùng cùng native session
và không có dependency/shared-resource conflict.

MCP server hard-reject concurrent calls trên cùng resolved Git root hoặc cùng
native `session_id`. Dependency và external/shared-resource conflict do QiQi lập
kế hoạch ở workspace level.

Không có tool `status`, `wait`, `read`, separate `resume` hay transcript.

## Delegation Silence

Sau khi bắt đầu dispatch một delegation wave, QiQi không phát user-visible
progress commentary kiểu “đang chạy”, “đang chờ” hoặc “chưa có kết quả”. QiQi chỉ
dispatch các task độc lập đã xác định thuộc cùng wave và nhận terminal tool
result. Sau khi các result cần thiết của wave resolve/fail, QiQi mới reconcile và
phát output tiếp theo cho người dùng.

## Routing

`instructions/agent-routing.yaml` là machine config. Agent entry định nghĩa CLI
grammar (`command`, `start_args`, `resume_args`, prompt transport); route entry
định nghĩa agent, model và native flags riêng của route.

Template có adapter Codex và Claude Code:

- Codex agent dùng `codex exec --yolo`, JSON event stream và native `exec resume`;
- Claude agent dùng `claude -p`, `--output-format json` và native `--resume`;
- flag phụ thuộc model như `--permission-mode auto` phải nằm ở route tương ứng,
  không đặt ở agent base args nếu không phải mọi model đều hỗ trợ.

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
Codex ↔ Claude phải START mới và handoff context, không resume chéo ID. Không chạy
đồng thời hai RESUME dùng cùng native session ID.

## Dependency và Delegation Waves

Các task có thể nằm cùng wave khi:

- thuộc các Git root khác nhau;
- không phụ thuộc output/contract/decision chưa có của nhau;
- không cùng thay đổi shared mutable resource;
- không dùng cùng native session;
- có prompt và completion criteria độc lập.

Task phụ thuộc producer, cùng Git root hoặc cùng shared resource phải sang wave
sau. Khi không chắc conflict, chạy tuần tự. Host/client có thể dispatch MCP calls
song song hoặc tuần tự; correctness không phụ thuộc khả năng parallel dispatch.

## Ranh giới

- Workspace root giữ orchestration và tri thức cross-repo.
- Repository con giữ architecture, domain rule, implementation và verification.
- QiQi không tự đọc/sửa/chạy repo-local workflow.
- Child stdout/stderr không được đưa vào QiQi context.
- MCP failure không được fallback sang shell-based child agent.
- Concurrency chỉ được phép giữa các resource độc lập; cùng Git root/session bị
  MCP chặn cứng.

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
6. Làm theo `docs/WORKSPACE_SETUP.md` để chạy START/RESUME và concurrency smoke
   test cho các agent đã cấu hình.

Không dùng template như monorepo wrapper và không chạy Git ở workspace root để
suy luận trạng thái repo con.
