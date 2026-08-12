# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này dùng khi đưa `workspace-template/` vào một workspace thực tế.
Mục tiêu là để QiQi chỉ điều phối ở workspace root và giao mọi repo-local work qua
MCP tool `delegate_repo_task`.

## Kết quả Cần đạt

Sau setup:

- `repos.yaml` trỏ đúng các Git root local;
- `SYSTEM_MAP.md` mô tả dependency/contract liên repo;
- `instructions/model-routing.md` chứa model đã xác nhận;
- project-scoped `.codex/config.toml` đăng ký MCP server `qiqi_delegate`;
- MCP server chỉ expose `delegate_repo_task`;
- child Codex chạy one-shot, ephemeral và trả structured terminal result;
- `bash scripts/workspace-check.sh` trả `PASS`.

## Runtime yêu cầu

Cần:

```bash
command -v codex
codex --version
command -v uv
uv --version
command -v python3
command -v git
command -v rg
command -v yq
```

MCP Python SDK và PyYAML được khai báo trong
`mcp/qiqi_delegate/pyproject.toml`; `uv` quản lý environment của MCP server.

## Bước 1: Điền Repository Registry

Từ workspace root, xác nhận từng repo:

```bash
git -C <repository-path> rev-parse --show-toplevel
git -C <repository-path> remote -v
git -C <repository-path> branch --show-current
git -C <repository-path> status --short
```

Điền `repos.yaml` bằng đường dẫn tương đối từ workspace root. Mỗi `path` phải trỏ
đúng Git root, không phải thư mục cha hoặc thư mục con.

Mỗi entry cần:

| Trường | Yêu cầu |
|---|---|
| `name` | Tên duy nhất QiQi dùng khi gọi MCP tool |
| `path` | Đường dẫn tương đối tới Git root |
| `role` | Vai trò thực tế của repo |
| `required_for` | Workflow/capability cần repo này |
| `depends_on` | Repository dependency; dùng `[]` nếu không có |

Không thêm repo chưa clone hoặc path giả.

## Bước 2: Hoàn thiện System Map và Knowledge

Điền `SYSTEM_MAP.md` bằng evidence thực tế cho topology, dependency, contract và
ownership liên repo.

Đọc `KNOWLEDGE.md`, sau đó chỉ tạo durable knowledge khi có evidence và khả năng
dùng lại. Chi tiết nội bộ một repository vẫn thuộc repository đó.

## Bước 3: Điền Model Routing

Xác nhận model từ Codex CLI/provider hiện tại rồi điền
`instructions/model-routing.md`.

QiQi chỉ cần hai giá trị khi override default:

- model ID;
- reasoning effort: `low`, `medium`, `high` hoặc `xhigh`.

Không lưu native session arguments, resume syntax hoặc concurrency orchestration.

## Bước 4: Chuẩn bị MCP Environment

Từ workspace root:

```bash
uv sync --project mcp/qiqi_delegate
bash -n scripts/qiqi-mcp-server.sh
python3 -m py_compile mcp/qiqi_delegate/server.py
```

`.codex/config.toml` đã đăng ký STDIO server:

```toml
[mcp_servers.qiqi_delegate]
command = "bash"
args = ["scripts/qiqi-mcp-server.sh"]
startup_timeout_sec = 30
tool_timeout_sec = 7200
required = true
enabled_tools = ["delegate_repo_task"]
default_tools_approval_mode = "approve"
```

`tool_timeout_sec` phải đủ dài để một coding task hoàn thành trong cùng MCP call.
Không hạ timeout xuống mức khiến QiQi phải tự theo dõi child process.

Codex hỗ trợ project-scoped `.codex/config.toml` cho trusted project. Khởi động
QiQi/Codex từ workspace root và trust project khi client yêu cầu.

## Bước 5: Hiểu Execution Boundary

QiQi chỉ gọi:

```text
delegate_repo_task(repository, task, model?, reasoning_effort?)
```

MCP server thực hiện nội bộ:

1. resolve `repository` từ `repos.yaml`;
2. xác nhận path là đúng Git root;
3. chạy one-shot `codex exec` trong repo;
4. dùng `--ephemeral` và `workspace-write`;
5. vô hiệu MCP `qiqi_delegate` trong child run để tránh recursive delegation;
6. giữ stdout/stderr ngoài QiQi context;
7. ép final response theo JSON Schema;
8. chỉ return khi child process đã kết thúc.

MCP server không expose `status`, `wait`, `read`, `resume`, `list_runs` hoặc
transcript tool.

QiQi không fallback sang shell-based `codex exec` nếu MCP lỗi.

## Bước 6: Xác minh Workspace

Chạy:

```bash
bash scripts/workspace-check.sh
```

Checker xác minh artifact, placeholder, MCP config/server contract, repository
registry và model routing. Nó không chạy test của repository con.

Có thể kiểm tra MCP được Codex nhận diện bằng lệnh setup thủ công:

```bash
codex mcp list
```

Lệnh này dành cho người setup/debug environment, không phải progress primitive
trong lifecycle của QiQi.

## Bước 7: Fresh-session Test

Mở Codex mới tại workspace root và kiểm tra:

1. QiQi mô tả đúng vai trò workspace-only.
2. Khi được hỏi repo-local fact, QiQi dùng `delegate_repo_task` thay vì tự đọc repo.
3. Trong tool call, QiQi không có progress/status loop.
4. Tool return chỉ chứa terminal structured result, không working transcript.
5. Follow-up repo task tạo một MCP call mới sau khi result trước đã reconcile.
6. Nếu MCP lỗi, QiQi báo blocker thay vì gọi child agent bằng shell.

Chỉ coi workspace sẵn sàng khi checker pass, MCP server khởi tạo được và một
one-shot delegation thử nghiệm trả terminal result đúng schema.
