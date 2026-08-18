# QiQi Multi-repository Workspace Template

Template này đặt tại root của một local workspace chứa nhiều Git repository độc
lập. QiQi giữ vai trò Chief of Staff kỹ thuật; repo-local execution đi qua
`qiqi_delegate`, còn durable reusable knowledge đi qua Shared Knowledge MCP.

## Thành phần

```text
AGENTS.md                         # Orchestration + knowledge lifecycle policy
identity.md                       # Danh tính và hard boundaries
repos.yaml                        # Repository registry
SYSTEM_MAP.md                     # Live topology/contract liên repo
instructions/agent-routing.yaml   # Canonical execution route registry
instructions/model-routing.md     # QiQi exact-route selection policy
.codex/config.toml                # Project-scoped qiqi_delegate only
mcp/qiqi_delegate/                # Herdr-backed execution MCP
mcp/knowledge/                    # Shared Knowledge MCP + core/CLI/tests
.qiqi/tasks/                      # Optional workspace-specific task state
.qiqi/runs/                       # Durable execution result artifacts
docs/
├── WORKSPACE_SETUP.md
├── KNOWLEDGE_STORE.md            # External store format/setup/human-edit workflow
└── examples/
scripts/
├── qiqi-mcp-server.sh
├── qiqi-knowledge-mcp-server.sh
├── qiqi-knowledge-store.sh
├── knowledge-mcp-check.sh
└── workspace-check.sh
```

## Hai MCP, hai boundary

```text
qiqi_delegate
= repo-local execution lifecycle + native session + result handoff

qiqi_knowledge
= shared durable knowledge read/write mechanics
```

`qiqi_delegate` là project-scoped tại workspace vì chỉ QiQi gọi execution tool.
`qiqi_knowledge` phải được đăng ký **user scope** của Codex/Claude để cả QiQi và
Herdr-launched child session ở bất kỳ repo CWD nào cũng dùng được.

Knowledge Store không nằm trong workspace template. Nó được chọn bằng absolute
`QIQI_KNOWLEDGE_ROOT`, có thể là Git repository riêng.

## Shared Knowledge lifecycle

Đầu mỗi work turn, QiQi và repo agent:

```text
understand concern
→ generate multiple search terms
→ knowledge_read
→ work
```

Trước finalize:

```text
review reusable verified knowledge
→ knowledge_write(entries=[...])
```

Nếu không có update vẫn gọi:

```text
knowledge_write(entries=[])
```

Agent submit **semantic knowledge**, không tạo file/path/directory. Knowledge MCP
sở hữu canonical ID/path, mkdir, Markdown rendering, `INDEX.md`, cross-process lock,
optimistic revision và atomic replacement.

Contract quan trọng:

- scope kinds: `global`, `system`, `repo`, `domain`;
- ID: `<scope-kind>:<scope-id>:<canonical-name>`;
- routing summary/when-to-read/keywords dùng canonical terminology, ưu tiên English;
- aliases optional và có thể đa ngôn ngữ;
- content dùng ngôn ngữ bất kỳ;
- **không có field `language`**;
- sources/provenance bắt buộc;
- detail Markdown metadata là canonical; `INDEX.md` chỉ là materialized routing index;
- human có thể sửa detail Markdown trực tiếp rồi `reindex` + `check`;
- live source/test của owner repo thắng shared knowledge stale.

Chi tiết đầy đủ: `docs/KNOWLEDGE_STORE.md`.

## Execution model

```text
QiQi knowledge_read + workspace context
  ↓ self-contained live task prompt
qiqi_delegate
  ↓ Herdr + interactive Codex/Claude
Repo agent knowledge_read
  ↓ investigation / implementation / verification
  ↓ knowledge_write
  ↓ terminal result vào .qiqi/runs/...md
qiqi_delegate
  ↓ validate result + native identity
QiQi
  ↓ read result_path
  ↓ reconcile live Cross-repo Impact
  ↓ knowledge review/write ở orchestration layer
```

QiQi là broker duy nhất của **live execution result/evidence** giữa repositories.
Shared reusable knowledge không cần được copy qua QiQi prompt; child query trực tiếp
qua Knowledge MCP.

## Public execution contract

```text
delegate_repo_task(repository, task, route, session_id?)
```

- không `session_id` → START native session;
- có `session_id` → RESUME đúng native session;
- success chỉ trả `{session_id, result_path}`;
- QiQi phải đọc `result_path` trước bước tiếp theo;
- không RESUME chỉ để yêu cầu report lại.

START task có English title ngắn ở dòng không rỗng đầu tiên để derive readable
result filename. RESUME giữ same artifact/path.

## Result artifact

Newest result vẫn có compatibility contract:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

`### Repo-local Knowledge` **không khôi phục local knowledge store cũ**. Nó chỉ ghi
shared knowledge review/update audit (`None` hoặc shared knowledge IDs/revisions).
`### Cross-repo Impact` là live execution handoff cho QiQi, không phải knowledge
transport.

## Workspace ↔ Repository handoff

Producer live result phải đi qua QiQi:

```text
repo A result
→ QiQi đọc/reconcile
→ relevant live fact/evidence trong repo B prompt
→ repo B
```

Child không tự đọc sibling result artifact hoặc sibling repo source. Việc child đọc
shared curated knowledge qua Knowledge MCP không thay đổi boundary này.

## Herdr và routing

Herdr là internal runtime của `qiqi_delegate`. `instructions/model-routing.md` chỉ
chọn exact route; `instructions/agent-routing.yaml` là machine-readable source of
truth cho agent/model/native argv. Routing examples dưới `docs/examples/` không
phải runtime input.

## Concurrency và silence

Trong một `qiqi_delegate` server process:

```text
same resolved Git root → reject concurrent call
same native session_id → reject concurrent call
```

Khác Git root có thể active đồng thời nếu không dependency/shared-resource conflict.
Trong delegation wave QiQi không phát progress commentary và không poll child state.

Shared Knowledge Store dùng cross-process file lock và revision checks riêng, vì
nhiều QiQi/child/human có thể cùng truy cập store.

## Setup

```bash
# Execution MCP
uv sync --project mcp/qiqi_delegate
herdr integration install codex
herdr integration install claude

# Shared Knowledge MCP/store
export QIQI_KNOWLEDGE_ROOT=/absolute/path/to/shared-knowledge
uv sync --project mcp/knowledge
bash scripts/qiqi-knowledge-store.sh init
bash scripts/knowledge-mcp-check.sh
```

Sau đó đăng ký `qiqi_knowledge` ở user scope theo `docs/KNOWLEDGE_STORE.md`, chạy:

```bash
bash scripts/workspace-check.sh
```

và thực hiện smoke tests trong `docs/WORKSPACE_SETUP.md`.

`.codex/config.toml` của workspace cố ý chỉ enable `delegate_repo_task`; không thêm
Knowledge MCP project-scoped vào file đó.
