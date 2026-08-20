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
├── core.py                       # TaskPacket + native capture validation + SQLite state
├── result_hook.py                # Native Stop-hook sink
├── server.py                     # Herdr-backed MCP execution boundary
├── pyproject.toml
└── tests/
.qiqi/tasks/                      # Optional workspace-local task artifacts
.qiqi/state/                      # Runtime SQLite state; generated, gitignored
.qiqi/runs/                       # Legacy-only migration input; generated path gitignored
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
= repo execution / native session / structured input / native final response

knowledge
= reusable durable knowledge retrieval / persistence
```

`.codex/config.toml` tại workspace chỉ đăng ký `qiqi_delegate`. Knowledge MCP được
đăng ký user/global scope để fresh QiQi session và Herdr-launched child agents ở
các repository khác nhau cùng thấy một service, independent CWD.

## Execution + Knowledge Model

Knowledge MCP là **conditional path**, không phải bước bắt buộc cho mọi turn.
`AGENTS.md` quyết định khi nào QiQi/repo agent MUST/MAY/SKIP read và khi nào
substantive work phải review/write.

```text
QiQi
  ↓ understand user intent
  ↓ conditional knowledge_read nếu durable context có thể đổi orchestration/answer
  ↓ live SYSTEM_MAP / previous native response evidence
  ↓ structured TaskPacket
     - original user_request
     - objective + scope
     - required_context + provenance
     - constraints + acceptance + verification + unknowns
qiqi_delegate
  ↓ validate packet + render closed-world prompt
  ↓ Herdr workspace + real interactive Codex/Claude
Execution agent
  ↓ understand repo-local concern
  ↓ conditional knowledge_read theo repo AGENTS.md
  ↓ live repo investigation / implementation / verification
  ↓ conditional knowledge review/write nếu substantive work tạo reusable conclusion
  ↓ native final assistant response
native Stop hook
  ↓ exact final message → invocation-private sink
qiqi_delegate
  ↓ validate native session identity
  ↓ persist MCP-owned session/turn state
  ↓ return {session_id, turn_id, state, agent_response}
QiQi
  ↓ read/reconcile full agent_response
  ↓ downstream required_context nếu cần
  ↓ conditional knowledge review/write cho durable system/global conclusion
```

Shared knowledge là context, không mạnh hơn live owner source/test. Current repo và
`context.repo/domain` chỉ là ranking hints trong retrieval, không giới hạn namespace.

## Workspace ↔ Repository Handoff

QiQi là handoff broker duy nhất giữa repositories đối với **live execution
evidence**.

Producer → consumer dependency:

```text
repo A native agent_response
→ QiQi đọc + reconcile
→ relevant fact/evidence + provenance trong repo B required_context
→ repo B
```

Repo B không tự mở repo A source/runtime state. Repo B được phép independently query
Shared Knowledge MCP vì đó là durable curated context, không phải live child state.

Nếu QiQi đã dùng một durable knowledge fact để quyết định repository, scope,
constraint, dependency hoặc acceptance criterion, fact đó phải được inline vào
`required_context`; child không được kỳ vọng tự query lại đúng premise đó.

## Shared Knowledge Lifecycle

Sau khi hiểu concern, agent áp dụng decision rule:

- **MUST read** khi prior reusable knowledge có khả năng đổi interpretation,
  orchestration, implementation hoặc verification;
- **MAY read** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- **SKIP read** cho typo/format/comment-only, exact local lookup, report/status-only
  từ evidence đã đủ hoặc mechanical work nơi durable context không thể đổi action.

QiQi không cần duplicate repo-agent query nếu knowledge chỉ có thể ảnh hưởng
repo-local implementation và không ảnh hưởng orchestration/TaskPacket.

Với substantive work có khả năng tạo hoặc xác nhận reusable conclusion, agent
review durable knowledge và gọi:

```text
knowledge_write(entries)
```

Trivial/mechanical/report-only work được skip write. Khi review là required nhưng
không có durable candidate, dùng `entries=[]`; không dùng empty write như ceremony.
Trước create/update candidate phải search existing concept để dedupe và ưu tiên
update.

Agent không truyền knowledge path/filename/directory; MCP sở hữu storage mechanics.
Nếu Knowledge MCP read lỗi, không được diễn giải như “store không có knowledge”.
Nếu durable candidate tồn tại nhưng write lỗi, không silently report như đã persist.

## Public qiqi_delegate Contract

Public tool dùng structured fields:

```text
delegate_repo_task(
  repository,
  route,
  user_request,
  objective,
  scope,
  out_of_scope,
  required_context,
  constraints,
  acceptance_criteria,
  verification,
  known_unknowns,
  session_id?
)
```

- `scope` và `acceptance_criteria` phải non-empty;
- `required_context` item có đúng `fact`, `source`, `certainty`;
- certainty là `verified`, `user-provided` hoặc `authoritative-decision`;
- không có `session_id` → START native Codex/Claude session mới;
- có `session_id` → RESUME đúng native session đó;
- cross-agent/repository resume bị từ chối;
- tool synchronous tới terminal turn hoặc failure;
- success trả native `session_id`, QiQi `turn_id`, `state` và exact
  `agent_response`.

Relevant native response đã đủ evidence thì QiQi trả lời trực tiếp; không START/
RESUME chỉ để lấy lại hoặc trình bày lại report.

## Structured Input / Closed-world Context

QiQi luôn giữ cả hai lớp:

```text
original user_request
+ QiQi repo-local objective / explicit required context
```

Child agent không chia sẻ hidden conversation, hidden reasoning, workspace control
context hoặc sibling-repository state của QiQi. Đối với external/live facts, những
gì không có trong TaskPacket không được giả định là child đã biết.

`required_context` là required premise, không phải search hint. Shared Knowledge MCP
của child dùng cho discovery/enrichment/verification khác; nó không thay thế fact
QiQi đã dùng để quyết định semantics của delegation.

Không còn English-title convention để tạo result filename vì storage concern không
nằm trong task semantics.

## Native Result Handoff

Execution agent không bị ép vào result schema hay fixed headings. Final assistant
response của agent là semantic handoff và được capture qua native Stop hook.

MCP **không** dùng:

- terminal viewport/scrollback;
- pane capture làm result transport;
- transcript JSONL parsing;
- agent-written Markdown result artifact.

Vì vậy response dài hơn một screen không bị mất phần đã scroll khỏi viewport.
QiQi nhận nguyên văn message native mà hook cung cấp và đánh giá completion bằng
TaskPacket + evidence trong response.

Runtime ownership/history nằm trong MCP-owned:

```text
.qiqi/state/qiqi_delegate.sqlite3
```

QiQi và child không đọc/sửa database này. `.qiqi/runs/` chỉ còn compatibility
bridge cho ownership metadata của session legacy khi RESUME; turn mới không đọc hay
ghi Markdown result tại đó.

## Herdr Runtime

Herdr vẫn là internal runtime của `qiqi_delegate`:

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

MCP yêu cầu adapter integration `current`, tạo workspace tại exact Git root, launch
real interactive TUI, wait terminal state, lấy native identity rồi cleanup.

Để capture exact final response, MCP inject invocation-scoped native Stop hook:

- Claude: `--settings` inline JSON chứa `Stop`/`StopFailure` command hooks;
- Codex: command `Stop` hook qua `-c hooks.Stop=...`, bật `features.hooks=true` và
  dùng invocation-scoped `--dangerously-bypass-hook-trust` cho hook command do MCP
  tự tạo.

Codex trust bypass chỉ được MCP inject cho invocation này; không đặt flag đó trong
route policy hay user prompt. Nếu native hook không trả final message hợp lệ, MCP
fail rõ và **không fallback** sang screen/transcript.

## Setup

Cài Shared Knowledge MCP **trước** từ `knowledge-template/`, mở fresh agent session,
sau đó setup workspace:

```bash
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Chi tiết, security note và smoke tests nằm trong `docs/WORKSPACE_SETUP.md`.
