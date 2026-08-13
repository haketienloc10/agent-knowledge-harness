# Agent Knowledge Harness

Bộ khung để vận hành **QiQi** tại một local workspace chứa nhiều Git repository
độc lập, với execution boundary rõ giữa workspace coordinator và coding agent
trong từng repository con.

## Vòng kín

```text
Người dùng
  ↓ yêu cầu và quyết định
QiQi tại workspace
  ↓ synchronous MCP delegate_repo_task
Codex / Claude Code tại repository con
  ↓ implementation + verification
  ↓ terminal structured result + native session_id
QiQi
  ↓ task context / native resume / cross-repo knowledge khi cần
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
`delegate_repo_task`. Tool chạy đúng một non-interactive START hoặc RESUME
invocation, giữ stdout/stderr ngoài QiQi context và chỉ trả terminal structured
result cùng native agent `session_id`.

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
| Repo execution | MCP `delegate_repo_task` |
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
- đổi agent nghĩa là START mới + handoff context, không resume chéo ID.

Không có status/wait/transcript/separate-resume tool.

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
START/RESUME smoke test.

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
manager riêng. Resumability chỉ là native session ID đi qua cùng synchronous MCP
tool; lifecycle vẫn là một active delegation tại một thời điểm.
