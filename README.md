# Agent Knowledge Harness

Bộ khung gồm ba lớp độc lập để vận hành QiQi trong multi-repository workspace và chia
sẻ durable knowledge giữa nhiều workspace/repository/session.

## Kiến trúc

```text
                         Shared Knowledge Store
                         Markdown + INDEX.md
                                ▲      │
                     write      │      │ search/read
                                │      ▼
                         Knowledge MCP (user scope)
                    search → exact read → write
                           ▲                    ▲
                           │                    │
Người dùng → QiQi workspace ──────┐       Repo execution agents
              │                   │              ▲
              │ TaskPacket        │              │ native final response
              ▼                   │              │
        qiqi_delegate MCP ────────┴──────────────┘
              │
              │ Herdr START / RESUME
              ▼
       independent Git repos
```

### `workspace-template/`

QiQi control plane tại workspace root:

- `repos.yaml` registry exact Git roots;
- `SYSTEM_MAP.md` live topology/ownership/dependency;
- structured TaskPacket cho mỗi delegation;
- model/runtime routing;
- synchronous `qiqi_delegate` START/RESUME;
- native final-response handoff qua Stop hook;
- MCP-owned SQLite session ownership dưới `.qiqi/state/`;
- dependency waves, evidence reuse và user reporting.

Workspace **không sở hữu durable knowledge store**. `.qiqi/runs/` chỉ có thể tồn tại
như legacy migration source cho session contract cũ; turn mới không dùng Markdown
artifact làm transport.

### `repo-template/`

Policy tối thiểu cho execution agent tại mỗi Git root:

- architecture + verification routing;
- Git-root/sibling-repo boundaries;
- closed-world TaskPacket context từ QiQi;
- conditional Shared Knowledge search/read/write lifecycle;
- cross-repo impact handoff về QiQi;
- native final assistant response là semantic handoff, không fixed headings.

### `knowledge-template/`

Repository-independent knowledge subsystem:

```text
knowledge-template/
├── README.md
├── store/
│   ├── INDEX.md
│   ├── global/
│   ├── systems/
│   ├── repos/
│   └── domains/
├── mcp/knowledge/
│   ├── contracts.py
│   ├── core.py
│   ├── server.py
│   ├── pyproject.toml
│   └── tests/
├── scripts/
│   ├── install-user-mcp.sh
│   ├── knowledge-mcp-server.sh
│   └── knowledge.py
└── skills/knowledge-distill/SKILL.md
```

Store có thể nằm trong repo riêng/path khác; MCP chỉ dùng explicit
`KNOWLEDGE_STORE_ROOT`, không suy luận từ CWD.

## Structured input, native output

`qiqi_delegate` cố ý làm input chặt và output linh hoạt.

### Input: TaskPacket

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

Nguyên tắc chính:

- `user_request` giữ wording gốc liên quan đến repo task;
- `objective`, `scope`, `constraints`, `acceptance_criteria` là repo-local contract;
- mọi live fact/decision/knowledge QiQi **đã dùng để quyết định task semantics** phải
  nằm trong `required_context` kèm provenance + certainty;
- child không chia sẻ hidden conversation/reasoning/workspace state của QiQi;
- Shared Knowledge của child dùng để discover/enrich/verify theo repo policy, không
  thay required premise QiQi đã dùng để tạo task.

### Output: native final response

MCP không ép execution agent ghi một Markdown schema. Native Stop hook chuyển full
`last_assistant_message` về MCP; transport không đọc terminal viewport/scrollback.

Terminal success thông thường:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled",
  "agent_response": "<exact native final assistant message>"
}
```

Nếu agent blocked trước native final response, MCP giữ session ownership để QiQi có
thể RESUME và trả `agent_response: null`; không giả mạo response từ screen/transcript.
Native response transport fail closed nếu Stop hook không trả result hợp lệ.

## Hai loại context

### Live execution evidence

Repo source/test và native result hiện tại là live truth. Khi repo B phụ thuộc work ở
repo A:

```text
repo A native response
→ QiQi reconcile
→ relevant fact/evidence + provenance trong repo B required_context
→ repo B
```

Child không tự mở sibling source, sibling result history hoặc workspace runtime state.

### Durable shared knowledge

Reusable, non-trivial, evidence-backed conclusion được persist qua Knowledge MCP. QiQi
và repo agents đều query cùng store. Current repo chỉ boost ranking; nó không giới hạn
namespace đọc được.

Nếu shared knowledge mâu thuẫn live source/test trong owner repo, live source/test
thắng và verified replacement conclusion mới được update knowledge khi phù hợp.

## Knowledge API — progressive disclosure

Public tools:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_write(entries)
```

Caller hiểu task rồi quyết định có cần durable context hay không. MCP không phải
ceremony cho mọi turn.

### Search

`knowledge_search` rank deterministic từ generated `INDEX.md`, không dùng embedding,
vector DB, translator hoặc LLM. Caller thường tạo khoảng 3–8 discriminative concepts.

Search trả bounded **decision cards** để chọn document:

```text
id
title
scope
summary
bounded when_to_read
bounded match reasons
score
```

Search card không trả `content`, `sources`, `revision`, physical `path` hoặc duplicate
`canonical_name`. `limit=10` nghĩa tối đa 10 candidate cards, **không** hydrate 10
full documents. Selected top hits vẫn được revision-check với detail file để stale
index fail rõ.

### Exact read

Sau search, caller hydrate chỉ một hoặc tối đa hai exact IDs:

```text
knowledge_read(ids=[...])
```

Full read trả stable ID, SHA-256 revision, canonical name, title/scope, full nested
routing, sources và semantic content. `content` không chứa storage H1; writer tự render
heading. Physical path không thuộc read API.

`knowledge_search` cố ý **không trả revision**. Vì vậy existing knowledge phải được
full-read trước update; agent không thể dùng search summary rồi overwrite document
chưa đọc.

### Write

Agent không tạo knowledge file trực tiếp. Create submit semantic fields, MCP derive:

```text
id   = <scope-kind>:<scope-id>:<canonical-name>
path = canonical namespace path
```

Update bắt buộc exact `id` + `expected_revision` từ full `knowledge_read`. Human edit
ngoài MCP làm revision/index stale và stale search/read/write bị reject cho tới khi
reindex.

Knowledge lifecycle:

- MUST search khi prior reusable knowledge có khả năng đổi interpretation,
  orchestration, implementation hoặc verification;
- MAY search khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- SKIP cho typo/format/comment-only, exact local lookup, report/status-only hoặc
  mechanical work nơi durable context không thể đổi action;
- substantive work có khả năng tạo/xác nhận reusable conclusion phải review/write;
- trivial/mechanical/report-only work được skip write;
- required review không candidate mới dùng `entries=[]`;
- trước create/update phải search existing concept; update existing target phải full
  read trước để lấy revision và full semantic payload.

## Language

Không có field `language`.

```text
canonical_name + routing metadata
→ canonical terminology, thường English

aliases
→ multilingual / legacy / acronym / project terms

content
→ Vietnamese / English / mixed tùy ý
```

Retrieval không phụ thuộc ngôn ngữ body.

## Human maintenance

Human được phép tạo/sửa detail Markdown trực tiếp theo schema trong
`knowledge-template/README.md`.

Sau direct edit:

```bash
python3 knowledge-template/scripts/knowledge.py check --root /path/to/store
python3 knowledge-template/scripts/knowledge.py reindex --root /path/to/store
python3 knowledge-template/scripts/knowledge.py check --root /path/to/store
```

Detail metadata là canonical; `INDEX.md` là generated projection.

## Cài Knowledge MCP

```bash
cd knowledge-template
bash scripts/install-user-mcp.sh --store-root /path/to/shared-knowledge/store
```

Installer tạo stable wrapper, cài knowledge-distill skill và đăng ký MCP `knowledge`
với Codex global config / Claude user scope khi CLI tương ứng có sẵn. Existing
registration cùng tên không bị overwrite.

Mở fresh agent session rồi smoke-test tool inventory có đủ:

```text
knowledge_search
knowledge_read
knowledge_write
```

## Cài workspace

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
cd /path/to/multi-repo
herdr integration install codex
herdr integration install claude
herdr integration status
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Project `.codex/config.toml` chỉ đăng ký `qiqi_delegate`; Knowledge MCP không duplicate
vào workspace config. Sau static/unit checker, chạy fresh-session acceptance smoke
trên installed Claude/Codex CLI thực tế cho adapter đang dùng.

## Cài repo template

```bash
rsync -av --ignore-existing repo-template/ /path/to/multi-repo/<repo>/
cd /path/to/multi-repo/<repo>
bash scripts/repo-check.sh
```

Repo agent hiểu concern rồi áp dụng Knowledge decision rule nhưng không đọc sibling
source/result/runtime state.

## Migrate workspace đã tồn tại

Từ checkout của `agent-knowledge-harness`:

```bash
bash scripts/migrate-workspace.sh --dry-run /path/to/multi-repo
bash scripts/migrate-workspace.sh /path/to/multi-repo
bash scripts/migrate-workspace.sh --status /path/to/multi-repo
```

Migration definitions là JSON dưới `migrations/`, pin exact `from_ref` / `to_ref` và
khai báo strategy riêng từng file (`replace`, `merge`, `delete`, `manual_review`).
Preflight chạy cho workspace + toàn bộ repo trước khi ghi managed file nào; state lưu
ở `.qiqi/agent-knowledge-harness-migrations.tsv`.

## Thiết kế cố ý

- Knowledge Store không phụ thuộc current workspace/repo.
- Search và full read là hai stage riêng; candidate discovery không hydrate full top-N.
- Agent submit semantic knowledge; MCP materialize file.
- Knowledge identity không phải filesystem path.
- Human Markdown edit là first-class workflow.
- Knowledge usage conditional theo task semantics, không per-turn ritual.
- qiqi_delegate dùng SQLite cho execution session ownership; Knowledge MCP giữ
  Markdown store riêng.
- qiqi_delegate không dùng terminal viewport/undocumented transcript schema để vận
  chuyển semantic result.
- QiQi broker live evidence; Knowledge MCP broker reusable knowledge.
