# Agent Knowledge Harness

Bộ khung để vận hành **QiQi — Chief of Staff kỹ thuật** tại một local workspace
chứa nhiều Git repository độc lập, với execution boundary rõ giữa workspace
coordination và coding agent trong từng repository con.

## Vòng kín

```text
Người dùng
  ↓ yêu cầu và quyết định
QiQi tại workspace
  ↓ dependency planning / delegation waves
  ↓ task prompt + route + optional native session_id
MCP delegate_repo_task
  ↓ Herdr-backed real interactive Codex / Claude
  ↓ implementation + verification
  ↓ write terminal turn result to .qiqi/runs/...md
MCP
  ↓ validate native identity + result artifact
  ↓ return {session_id, result_path}
QiQi
  ↓ read result_path
  ↓ reconcile / task context / native resume / cross-repo knowledge
Người dùng
```

## Hai template

### `workspace-template/`

Đặt tại workspace root. Nó sở hữu QiQi, repository registry, topology, task
context, routing, MCP delegation, result handoff và tri thức cross-repo.

```text
workspace-template/
├── .codex/config.toml
├── AGENTS.md
├── identity.md
├── repos.yaml
├── SYSTEM_MAP.md
├── KNOWLEDGE.md
├── README.md
├── instructions/
│   ├── agent-routing.yaml          # canonical runtime registry
│   └── model-routing.md            # QiQi exact-route selection policy
├── mcp/qiqi_delegate/
│   ├── pyproject.toml
│   └── server.py
├── knowledge/
├── .qiqi/tasks/
├── .qiqi/runs/                    # runtime-created result artifacts
├── docs/
│   ├── WORKSPACE_SETUP.md
│   └── examples/                  # documentation-only routing examples
└── scripts/
    ├── qiqi-mcp-server.sh
    └── workspace-check.sh
```

`instructions/` chỉ chứa active instructions. `qiqi_delegate` chỉ load
`instructions/agent-routing.yaml`; các routing example dưới `docs/examples/` không
phải runtime input.

QiQi không quản lý pane/process hoặc polling. Repo-local work chỉ đi qua
`delegate_repo_task`.

### `repo-template/`

Đặt tại Git root của từng repository con. Nó giúp execution agent hiểu
architecture, verification và knowledge ownership nội bộ.

```text
repo-template/
├── AGENTS.md
├── CLAUDE.md
├── ARCHITECTURE.md
├── docs/
│   ├── VERIFY.md
│   ├── REPO_SETUP.md
│   ├── domain/README.md
│   ├── specs/README.md
│   ├── decisions/README.md
│   └── friction/README.md
└── scripts/repo-check.sh
```

## Public MCP Contract

```text
delegate_repo_task(repository, task, route, session_id?)
```

Semantics:

- không có `session_id` → START native session mới;
- có `session_id` → RESUME đúng native session đó;
- `task` semantics thuộc QiQi;
- MCP resolve repository/route, chạy Herdr lifecycle và append result-handoff
  footer;
- tool synchronous đến khi turn settle hoặc fail;
- không có status/wait/read/transcript/separate-resume tool.

Success return chỉ gồm:

```json
{
  "session_id": "<native-session-id>",
  "result_path": ".qiqi/runs/<session-artifact>.md"
}
```

QiQi phải đọc `result_path` trước khi quyết định bước tiếp theo. Không RESUME chỉ
để yêu cầu agent lặp lại report.

## Prompt Ownership

QiQi viết execution prompt: outcome, scope, dependency, evidence, constraints và
verification. MCP không ép cách agent làm việc.

Với START, dòng không rỗng đầu tiên của task là một **English task title** ngắn,
ưu tiên ASCII và khoảng 3–8 từ. MCP đã derive filename slug từ dòng đầu này; phần
instruction bên dưới vẫn có thể dùng ngôn ngữ phù hợp nhất. RESUME giữ nguyên
artifact/path được tạo ở START.

MCP chỉ append protocol footer để agent biết exact result artifact, pending marker
và required headings. Boundary này giữ policy ở đúng tầng:

```text
QiQi                   → what/why/scope/quality + exact route choice
model-routing.md       → when QiQi should choose each route
agent-routing.yaml     → executable/model/native argv for that route
MCP + Herdr            → lifecycle/session/result handoff
repo agent             → investigation/implementation/verification
```

## Result Artifact

Mỗi native session sở hữu một durable Markdown artifact:

```text
.qiqi/runs/<repo>-<english-task-slug>-<native-session-id>.md
```

`<english-task-slug>` được derive từ English title ở dòng không rỗng đầu tiên của
START task, theo kebab-case ASCII, tối đa 48 ký tự. Ví dụ `Update checkout
validation` tạo slug `update-checkout-validation`.

START tạo pending artifact rồi promote sau khi native identity có sẵn. RESUME
append `Task N / Result N` vào exact artifact đó và trả lại cùng `result_path`.

Newest result có:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

`Outcome` chỉ là `completed` hoặc `blocked`.

## Herdr Execution

MCP dùng Herdr như internal interactive control plane:

```text
MCP
  → ensure named Herdr server
  → require selected adapter integration = current
  → create workspace at exact repo Git root
  → start real interactive Codex/Claude TUI
  → prompt actual QiQi task
  → wait for settled state
  → read native session identity from integration
  → validate result artifact
  → close workspace
```

Herdr integration setup là explicit environment setup; MCP không tự mutate
Codex/Claude config để install integration.

## Routing

`workspace-template/instructions/model-routing.md` là policy chỉ để QiQi chọn
**exact route**. Nó không chứa runtime model IDs hoặc CLI flags.

`workspace-template/instructions/agent-routing.yaml` là canonical machine source
of truth và là routing file duy nhất MCP load. Nó sở hữu:

- interactive agent command;
- adapter;
- START/RESUME argv;
- model;
- route-specific flags.

Runtime placeholders:

```text
{model}
{session_id}
{result_dir}
{route_args}
```

QiQi chỉ chọn route. Public MCP schema không đổi khi model/native flags thay đổi.
Các file `workspace-template/docs/examples/agent-routing.*.yaml` chỉ là tài liệu
tham khảo; route chỉ khả dụng khi tồn tại trong canonical registry.

## Concurrency

Các call trên independent Git roots có thể active đồng thời nếu không dependency
hoặc shared-resource conflict.

Trong cùng `qiqi_delegate` server process:

```text
same resolved Git root → reject concurrent call
same native session_id → reject concurrent call
```

MCP không silently queue cùng repo/session. Dependency/shared external resource do
QiQi lập kế hoạch bằng delegation wave.

## Delegation Silence

Trong lúc wave in-flight, QiQi không phát user-visible progress commentary và
không poll child state. Khi tool success, QiQi đọc result artifact; sau khi đủ
terminal result mới reconcile và giao tiếp tiếp.

## Ranh giới sở hữu

| Loại thông tin | Nơi lưu |
|---|---|
| Repository và local path | Workspace `repos.yaml` |
| Topology/dependency liên repo | Workspace `SYSTEM_MAP.md` |
| Contract/decision cross-repo có evidence | Workspace `knowledge/` |
| Working task state | Workspace `.qiqi/tasks/` |
| Terminal session/turn handoff | Workspace `.qiqi/runs/` |
| Agent/model/native flags + START/RESUME argv | Workspace `instructions/agent-routing.yaml` |
| Policy chọn exact route | Workspace `instructions/model-routing.md` |
| Routing customization examples | Workspace `docs/examples/` |
| Interactive execution/session lifecycle | MCP `delegate_repo_task` + Herdr |
| Architecture/implementation/verification nội bộ | Repository con |

## Áp dụng vào Workspace

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
cd /path/to/multi-repo
herdr integration install codex
herdr integration install claude
herdr integration status
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Sau đó khởi động Codex tại workspace root. Project-scoped `.codex/config.toml`
đăng ký STDIO MCP server `qiqi_delegate` và chỉ enable `delegate_repo_task`.

Xem `docs/WORKSPACE_SETUP.md` để chạy START/RESUME, result artifact continuity và
concurrency smoke tests.

## Áp dụng vào Repository con

```bash
rsync -av --ignore-existing repo-template/ /path/to/multi-repo/<repository>/
cd /path/to/multi-repo/<repository>
bash scripts/repo-check.sh
```

Nếu repo đã có `AGENTS.md`, không ghi đè; gộp Git-root boundary, architecture,
verification, knowledge ownership và final result contract.

## Thiết kế Cố ý

Harness cố ý không có public status polling, watcher, transcript API hoặc session
manager riêng. Resumability là native session ID đi qua cùng MCP tool. Result
content đi qua durable Markdown artifact, không duplicate inline trong tool return.