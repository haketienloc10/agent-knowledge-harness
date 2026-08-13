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
MCP delegate_repo_task calls
  ↓ START hoặc RESUME
Codex / Claude Code tại các repository con độc lập
  ↓ implementation + verification
  ↓ terminal structured result + native session_id
QiQi
  ↓ reconcile / task context / native resume / cross-repo knowledge
Người dùng
```

## Hai template

### `workspace-template/`

Đặt tại workspace root. Nó sở hữu QiQi, repository registry, topology, task
context, agent/model routing, MCP delegation và tri thức cross-repo.

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
│   ├── agent-routing.yaml
│   └── model-routing.md
├── mcp/qiqi_delegate/
│   ├── pyproject.toml
│   └── server.py
├── knowledge/
├── .qiqi/tasks/
├── docs/WORKSPACE_SETUP.md
└── scripts/
    ├── qiqi-mcp-server.sh
    └── workspace-check.sh
```

QiQi không quản lý pane/process hoặc polling. Repo-local work chỉ đi qua MCP tool
`delegate_repo_task`. Mỗi call chạy đúng một non-interactive START hoặc RESUME
invocation, giữ stdout/stderr ngoài QiQi context và chỉ trả terminal structured
result cùng native agent `session_id`.

Các call nhắm tới resolved Git root độc lập có thể active đồng thời. Trong cùng
`qiqi_delegate` server process, MCP từ chối concurrent invocation trên cùng
resolved Git root hoặc cùng native `session_id`. Dependency và shared mutable
resource vẫn do QiQi lập kế hoạch theo delegation wave.

Trong lúc một wave in-flight, QiQi áp dụng **Delegation Silence**: không phát
user-visible progress commentary và không poll trạng thái child.

`instructions/agent-routing.yaml` tách execution mechanics khỏi QiQi: mỗi agent
định nghĩa command/start_args/resume_args; mỗi route định nghĩa agent/model/flags.
Template hiện có adapter Codex và Claude Code. Public MCP schema không đổi khi
model hoặc native flags thay đổi.

### `repo-template/`

Đặt tại Git root của từng repository con. Nó giúp execution agent hiểu
architecture, verification và knowledge ownership nội bộ.

```text
repo-template/
├── AGENTS.md
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

## Ranh giới sở hữu

| Loại thông tin | Nơi lưu |
|---|---|
| Repository và đường dẫn local | Workspace `repos.yaml` |
| Topology/dependency liên repo | Workspace `SYSTEM_MAP.md` |
| Contract/decision cross-repo có evidence | Workspace `knowledge/` |
| Yêu cầu, blocker, terminal outcome và native session ID cần giữ | Workspace `.qiqi/tasks/` |
| Agent/model/native flags + START/RESUME argv | Workspace `instructions/agent-routing.yaml` |
| Policy chọn route | Workspace `instructions/model-routing.md` |
| Repo execution + repo/session conflict guard | MCP `delegate_repo_task` |
| Architecture, implementation, verification nội bộ | Repository con |

## START và RESUME

Public tool giữ một contract:

```text
delegate_repo_task(repository, task, route, session_id?)
```

- không có `session_id` → START native session mới;
- có `session_id` → RESUME native session đó bằng route đã chọn;
- tool trả native ID thật của Codex/Claude Code;
- resume chỉ thành công nếu invocation trả lại đúng ID được yêu cầu;
- đổi agent nghĩa là START mới + handoff context, không resume chéo ID;
- không chạy đồng thời hai RESUME dùng cùng native session ID.

Không có status/wait/transcript/separate-resume tool.

## Delegation Waves

QiQi có thể đặt nhiều repo task vào cùng wave khi chúng:

- thuộc các resolved Git root khác nhau;
- không phụ thuộc output/decision chưa có của nhau;
- không cùng thao tác shared mutable resource;
- không dùng cùng native session;
- có prompt và completion criteria độc lập.

Task có dependency hoặc conflict phải sang wave sau. Khi không chắc có conflict,
chạy tuần tự. Host có thể parallelize MCP calls hoặc không; correctness của
workflow không phụ thuộc parallel dispatch.

## Áp dụng vào Workspace

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
cd /path/to/multi-repo
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Sau đó khởi động Codex tại workspace root. Project-scoped `.codex/config.toml`
đăng ký STDIO MCP server `qiqi_delegate` và chỉ enable `delegate_repo_task`.

Xem `docs/WORKSPACE_SETUP.md` để điền repo registry, agent/model routing và chạy
START/RESUME/concurrency smoke test.

## Áp dụng vào Repository con

Với từng Git repository trong `repos.yaml`:

```bash
rsync -av --ignore-existing repo-template/ /path/to/multi-repo/<repository>/
cd /path/to/multi-repo/<repository>
bash scripts/repo-check.sh
```

Nếu repo đã có `AGENTS.md`, không ghi đè; gộp các nguyên tắc về Git-root boundary,
architecture, verification và final result contract.

## Thiết kế Cố ý

Harness cố ý không có status polling, watcher, daemon, transcript API hoặc session
manager riêng. Resumability chỉ là native session ID đi qua cùng MCP tool.
Concurrency được giới hạn theo resource: independent Git roots có thể chạy đồng
thời; trong cùng `qiqi_delegate` server process, cùng Git root hoặc cùng native
session bị chặn cứng. Dependency/shared resource được QiQi điều phối bằng
delegation waves.
