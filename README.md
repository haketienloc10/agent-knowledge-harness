# Agent Knowledge Harness

Bộ khung để vận hành **QiQi — Chief of Staff kỹ thuật** tại một local workspace
chứa nhiều Git repository độc lập, với execution boundary rõ giữa workspace
coordination và coding agent trong từng repository con.

## Vòng kín

```text
Người dùng
  ↓ yêu cầu và quyết định
QiQi tại workspace
  ↓ đọc SYSTEM_MAP / knowledge cần thiết
  ↓ self-contained task prompt cho repo A
MCP delegate_repo_task
  ↓ real interactive Codex / Claude tại repo A
Repo A agent
  ↓ implementation / verification / repo-local knowledge
  ↓ terminal result + Cross-repo Impact
QiQi
  ↓ đọc result_path và reconcile
  ↓ chắt lọc relevant fact/evidence
  ↓ self-contained task prompt cho repo B nếu cần
Repo B agent
  ↓ implementation / verification / terminal result
QiQi
  ↓ reconcile outcome
  ↓ cập nhật workspace knowledge nếu thông tin thực sự dùng lại
Người dùng
```

QiQi là handoff broker duy nhất giữa các repository. Child agents không tự đọc
repository anh em, workspace `knowledge/` hoặc result artifact của repository khác
để lấy cross-repo context.

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
├── README.md
├── instructions/
│   ├── agent-routing.yaml          # canonical runtime registry
│   └── model-routing.md            # QiQi exact-route selection policy
├── mcp/qiqi_delegate/
│   ├── pyproject.toml
│   └── server.py
├── knowledge/
│   ├── README.md                   # cách lưu/cập nhật knowledge
│   ├── INDEX.md                    # summary index để chọn knowledge cần đọc
│   ├── systems/
│   ├── contracts/
│   └── decisions/
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

### `repo-template/`

Đặt tại Git root của từng repository con. Nó giúp execution agent hiểu
architecture, verification, repo-local knowledge ownership và cách handoff kết quả
về QiQi.

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

## Workflow hai chiều

### QiQi → repository

QiQi:

1. Xác định repo và dependency.
2. Đọc `SYSTEM_MAP.md` khi task chạm boundary cross-repo.
3. Đọc `knowledge/INDEX.md`, sau đó chỉ mở exact knowledge document liên quan.
4. Nếu có producer result, đọc terminal artifact của producer.
5. Chắt lọc workspace knowledge/upstream result thành context trực tiếp trong
   prompt của consumer.
6. Gọi `delegate_repo_task`.

Repo agent không tự mở workspace knowledge hoặc sibling result artifact.

### Repository → QiQi

Repo agent trả terminal result có:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

`Repo-local Knowledge` cho biết source of truth nội bộ đã cập nhật.
`Cross-repo Impact` đưa fact/evidence cần QiQi chuyển tới repository khác hoặc xử
lý ở workspace.

QiQi đọc result rồi:

- truyền relevant impact vào downstream prompt nếu task hiện tại cần;
- cập nhật `SYSTEM_MAP.md` nếu topology/ownership thay đổi;
- cập nhật `knowledge/` + `knowledge/INDEX.md` nếu thông tin có khả năng dùng lại;
- không tạo durable knowledge nếu thông tin chỉ phục vụ handoff hiện tại.

## Knowledge MVP

`workspace-template/knowledge/INDEX.md` là read router. Mỗi dòng phải đủ summary,
`Khi nào cần đọc` và phạm vi để QiQi quyết định có mở document hay không.

`workspace-template/knowledge/README.md` là write guide. Nó định nghĩa khi nào cần
lưu tri thức cross-repo, nơi lưu và yêu cầu cập nhật `INDEX.md` cùng thay đổi.

Không có proposal lifecycle trong MVP. Result artifact giữ terminal history; task
context giữ continuation state; durable knowledge chỉ giữ thông tin cross-repo có
khả năng dùng lại.

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

QiQi viết execution prompt: outcome, scope, dependency, relevant workspace
knowledge, upstream result, evidence, constraints và verification. MCP không ép
cách agent làm việc.

Với START, dòng không rỗng đầu tiên của task là một **English task title** ngắn,
ưu tiên ASCII và khoảng 3–8 từ. MCP derive filename slug từ dòng đầu này; phần
instruction bên dưới vẫn có thể dùng ngôn ngữ phù hợp nhất. RESUME giữ nguyên
artifact/path được tạo ở START.

MCP chỉ append protocol footer để agent biết exact result artifact, pending marker
và required headings. Boundary này giữ policy ở đúng tầng:

```text
QiQi                   → what/why/scope/quality + cross-repo handoff context
model-routing.md       → when QiQi should choose each route
agent-routing.yaml     → executable/model/native argv for that route
MCP + Herdr            → lifecycle/session/result handoff
repo agent             → investigation/implementation/verification + outbound impact
```

## Result Artifact

Mỗi native session sở hữu một durable Markdown artifact:

```text
.qiqi/runs/<repo>-<english-task-slug>-<native-session-id>.md
```

`<english-task-slug>` được derive từ English title ở dòng không rỗng đầu tiên của
START task, theo kebab-case ASCII, tối đa 48 ký tự. START tạo pending artifact rồi
promote sau khi native identity có sẵn. RESUME append `Task N / Result N` vào exact
artifact đó và trả lại cùng `result_path`.

Artifact này là handoff **repo agent → QiQi**. Child agent khác không tự dùng nó làm
input; QiQi đọc và chuyển relevant context qua prompt.

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
of truth và là routing file duy nhất MCP load. Nó sở hữu interactive agent command,
adapter, START/RESUME argv, model và route-specific flags.

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

Consumer cần producer result phải ở wave sau. QiQi đọc producer result và đưa
relevant fact/evidence vào consumer prompt trước khi dispatch.

## Delegation Silence

Trong lúc wave in-flight, QiQi không phát user-visible progress commentary và
không poll child state. Khi tool success, QiQi đọc result artifact; sau khi đủ
terminal result mới reconcile và giao tiếp tiếp.

## Ranh giới sở hữu

| Loại thông tin | Nơi lưu |
|---|---|
| Repository và local path | Workspace `repos.yaml` |
| Topology/dependency liên repo | Workspace `SYSTEM_MAP.md` |
| Mục lục knowledge cần đọc | Workspace `knowledge/INDEX.md` |
| Quy tắc lưu/cập nhật knowledge | Workspace `knowledge/README.md` |
| Contract/decision/flow cross-repo dùng lại | Workspace `knowledge/` |
| Working task + handoff state | Workspace `.qiqi/tasks/` |
| Terminal session/turn handoff | Workspace `.qiqi/runs/` |
| Agent/model/native flags + START/RESUME argv | Workspace `instructions/agent-routing.yaml` |
| Policy chọn exact route | Workspace `instructions/model-routing.md` |
| Routing customization examples | Workspace `docs/examples/` |
| Interactive execution/session lifecycle | MCP `delegate_repo_task` + Herdr |
| Architecture/implementation/verification/repo-local knowledge | Repository con |

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

Xem `docs/WORKSPACE_SETUP.md` để chạy START/RESUME, result artifact continuity,
concurrency và repo-A → QiQi → repo-B handoff smoke tests.

## Áp dụng vào Repository con

```bash
rsync -av --ignore-existing repo-template/ /path/to/multi-repo/<repository>/
cd /path/to/multi-repo/<repository>
bash scripts/repo-check.sh
```

Nếu repo đã có `AGENTS.md`, không ghi đè; gộp Git-root boundary, architecture,
verification, QiQi handoff, knowledge ownership và final result contract.

## Thiết kế Cố ý

Harness cố ý không có public status polling, watcher, transcript API hoặc session
manager riêng. Resumability là native session ID đi qua cùng MCP tool. Result
content đi qua durable Markdown artifact; cross-repo context đi qua QiQi task
prompt, không qua shared child-agent filesystem access.
