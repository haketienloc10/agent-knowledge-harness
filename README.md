# Agent Knowledge Harness

Bộ khung gồm ba lớp độc lập để vận hành QiQi trong multi-repository workspace và
chia sẻ durable knowledge giữa nhiều workspace/repository/session.

## Kiến trúc

```text
                         Shared Knowledge Store
                         Markdown + INDEX.md
                                ▲      │
                                │      ▼
                         Knowledge MCP (user scope)
                          read            write
                           ▲                ▲
                           │                │
Người dùng → QiQi workspace ──────┐   Repo execution agents
              │                   │          ▲
              │ TaskPacket        │          │ native final response
              ▼                   │          │
        qiqi_delegate MCP ────────┴──────────┘
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

Workspace **không sở hữu durable knowledge store**. `.qiqi/runs/` chỉ có thể tồn
tại như legacy migration source cho session đã được tạo bởi contract cũ; turn mới
không dùng Markdown artifact làm transport.

### `repo-template/`

Policy tối thiểu cho execution agent tại mỗi Git root:

- architecture + verification routing;
- Git-root/sibling-repo boundaries;
- closed-world TaskPacket context từ QiQi;
- conditional Shared Knowledge MCP read/write lifecycle;
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

Public execution boundary:

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

Các nguyên tắc chính:

- `user_request` giữ wording người dùng liên quan đến repo task;
- `objective`, `scope`, `constraints` và `acceptance_criteria` là repo-local contract;
- mọi live fact/decision/knowledge mà QiQi **đã dùng để quyết định task semantics**
  phải nằm trong `required_context` kèm provenance + certainty;
- child không chia sẻ hidden conversation/reasoning/workspace state của QiQi;
- Shared Knowledge MCP của child dùng để discover/enrich/verify theo repo policy,
  không thay required premise mà QiQi đã dùng để tạo task.

### Output: native final response

MCP không ép execution agent ghi một Markdown schema. Agent chọn structure phù hợp
implementation, investigation, review, design hoặc loại task thực tế.

Native Stop hook chuyển full `last_assistant_message` về MCP. Vì transport không
đọc terminal viewport/scrollback, response dài hơn một screen không bị cắt chỉ vì
đã scroll khỏi TUI.

Terminal success thông thường:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled",
  "agent_response": "<exact native final assistant message>"
}
```

Claude native failure có thể trả `state: "failed"` cùng response/error detail mà
StopFailure hook cung cấp.

Nếu Herdr phát hiện agent đang **blocked chờ interactive input trước khi có native
final response**, MCP phải giữ native session ownership để QiQi có thể RESUME đúng
conversation. Blocked handoff không được giả mạo một `agent_response` mà agent chưa
thực sự phát ra.

Runtime không fallback sang terminal screen hoặc transcript parser nếu native result
capture thiếu; failure phải rõ thay vì silently trả report bị cắt.

## Hai loại context

### Live execution evidence

Repo source/test và native result hiện tại là live truth. Khi repo B phụ thuộc work
vừa xảy ra ở repo A:

```text
repo A native response
→ QiQi reconcile
→ relevant fact/evidence + provenance trong repo B required_context
→ repo B
```

Child không tự mở sibling source, sibling result history hoặc workspace runtime
state.

### Durable shared knowledge

Reusable, non-trivial, evidence-backed conclusion được persist qua Knowledge MCP.
QiQi và repo agents đều có thể query cùng store trực tiếp. Current repository chỉ
boost ranking; nó không giới hạn namespace đọc được.

Nếu shared knowledge mâu thuẫn live source/test trong owner repo, live source/test
thắng và verified reusable conclusion mới phải update knowledge khi phù hợp.

## Knowledge API

MVP expose đúng hai tools:

```text
knowledge_read(keywords, context?, limit?)
knowledge_write(entries)
```

Caller hiểu task rồi quyết định có cần durable context hay không. MCP không phải
ceremony bắt buộc cho mọi turn:

- MUST read khi prior reusable knowledge có khả năng đổi interpretation,
  orchestration, implementation hoặc verification;
- MAY read khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- SKIP read cho typo/format/comment-only, exact local lookup, report/status-only từ
  evidence đã đủ hoặc mechanical work nơi durable context không thể đổi action;
- substantive work có khả năng tạo/xác nhận reusable conclusion phải review/write;
- trivial/mechanical/report-only work được skip write;
- required review không có durable candidate mới dùng `entries=[]`;
- trước create/update phải search existing concept để dedupe và ưu tiên update.

Khi read, caller sinh nhiều search terms. MCP rank deterministic từ generated
`INDEX.md`; không dùng embeddings/vector DB/translator/LLM.

Agent không tạo knowledge file trực tiếp. Create submit semantic fields, MCP derive:

```text
id   = <scope-kind>:<scope-id>:<canonical-name>
path = canonical namespace path
```

Update bắt buộc exact `id` + `expected_revision` từ read. Human edit ngoài MCP làm
revision/index stale và stale write/read bị reject cho tới khi reindex.

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

Retrieval không phụ thuộc ngôn ngữ của body.

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

Knowledge MCP được cài user/global scope để QiQi và Herdr-launched child agents ở
các repository khác nhau cùng thấy service:

```bash
cd knowledge-template
bash scripts/install-user-mcp.sh --store-root /path/to/shared-knowledge/store
```

Installer tạo stable wrapper và đăng ký MCP tên `knowledge` với Codex global config
và Claude user scope khi CLI tương ứng có sẵn. Existing registration cùng tên không
bị ghi đè.

Mở fresh agent session sau installation rồi smoke-test `knowledge_read`.

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

Project-scoped `.codex/config.toml` của workspace chỉ đăng ký `qiqi_delegate`.
Knowledge MCP không được duplicate vào workspace project config.

Sau static/unit checker, phải chạy fresh-session acceptance smoke trên **installed
Claude/Codex CLI thực tế** cho adapter đang dùng. Unit test không thay thế smoke này
vì native Stop-hook payload/CLI flags là external contract.

## Cài repo template

```bash
rsync -av --ignore-existing repo-template/ /path/to/multi-repo/<repo>/
cd /path/to/multi-repo/<repo>
bash scripts/repo-check.sh
```

Repo agent hiểu concern rồi áp dụng Knowledge MCP decision rule nhưng vẫn không được
đọc sibling source/result/runtime state.

## Migrate workspace đã tồn tại

Từ checkout của `agent-knowledge-harness`:

```bash
bash scripts/migrate-workspace.sh --dry-run /path/to/multi-repo
bash scripts/migrate-workspace.sh /path/to/multi-repo
bash scripts/migrate-workspace.sh --status /path/to/multi-repo
```

Shell script chỉ là stable launcher; migration core nằm trong
`scripts/migrate_workspace.py`. Script đọc `repos.yaml`, migrate workspace và từng
exact Git root con. Thêm `--verify` để chạy workspace/repo checker trước khi ghi
migration state.

Migration definitions là JSON dưới `migrations/`, pin exact `from_ref` / `to_ref`
và khai báo strategy riêng cho từng file:

- `replace`: template-owned policy/docs/checker/runtime; local divergence được backup
  trước khi replace;
- `merge`: dùng cho instruction có local customization cần giữ bằng 3-way merge;
- `delete`: legacy template path; diverged content được archive trước khi xóa;
- `manual_review`: live/customized artifact không overwrite tự động.

Migration `0004` chuyển execution handoff từ opaque prompt + Markdown result sang
TaskPacket + native Stop-hook response + SQLite session ownership. Với repo
`AGENTS.md`, migration dùng 3-way merge để không mặc nhiên xóa instruction đặc thù
của product repository.

Preflight chạy cho workspace + toàn bộ repo của cùng migration version trước khi ghi
managed file nào. State được lưu tập trung tại:

```text
<workspace>/.qiqi/agent-knowledge-harness-migrations.tsv
```

State giữ version riêng cho workspace và từng `repo:<relative-path>`, nên repository
được thêm vào `repos.yaml` sau này vẫn bắt đầu migrate từ version 0.

## Thiết kế cố ý

- Knowledge Store không phụ thuộc current workspace/repo.
- Agent submit knowledge; Knowledge MCP materialize file.
- Knowledge identity không phải filesystem path.
- Human Markdown edit là first-class workflow.
- Knowledge usage là conditional theo task semantics, không phải per-turn ritual.
- qiqi_delegate dùng SQLite cho execution session ownership; Knowledge MCP vẫn giữ
  Markdown store riêng, không trộn hai lifecycle.
- qiqi_delegate không dùng terminal viewport hoặc undocumented transcript schema để
  vận chuyển semantic result.
- QiQi broker live evidence; Knowledge MCP broker reusable knowledge.
