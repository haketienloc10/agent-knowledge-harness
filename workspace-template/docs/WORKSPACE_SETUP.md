# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này dùng khi đưa `workspace-template/` vào một workspace thực tế.
Mục tiêu là để QiQi chỉ điều phối ở workspace root và giao mọi repo-local work qua
MCP tool `delegate_repo_task`.

## Kết quả Cần đạt

Sau setup:

- `repos.yaml` trỏ đúng các Git root local;
- `SYSTEM_MAP.md` mô tả dependency/contract liên repo;
- `instructions/agent-routing.yaml` chứa agent, model, flags và START/RESUME argv
  đã xác nhận;
- `instructions/model-routing.md` map profile sang route;
- project-scoped `.codex/config.toml` đăng ký MCP server `qiqi_delegate`;
- MCP server chỉ expose `delegate_repo_task`;
- mỗi delegation chạy đúng một non-interactive START hoặc RESUME invocation;
- terminal result trả native Codex/Claude `session_id` cùng structured result;
- `bash scripts/workspace-check.sh` trả `PASS`.

## Runtime yêu cầu

Cần tối thiểu:

```bash
command -v codex && codex --version
command -v claude && claude --version
command -v uv && uv --version
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

## Bước 2: Hoàn thiện System Map và Knowledge

Điền `SYSTEM_MAP.md` bằng evidence thực tế cho topology, dependency, contract và
ownership liên repo.

Đọc `KNOWLEDGE.md`, sau đó chỉ tạo durable knowledge khi có evidence và khả năng
dùng lại. Chi tiết nội bộ một repository vẫn thuộc repository đó.

## Bước 3: Điền Agent Routing

`instructions/agent-routing.yaml` là machine-readable execution registry.
Template ban đầu có hai adapter:

- `codex`: non-interactive `codex exec`, `--yolo`, JSON event stream để lấy native
  thread/session ID, structured result file và native `exec resume`;
- `claude`: non-interactive `claude -p`, `--permission-mode auto`,
  `--output-format json`, lấy `session_id` từ JSON envelope và native `--resume`.

Xác nhận CLI local trước khi thay placeholder:

```bash
codex exec --help
claude --help
```

`auto` là giá trị permission mode được workspace này chủ động cấu hình theo yêu
cầu vận hành. Nếu Claude CLI local không chấp nhận đúng giá trị đó, sửa
`agent-routing.yaml` theo mode đã xác nhận trên máy thay vì hard-code trong MCP
server.

Mỗi agent entry sở hữu:

```text
command
adapter
prompt_transport
start_args
resume_args
```

Mỗi route sở hữu:

```text
agent
model
args
```

Ví dụ một route Codex có thể thêm reasoning effort bằng `args`; route Claude có
thể để `args: []` hoặc thêm native flags riêng. Flags thay đổi theo model/agent
thì chỉ sửa registry.

Không thêm `--ephemeral` vào Codex route cần resume: START phải persist native
thread để `codex exec resume <session-id>` có thể mở lại sau đó.

## Bước 4: Điền Model Routing

`instructions/model-routing.md` chỉ là policy cho QiQi chọn route. Thay các
placeholder `{{FAST_ROUTE}}`, `{{BALANCED_ROUTE}}`, `{{DEEP_ROUTE}}`,
`{{VERIFIER_ROUTE}}` bằng tên route thực sự tồn tại trong `agent-routing.yaml`.

QiQi chỉ truyền tên route; không tự truyền executable, model ID, reasoning flag
hay permission mode vào MCP tool.

## Bước 5: Chuẩn bị MCP Environment

Từ workspace root:

```bash
uv sync --project mcp/qiqi_delegate
bash -n scripts/qiqi-mcp-server.sh
python3 -m py_compile mcp/qiqi_delegate/server.py
```

`.codex/config.toml` đăng ký STDIO server `qiqi_delegate`. `tool_timeout_sec` phải
đủ dài để một coding task hoàn thành trong cùng MCP call; không hạ timeout xuống
mức khiến QiQi phải tự theo dõi child process.

Khởi động QiQi/Codex từ workspace root và trust project khi client yêu cầu.

## Bước 6: Hiểu Execution Boundary

QiQi chỉ gọi:

```text
delegate_repo_task(repository, task, route, session_id?)
```

### START

```text
session_id absent
→ resolve route
→ agent.start_args + route.args
→ non-interactive child invocation
→ terminal result + native session_id
```

### RESUME

```text
session_id present
→ resolve route
→ agent.resume_args + route.args + native session_id
→ non-interactive child invocation
→ terminal result + same native session_id
```

MCP server xác nhận session ID trả về của RESUME đúng bằng ID được yêu cầu. Nếu
CLI fallback sang session mới hoặc không thể resume ID cũ, tool fail thay vì âm
thầm coi là resume thành công.

Muốn đổi model/flags trong cùng agent, chọn route khác và truyền cùng
`session_id`; CLI agent quyết định config đó có hợp lệ cho resume hay không.
Muốn đổi Codex ↔ Claude, START mới và handoff context; không resume chéo native
session ID.

MCP server không expose `status`, `wait`, `read`, separate `resume`, `list_runs`
hoặc transcript tool. QiQi không fallback sang shell-based agent CLI nếu MCP lỗi.

## Bước 7: Result Normalization

MCP giữ stdout/stderr trong temporary directory và xóa khi call kết thúc.

- Codex adapter đọc JSON events để lấy native thread ID và đọc structured final
  result từ result file.
- Claude adapter đọc JSON envelope để lấy `session_id`, sau đó parse field
  `result` thành common JSON result.

QiQi chỉ nhận metadata terminal:

```text
agent
route
model
session_id
run_id
repository
duration_seconds
```

và common result:

```text
outcome
changes
verification
git_state
blockers
repo_local_knowledge
cross_repo_impact
```

## Bước 8: Xác minh Workspace

Chạy:

```bash
bash scripts/workspace-check.sh
```

Checker xác minh artifact, placeholder, MCP runtime, repository registry,
agent/route config và các configured long flags có xuất hiện trong CLI help của
agent tương ứng. Nó không gọi model API và không chạy test của repository con.

Có thể kiểm tra MCP được Codex nhận diện bằng:

```bash
codex mcp list
```

Lệnh này dành cho setup/debug environment, không phải progress primitive trong
lifecycle của QiQi.

## Bước 9: Fresh-session Test

Mở Codex mới tại workspace root và kiểm tra:

1. QiQi mô tả đúng vai trò workspace-only.
2. Repo-local fact đi qua `delegate_repo_task`.
3. START với một route Codex trả native `session_id`.
4. RESUME ID đó bằng route Codex phù hợp giữ đúng native ID.
5. START với một route Claude trả native `session_id`.
6. RESUME ID đó bằng route Claude phù hợp giữ đúng native ID.
7. Trong mỗi tool call không có progress/status loop.
8. Tool return chỉ chứa terminal structured result, không working transcript.
9. Nếu MCP/CLI lỗi, QiQi báo blocker thay vì gọi child agent bằng shell.

Chỉ coi workspace sẵn sàng khi checker pass, MCP server khởi tạo được và ít nhất
một START/RESUME smoke test cho từng agent được cấu hình đã thành công.
