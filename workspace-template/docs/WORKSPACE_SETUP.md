# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này dùng khi đưa `workspace-template/` vào một workspace thực tế.
Mục tiêu là để QiQi giữ vai trò Chief of Staff tại workspace root và giao mọi
repo-local work qua MCP tool `delegate_repo_task`.

## Kết quả Cần đạt

Sau setup:

- `repos.yaml` trỏ đúng các Git root local và không có hai entry cùng resolve về
  một Git root;
- `SYSTEM_MAP.md` mô tả dependency/contract liên repo;
- `instructions/agent-routing.yaml` chứa agent, model, flags và START/RESUME argv
  đã xác nhận;
- `instructions/model-routing.md` map profile sang route;
- project-scoped `.codex/config.toml` đăng ký MCP server `qiqi_delegate`;
- MCP server chỉ expose `delegate_repo_task`;
- mỗi delegation chạy đúng một non-interactive START hoặc RESUME invocation;
- các repo task độc lập có thể chạy đồng thời;
- MCP hard-reject concurrent calls trên cùng resolved Git root hoặc cùng native
  `session_id`;
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
đúng Git root, không phải thư mục cha hoặc thư mục con. Không tạo hai repository
entry cùng resolve về một Git root vì concurrency guard sở hữu resource theo Git
root thực tế, không theo alias name.

## Bước 2: Hoàn thiện System Map và Knowledge

Điền `SYSTEM_MAP.md` bằng evidence thực tế cho topology, dependency, contract và
ownership liên repo.

Đọc `KNOWLEDGE.md`, sau đó chỉ tạo durable knowledge khi có evidence và khả năng
dùng lại. Chi tiết nội bộ một repository vẫn thuộc repository đó.

`SYSTEM_MAP.md` cũng là một nguồn để QiQi nhận diện dependency giữa các task trước
khi gom chúng vào cùng delegation wave.

## Bước 3: Điền Agent Routing

`instructions/agent-routing.yaml` là machine-readable execution registry.
Template ban đầu có hai adapter:

- `codex`: non-interactive `codex exec`, `--yolo`, JSON event stream để lấy native
  thread/session ID, structured result file và native `exec resume`;
- `claude`: non-interactive `claude -p`, `--output-format json`, lấy `session_id`
  từ JSON envelope và native `--resume`.

Xác nhận CLI local trước khi thay placeholder:

```bash
codex exec --help
claude --help
```

Flag phụ thuộc model phải nằm ở route tương ứng. Ví dụ, nếu Haiku không hỗ trợ
`--permission-mode auto` nhưng Sonnet 5+ hỗ trợ, giữ Claude agent base args không
có flag đó; chỉ route Sonnet phù hợp mới thêm:

```yaml
args:
  - --permission-mode
  - auto
```

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

`instructions/model-routing.md` chỉ là policy cho QiQi chọn route. Profile có thể
trỏ tới Codex hoặc Claude route đã tồn tại trong `agent-routing.yaml`.

QiQi chỉ truyền tên route; không tự truyền executable, model ID, reasoning flag
hay permission mode vào MCP tool.

Model routing không quyết định concurrency. Dependency, Git root và shared
resource mới quyết định task nào được cùng một delegation wave.

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
→ resolve repository + route
→ claim resolved Git root
→ agent.start_args + route.args
→ non-interactive child invocation
→ terminal result + native session_id
→ release Git root
```

### RESUME

```text
session_id present
→ resolve repository + route
→ claim resolved Git root + native session_id
→ agent.resume_args + route.args + native session_id
→ non-interactive child invocation
→ terminal result + same native session_id
→ release Git root + session_id
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

## Bước 7: Dependency và Delegation Waves

QiQi có thể dispatch nhiều repo task trong cùng wave khi tất cả điều kiện sau đều
đúng:

- chúng thuộc các resolved Git root khác nhau;
- không phụ thuộc output, contract, schema, migration, generated artifact hoặc
  decision chưa có của nhau;
- không cùng thao tác một external/shared mutable resource;
- không dùng cùng native `session_id`;
- mỗi task có prompt, scope và completion criteria độc lập.

Task phải sang wave sau nếu consumer cần producer result, cùng Git root, cùng
shared mutable resource hoặc chưa đủ evidence để xác nhận độc lập.

MCP hard guard chỉ bảo vệ resource mà server biết chắc:

- cùng resolved Git root → reject concurrent call;
- cùng native `session_id` → reject concurrent resume.

Dependency và shared external resource vẫn do QiQi lập kế hoạch. Khi không chắc
có conflict, chạy tuần tự.

Host/client có thể dispatch MCP calls song song hoặc tuần tự. Correctness của
workspace không được phụ thuộc việc host có thực sự parallelize tool calls hay
không.

## Bước 8: Delegation Silence

Sau khi bắt đầu dispatch một wave, QiQi không phát user-visible progress
commentary kiểu “đang chạy”, “đang chờ”, “chưa có kết quả” hoặc “tiếp tục chờ”.

Trong lúc wave in-flight, QiQi chỉ:

- dispatch các `delegate_repo_task` độc lập đã xác định thuộc wave;
- nhận terminal result/failure của các call đó.

QiQi không poll status/process/PID/transcript, không suy đoán tiến độ và không
khởi động downstream task dựa trên partial state. Sau khi các result cần thiết của
wave terminally resolve/fail, QiQi reconcile rồi mới phát user-visible output hoặc
lập wave tiếp theo.

## Bước 9: Result Normalization

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

## Bước 10: Xác minh Workspace

Chạy:

```bash
bash scripts/workspace-check.sh
```

Checker xác minh artifact, placeholder, MCP runtime, repository registry,
agent/route config, configured long flags, repo/session concurrency guard và việc
không còn global delegation lock. Checker cũng từ chối nhiều `repos.yaml` entry
cùng resolve về một Git root.

Checker không gọi model API và không chạy test của repository con.

Có thể kiểm tra MCP được Codex nhận diện bằng:

```bash
codex mcp list
```

Lệnh này dành cho setup/debug environment, không phải progress primitive trong
lifecycle của QiQi.

## Bước 11: Fresh-session Test

Mở Codex mới tại workspace root và kiểm tra:

1. QiQi mô tả đúng vai trò Chief of Staff workspace-only.
2. Repo-local fact đi qua `delegate_repo_task`.
3. START với một route Codex trả native `session_id`.
4. RESUME ID đó bằng route Codex phù hợp giữ đúng native ID.
5. START với một route Claude trả native `session_id`.
6. RESUME ID đó bằng route Claude phù hợp giữ đúng native ID.
7. Hai read-only task trên hai Git root độc lập có thể được dispatch trong cùng
   delegation wave nếu host hỗ trợ concurrent MCP calls.
8. Hai call cùng Git root bị MCP reject khi call đầu còn active.
9. Hai RESUME dùng cùng native `session_id` bị MCP reject khi call đầu còn active.
10. Trong wave không có user-visible progress commentary từ QiQi theo policy.
11. Tool return chỉ chứa terminal structured result, không working transcript.
12. Nếu MCP/CLI lỗi, QiQi báo blocker thay vì gọi child agent bằng shell.

Chỉ coi workspace sẵn sàng khi checker pass, MCP server khởi tạo được và smoke
test START/RESUME cho các agent được cấu hình đã thành công. Concurrency smoke test
nên dùng read-only task trên hai repository độc lập để tránh side effect.
