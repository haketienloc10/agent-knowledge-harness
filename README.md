# Agent Knowledge Harness

Bộ khung để vận hành **QiQi — Chief of Staff kỹ thuật** tại multi-repository
workspace với hai boundary tách biệt:

```text
qiqi_delegate  → repo-local execution + native session + result handoff
qiqi_knowledge → shared durable knowledge read/write
```

## Vòng kín

```text
Người dùng
  ↓
QiQi knowledge_read + workspace context
  ↓ self-contained live task prompt
Repo A agent knowledge_read
  ↓ implementation / verification
  ↓ knowledge_write
  ↓ terminal result + live Cross-repo Impact
QiQi
  ↓ đọc result_path và reconcile
  ↓ live fact/evidence vào repo B prompt nếu cần
Repo B agent knowledge_read / work / knowledge_write
  ↓ terminal result
QiQi
  ↓ orchestration-level knowledge review/write
Người dùng
```

QiQi broker **live execution result/evidence** giữa repositories. Knowledge MCP
broker **durable reusable knowledge**. Child agent được đọc shared knowledge nhưng
không tự đọc sibling source hoặc sibling `.qiqi/runs` artifact.

## Workspace template

`workspace-template/` sở hữu QiQi, registry/topology, execution routing, hai MCP
runtime, result handoff và setup/checkers.

```text
workspace-template/
├── .codex/config.toml              # project-scoped qiqi_delegate only
├── AGENTS.md
├── identity.md
├── repos.yaml
├── SYSTEM_MAP.md
├── instructions/
│   ├── agent-routing.yaml
│   └── model-routing.md
├── mcp/
│   ├── qiqi_delegate/
│   └── knowledge/
├── .qiqi/runs/
├── docs/
│   ├── WORKSPACE_SETUP.md
│   ├── KNOWLEDGE_STORE.md
│   └── examples/
└── scripts/
    ├── qiqi-mcp-server.sh
    ├── qiqi-knowledge-mcp-server.sh
    ├── qiqi-knowledge-store.sh
    ├── knowledge-mcp-check.sh
    └── workspace-check.sh
```

Knowledge Store **không nằm trong workspace**. Nó là external Markdown store được
trỏ bởi `QIQI_KNOWLEDGE_ROOT`, phù hợp để đặt trong Git repository riêng.

## Repository template

`repo-template/` đặt tại mỗi Git root và giữ architecture/verification, Git-root
boundary, Shared Knowledge lifecycle và QiQi live-result handoff semantics.

Repo template không tạo `knowledge/`, `docs/domain/`, `docs/specs/` hay
`docs/decisions/` chỉ để phục vụ knowledge lifecycle. Durable knowledge đi qua
shared external store.

## Shared Knowledge contract

Public tools:

```text
knowledge_read(keywords, context?, limit?)
knowledge_write(entries)
```

Agent submit semantic knowledge, không chọn storage filename/path/directory.
Knowledge MCP sở hữu canonical identity/path, mkdir, Markdown rendering,
`INDEX.md`, file locking, optimistic revision và atomic replace.

Canonical identity:

```text
<scope-kind>:<scope-id>:<canonical-name>
```

Scope kinds: `global`, `system`, `repo`, `domain`.

Document rules:

- routing summary/when-to-read/keywords dùng canonical terminology, ưu tiên English;
- aliases optional, có thể đa ngôn ngữ;
- content tự do ngôn ngữ;
- **không có field `language`**;
- sources/provenance bắt buộc;
- detail document metadata là canonical source;
- `INDEX.md` chỉ là generated routing index;
- human có thể sửa detail Markdown trực tiếp rồi `reindex` + `check`;
- update dùng exact `id` + `expected_revision`;
- stale write bị reject;
- live owner-repo source/test thắng shared knowledge stale.

Đầu work turn agent gọi `knowledge_read`; trước finalize luôn review rồi gọi
`knowledge_write`, kể cả `entries=[]` khi không có knowledge đáng persist.

Chi tiết format và user-scope registration: `workspace-template/docs/KNOWLEDGE_STORE.md`.

## Vì sao Knowledge MCP dùng user scope

QiQi chạy ở workspace root còn Herdr launch execution agent tại exact child Git
root. Knowledge MCP phải độc lập CWD và khả dụng ở cả hai nơi, nên nó được đăng ký
ở user scope của Codex/Claude. Workspace `.codex/config.toml` cố ý chỉ chứa
`qiqi_delegate`.

## Execution contract

```text
delegate_repo_task(repository, task, route, session_id?)
```

Không `session_id` → START; có ID → RESUME đúng native session. Success chỉ trả:

```json
{
  "session_id": "<native-session-id>",
  "result_path": ".qiqi/runs/<session-artifact>.md"
}
```

QiQi phải đọc `result_path` trước quyết định tiếp theo và không RESUME chỉ để lấy
report lại.

Current result headings vẫn giữ compatibility:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

`Repo-local Knowledge` giờ chỉ audit shared knowledge review/update, không phải
local knowledge store. `Cross-repo Impact` là live execution signal, không phải
knowledge transport.

## Setup

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
cd /path/to/multi-repo

# execution
herdr integration install codex
herdr integration install claude
uv sync --project mcp/qiqi_delegate

# shared knowledge
export QIQI_KNOWLEDGE_ROOT=/absolute/path/to/shared-knowledge
uv sync --project mcp/knowledge
bash scripts/qiqi-knowledge-store.sh init
bash scripts/knowledge-mcp-check.sh
```

Đăng ký `qiqi_knowledge` ở Codex/Claude user scope theo `docs/KNOWLEDGE_STORE.md`,
sau đó chạy `bash scripts/workspace-check.sh` và smoke tests trong
`docs/WORKSPACE_SETUP.md`.

Repo con:

```bash
rsync -av --ignore-existing repo-template/ /path/to/multi-repo/<repository>/
cd /path/to/multi-repo/<repository>
bash scripts/repo-check.sh
```

## Thiết kế cố ý

Không có vector DB, embeddings, translation service hay LLM bên trong Knowledge MCP
MVP. Agent làm semantic keyword/distillation; MCP làm deterministic routing và
persistence mechanics. Không có public execution polling/transcript/session manager
ngoài `delegate_repo_task`.
