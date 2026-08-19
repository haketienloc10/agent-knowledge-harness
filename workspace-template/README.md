# QiQi Multi-repository Workspace Template

Template này đặt tại root của local workspace chứa nhiều Git repository độc lập.
QiQi giữ vai trò Chief of Staff kỹ thuật; mọi repo-local work đi qua MCP tool
`delegate_repo_task`.

Durable reusable knowledge **không nằm trong workspace template**. QiQi và execution
agents dùng cùng user-scoped Shared Knowledge MCP (`knowledge_read` /
`knowledge_write`) được cài từ `knowledge-template/`.

## Thành phần

```text
AGENTS.md                         # QiQi orchestration + knowledge policy
identity.md                       # Danh tính và hard boundaries
repos.yaml                        # Registry exact Git roots
SYSTEM_MAP.md                     # Live topology/ownership/dependency
instructions/agent-routing.yaml   # Canonical runtime route registry
instructions/model-routing.md     # QiQi exact-route selection policy
.codex/config.toml                # Project-scoped qiqi_delegate only
mcp/qiqi_delegate/
├── pyproject.toml
└── server.py
.qiqi/tasks/                      # Optional workspace-local task artifacts
.qiqi/runs/                       # Durable execution result artifacts
docs/
├── WORKSPACE_SETUP.md
└── examples/
scripts/qiqi-mcp-server.sh
scripts/workspace-check.sh
```

Workspace cố ý **không có `knowledge/` directory** để tránh tạo một truth store thứ
hai cạnh Shared Knowledge Store.

## Hai MCP độc lập

```text
qiqi_delegate
= repo execution / native session / result handoff

knowledge
= reusable durable knowledge retrieval / persistence
```

`.codex/config.toml` tại workspace chỉ đăng ký `qiqi_delegate`. Knowledge MCP được
đăng ký user/global scope để fresh QiQi session và Herdr-launched child agents ở
các repository khác nhau cùng thấy một service, independent CWD.

## Execution + Knowledge Model

```text
QiQi
  ↓ understand task
  ↓ knowledge_read(task keywords)
  ↓ live SYSTEM_MAP / existing result evidence
  ↓ self-contained task prompt + route + optional session_id
qiqi_delegate
  ↓ Herdr workspace + real interactive Codex/Claude
Execution agent
  ↓ knowledge_read(task keywords)
  ↓ live repo investigation / implementation / verification
  ↓ knowledge_write(distilled reusable knowledge or entries=[])
  ↓ terminal Result vào .qiqi/runs/...md
qiqi_delegate
  ↓ validate result + native identity
  ↓ return {session_id, result_path}
QiQi
  ↓ read/reconcile result
  ↓ downstream live handoff nếu cần
  ↓ knowledge_write(system/global conclusion or entries=[])
```

Shared knowledge là context, không mạnh hơn live owner source/test. Current repo và
`context.repo/domain` chỉ là ranking hints trong retrieval, không giới hạn namespace.

## Workspace ↔ Repository Handoff

QiQi là handoff broker duy nhất giữa repositories đối với **live execution
evidence**.

Producer → consumer dependency vẫn là:

```text
repo A terminal result
→ QiQi đọc + reconcile
→ relevant fact/evidence trong repo B task prompt
→ repo B
```

Repo B không tự mở repo A source/result. Repo B được phép independently query
Shared Knowledge MCP vì đó là durable curated context, không phải live child state.

`### Cross-repo Impact` trong result vẫn là execution-impact signal: persist knowledge
không thay thế handoff khi repository khác còn cần investigation/implementation/
verification.

## Shared Knowledge Lifecycle

Khi đã hiểu work turn, QiQi tạo nhiều relevant search terms và gọi:

```text
knowledge_read(keywords, context?, limit?)
```

Trước khi user task kết thúc, QiQi review reusable verified conclusion và gọi:

```text
knowledge_write(entries)
```

Nếu không có durable candidate, vẫn dùng `entries=[]` để ghi nhận review hoàn tất.
Agent không truyền knowledge path/filename/directory; MCP sở hữu storage mechanics.

Nếu Knowledge MCP read lỗi, không được diễn giải như “store không có knowledge”.
Nếu durable candidate tồn tại nhưng write lỗi, không silently report như đã persist.

## Public qiqi_delegate Contract

```text
delegate_repo_task(repository, task, route, session_id?)
```

- không có `session_id` → START native Codex/Claude session mới;
- có `session_id` → RESUME đúng native session đó;
- cross-agent resume bị từ chối;
- tool synchronous tới terminal turn hoặc failure;
- success chỉ trả native `session_id` + workspace-relative `result_path`.

QiQi phải đọc `result_path` trước khi quyết định bước tiếp theo. Relevant artifact
đã đủ evidence thì trả lời trực tiếp; không START/RESUME chỉ để lấy lại hoặc trình
bày lại report.

## Prompt Ownership

Task prompt do QiQi sở hữu: outcome, scope, live dependency evidence, constraints và
verification. Shared durable knowledge không cần được copy toàn bộ vào prompt vì
child agent có Knowledge MCP; **live producer result vẫn phải inline qua QiQi**.

Với START, dòng không rỗng đầu tiên của `task` là English title ngắn (3–8 từ,
ưu tiên ASCII) để MCP derive readable result slug. RESUME giữ exact result artifact.

## Result Artifact

Newest Result hiện giữ compatibility headings:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

`Repo-local Knowledge` là legacy label: repo policy dùng section này để ghi Shared
Knowledge MCP IDs create/update, `None`, hoặc persistence failure. Nó không còn tạo
nghĩa vụ ghi durable knowledge vào repository.

## Herdr Runtime

Herdr vẫn là internal runtime của `qiqi_delegate`:

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

MCP yêu cầu adapter integration `current`, tạo workspace tại exact Git root, launch
real interactive TUI, wait terminal state, lấy native identity rồi cleanup.

## Setup

Cài Shared Knowledge MCP **trước** từ `knowledge-template/`, mở fresh agent session,
sau đó setup workspace:

```bash
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Chi tiết và smoke tests nằm trong `docs/WORKSPACE_SETUP.md`.
