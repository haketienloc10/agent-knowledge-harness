# QiQi Multi-repository Workspace Template

Template này đặt tại root của một local workspace chứa nhiều Git repository độc lập. QiQi giữ vai trò Chief of Staff kỹ thuật; mọi repo-local work đi qua MCP tool `delegate_repo_task`.

## Thành phần

```text
AGENTS.md                         # Policy orchestration của QiQi
identity.md                       # Danh tính và giới hạn
repos.yaml                        # Registry repository
SYSTEM_MAP.md                     # Quan hệ/contract liên repo
KNOWLEDGE.md                      # Router tri thức cross-repo
instructions/agent-routing.yaml   # Interactive agent/model/flags + START/RESUME argv
instructions/model-routing.md     # Policy profile → route
.codex/config.toml                # Project-scoped MCP registration
mcp/qiqi_delegate/
├── pyproject.toml                # MCP runtime dependencies
└── server.py                     # Herdr-backed delegate_repo_task
knowledge/                        # Durable cross-repo knowledge
.qiqi/tasks/                      # Working context + session/result pointers
.qiqi/runs/                       # Durable MCP result artifacts (runtime-created)
docs/WORKSPACE_SETUP.md           # Setup/takeover
scripts/qiqi-mcp-server.sh        # MCP STDIO launcher
scripts/workspace-check.sh        # Harness checker
```

## Execution Model

QiQi sở hữu task semantics và route selection. MCP sở hữu Herdr lifecycle, native session identity và result handoff.

```text
QiQi
  ↓ task prompt + route + optional session_id
MCP delegate_repo_task
  ↓ Herdr workspace + real interactive Codex/Claude
  ↓ synchronous prompt/wait
Execution agent
  ↓ implementation / investigation / verification
  ↓ write newest Result section into .qiqi/runs/...md
MCP
  ↓ validate result + native identity
  ↓ return {session_id, result_path}
QiQi
  ↓ read result_path
  ↓ reconcile outcome / dependency / next decision
```

Mỗi call synchronous: chỉ resolve sau khi interactive turn settle (`idle`, `done` hoặc `blocked`) hoặc fail. Không có public `status`, `wait`, `read`, separate `resume`, `list-runs` hay transcript tool.

## Public MCP Contract

```text
delegate_repo_task(repository, task, route, session_id?)
```

- không có `session_id` → START native Codex/Claude session mới;
- có `session_id` → RESUME đúng native session đó;
- `session_id` là native ID opaque; MCP không infer RESUME từ repository;
- cross-agent resume bị từ chối.

Success return chỉ gồm:

```json
{
  "session_id": "<native-session-id>",
  "result_path": ".qiqi/runs/<repo>-<initial-task-slug>-<session-id>.md"
}
```

QiQi phải đọc `result_path` trước khi quyết định bước tiếp theo. Không RESUME chỉ để yêu cầu agent lặp lại report đã nằm trong result artifact.

## Prompt Ownership

Task prompt do QiQi quyết định. MCP không thêm operating policy về scope, implementation, verification hoặc repo behavior. MCP chỉ append một **result-handoff protocol footer** để agent biết exact result artifact, pending marker, required headings và `Outcome = completed|blocked`.

## Result Artifact

Mỗi native session có một durable Markdown artifact dưới `.qiqi/runs/`.

START tạo pending artifact trước khi native identity có sẵn, prompt actual task, sau đó validate và promote atomically sang filename chứa native session ID. RESUME resolve chính xác artifact hiện có bằng repository + native `session_id`, append `Task N / Result N`, rồi trả lại cùng `result_path`.

Newest result có headings:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

QiQi được đọc `.qiqi/runs/` vì đây là workspace-level terminal handoff, không phải repo-local source investigation.

## Herdr Runtime

Herdr là internal runtime của MCP. Chuẩn bị integration cho agent sẽ dùng:

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

MCP yêu cầu selected adapter integration ở trạng thái `current`, tự ensure named Herdr session/server (mặc định `qiqi-delegate`), tạo workspace tại exact Git root, launch real interactive Codex/Claude TUI, prompt/wait, lấy native identity và đóng workspace sau turn.

QiQi không quản lý Herdr pane/workspace/status trong normal workflow.

## Routing

`instructions/agent-routing.yaml` là source of truth machine-readable. Agent entry định nghĩa `command`, `adapter`, `start_args`, `resume_args`; route entry định nghĩa `agent`, `model`, `args`.

Runtime placeholders:

```text
{model}
{session_id}
{result_dir}
{route_args}
```

`start_args` không chứa `{session_id}`; `resume_args` phải chứa `{session_id}`. Registry dùng interactive CLI, không dùng `codex exec`, `claude -p`, JSON output schema hoặc output envelope làm execution transport.

QiQi chỉ chọn route; không truyền raw model/CLI flags qua MCP public API.

## Concurrency

Trong cùng `qiqi_delegate` server process:

```text
same resolved Git root → reject concurrent call
same native session_id → reject concurrent call
```

Khác Git root và khác native session có thể chạy đồng thời nếu không dependency/shared-resource conflict. Dependency và shared external resource do QiQi lập kế hoạch.

## Delegation Silence

Khi delegation wave in-flight, QiQi không phát user-visible progress commentary và không poll child state. Sau terminal tool success, QiQi đọc result artifact; sau khi đủ result của wave mới reconcile và giao tiếp tiếp.

## Ranh giới

- Workspace root giữ orchestration và tri thức cross-repo.
- Repository con giữ architecture/domain/implementation/verification.
- QiQi không tự đọc/sửa/chạy repo-local workflow.
- Execution agent chỉ được ghi ngoài Git root vào exact result artifact mà MCP handoff cho turn đó.
- MCP failure không fallback sang shell-based child agent.
- Herdr là implementation detail của MCP, không phải public orchestration API.

## Sử dụng

1. Sao chép template vào workspace root.
2. Điền `repos.yaml`, `SYSTEM_MAP.md`, routing và knowledge index.
3. Cài/kiểm tra Herdr integrations cho agent sẽ dùng.
4. Chạy `uv sync --project mcp/qiqi_delegate`.
5. Chạy `bash scripts/workspace-check.sh`.
6. Khởi động Codex tại workspace root; `.codex/config.toml` chỉ enable `delegate_repo_task`.
7. Làm theo `docs/WORKSPACE_SETUP.md` để smoke test START/RESUME, result artifact continuity và concurrency guard.

Không dùng template như monorepo wrapper và không chạy Git ở workspace root để suy luận trạng thái repo con.
