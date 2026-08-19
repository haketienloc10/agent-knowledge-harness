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
              │ live handoff      │          │
              ▼                   │          │
        qiqi_delegate MCP ────────┴──────────┘
              │
              ▼
       independent Git repos
```

### `workspace-template/`

QiQi control plane tại workspace root:

- `repos.yaml` registry exact Git roots;
- `SYSTEM_MAP.md` live topology/ownership/dependency;
- model/runtime routing;
- synchronous `qiqi_delegate` START/RESUME;
- `.qiqi/runs/` terminal result handoff;
- dependency waves, evidence reuse và user reporting.

Workspace **không còn sở hữu durable knowledge store**.

### `repo-template/`

Policy tối thiểu cho execution agent tại mỗi Git root:

- architecture + verification routing;
- Git-root/sibling-repo boundaries;
- live upstream context từ QiQi;
- conditional Shared Knowledge MCP read/write lifecycle;
- Cross-repo Impact handoff về QiQi;
- result artifact finalization.

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

## Hai loại context

### Live execution evidence

Repo source/test/result hiện tại là live truth. Khi repo B phụ thuộc work vừa xảy ra
ở repo A:

```text
repo A result
→ QiQi đọc/reconcile
→ relevant fact/evidence trong repo B task prompt
```

Child không tự mở sibling source hoặc sibling result artifact.

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
  trivial/mechanical/report-only work được skip write;
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

## Cài repo template

```bash
rsync -av --ignore-existing repo-template/ /path/to/multi-repo/<repo>/
cd /path/to/multi-repo/<repo>
bash scripts/repo-check.sh
```

Repo agent hiểu concern rồi áp dụng Knowledge MCP decision rule nhưng vẫn không được
đọc sibling source/result.

## Migrate workspace đã tồn tại

Từ checkout của `agent-knowledge-harness`, public command vẫn là:

```bash
bash scripts/migrate-workspace.sh --dry-run /path/to/multi-repo
bash scripts/migrate-workspace.sh /path/to/multi-repo
bash scripts/migrate-workspace.sh --status /path/to/multi-repo
```

Shell script chỉ là stable launcher; migration core nằm trong
`scripts/migrate_workspace.py`. Script đọc `repos.yaml`, rồi migrate workspace và
từng exact Git root con. Thêm `--verify` để chạy `workspace-check.sh` và
`repo-check.sh` trước khi ghi migration state.

Migration definitions là JSON dưới `migrations/`, pin exact `from_ref` / `to_ref`
và khai báo strategy riêng cho từng file:

- `replace`: template-owned policy/docs/checker. Nếu local file đã diverge, script
  archive bản local vào `.qiqi/migration-backups/vNNNN/...` rồi replace bằng target
  template; không cần `--force` và không mất customization cũ;
- `merge`: dành cho future migration nhỏ nơi local customization cần được giữ bằng
  3-way merge; conflict overlap mới dừng preflight, `--force` mới cho phép backup +
  replace;
- `delete`: legacy template path. Nếu local content diverge, archive trước rồi xóa;
- `manual_review`: live/customized artifact; không overwrite tự động.

Migration v1 là architecture rewrite lớn nên toàn bộ template-owned `AGENTS.md`,
README/setup/checker/task guidance dùng `replace` có backup. Workspace `SYSTEM_MAP.md`,
`identity.md` và repo `ARCHITECTURE.md` vẫn là `manual_review` vì chứa live truth.

Preflight chạy cho workspace + toàn bộ repo của cùng migration version trước khi ghi
managed file nào. State được lưu tập trung tại:

```text
<workspace>/.qiqi/agent-knowledge-harness-migrations.tsv
```

State giữ version riêng cho workspace và từng `repo:<relative-path>`, nên repository
được thêm vào `repos.yaml` sau này vẫn bắt đầu migrate từ version 0.

## Result artifact

Current qiqi_delegate compatibility contract vẫn có headings:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

`Repo-local Knowledge` hiện là legacy label: repo agent ghi Knowledge MCP IDs đã
create/update, `None`, hoặc persistence failure. Không còn repo-local durable
knowledge lifecycle bắt buộc.

`Cross-repo Impact` là live execution-impact signal; durable persistence không thay
thế handoff nếu repo khác còn cần work.

## Thiết kế cố ý

- Knowledge Store không phụ thuộc current workspace/repo.
- Agent submit knowledge; MCP materialize file.
- Knowledge identity không phải filesystem path.
- Human Markdown edit là first-class workflow.
- Knowledge usage là conditional theo task semantics, không phải per-turn ritual.
- No hidden database; no vector store trong MVP.
- qiqi_delegate và Knowledge MCP là hai lifecycle độc lập.
- QiQi broker live evidence; Knowledge MCP broker reusable knowledge.
