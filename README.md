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
Execution agent tại repository con
  ↓ implementation + verification
  ↓ terminal structured result
QiQi
  ↓ task context / cross-repo knowledge khi cần
Người dùng
```

## Hai template

### `workspace-template/`

Đặt tại workspace root. Nó sở hữu QiQi, repository registry, topology, task
context, model routing, MCP delegation và tri thức cross-repo.

```text
workspace-template/
├── .codex/config.toml
├── AGENTS.md
├── identity.md
├── repos.yaml
├── SYSTEM_MAP.md
├── KNOWLEDGE.md
├── README.md
├── instructions/model-routing.md
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

QiQi không quản lý child session/pane/process. Repo-local work chỉ đi qua MCP tool
`delegate_repo_task`. Tool tự chạy one-shot Codex, giữ transcript ngoài QiQi
context và chỉ trả structured terminal result.

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
| Yêu cầu, blocker và terminal outcome cần giữ | Workspace `.qiqi/tasks/` |
| Model/reasoning effort | Workspace `instructions/model-routing.md` |
| Repo execution | MCP `delegate_repo_task` |
| Architecture, implementation, verification nội bộ | Repository con |

## Áp dụng vào Workspace

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
cd /path/to/multi-repo
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Sau đó khởi động Codex tại workspace root. Project-scoped `.codex/config.toml`
đăng ký STDIO MCP server `qiqi_delegate` và chỉ enable `delegate_repo_task`.

Xem `docs/WORKSPACE_SETUP.md` để điền registry/model routing và chạy fresh-session
test.

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

Harness cố ý không có child-session manager, status polling, watcher, daemon,
resume workflow hoặc transcript API. Nếu sau này cần concurrency hay resumability,
chỉ thêm sau khi có use case thực tế và không làm bẩn QiQi orchestration context.
