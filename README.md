# Agent Knowledge Harness

Bộ khung vận hành QiQi trong multi-repository workspace với bốn nguồn truth độc lập:

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

## Kiến trúc

```text
                         Shared Knowledge Store
                                ▲
                                │
                         Knowledge MCP
                   search → exact read → write
                                ▲
                                │ reusable truth
                                │
User → QiQi workspace ──────────┼───────────────┐
          │                     │               │
          │                     ▼               │
          │            Global Work Item MCP     │
          │              SQLite user-scope      │
          │                     ▲               │
          │                     │ task truth    │
          ▼                     │               │
    qiqi_delegate MCP ──────────┴───────────────┘
          │                                     ▲
          │ Herdr START / RESUME                │ native final response
          ▼                                     │
    independent Git repos ──────────────────────┘
             repo source/test truth
```

QiQi và repo execution agents cùng đọc một canonical Work Item. Child chỉ làm phần thuộc current Git root; cross-repo remaining work/handoff quay lại QiQi để điều phối repo khác.

## Thành phần

- `workspace-template/`: QiQi orchestration/control plane.
- `repo-template/`: execution-agent policy cho từng Git root.
- `work-item-template/`: user-scoped Global Work Item MCP.
- `knowledge-template/`: user-scoped progressive Shared Knowledge MCP + store.
- `migrations/`: upgrade definitions cho workspace/repo đã cài harness.

## Global Work Item MCP

MVP tools:

```text
work_item_get(id)
work_item_list(status?, repository?, limit?)
work_item_create(...)
work_item_update(id, expected_revision, changes)
```

Work Item giữ:

```text
status / phase / summary
current_requirements
questions
decisions
changes
repos
blockers
handoffs
next_actions
checkpoints
revision
```

Mục tiêu là giữ continuity cho task product xuyên investigation, planning, implementation, UT, IT, UAT, bug fixing và Q&A mà không bắt user/QiQi kể lại history.

`phase` không phải hard workflow engine. Requirement/customer decision evolution được persist cùng task; decision cũ bị thay được supersede thay vì silent rewrite.

## Shared Knowledge MCP

Current public API:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_write(entries)
```

Progressive disclosure:

```text
search thin decision cards
→ chọn 1–2 exact IDs
→ full read semantic content + sources + revision
→ write khi cần
```

Search card không phải full evidence và không chứa revision. Existing update target phải full-read trước.

## Structured input, native output

`qiqi_delegate` nhận structured TaskPacket và trả exact native final assistant response qua Stop hook. Không dùng fixed Markdown result schema, terminal viewport hoặc transcript parser làm semantic transport.

Khi delegation thuộc Work Item, QiQi truyền canonical Work Item ID + revision trong `required_context`; child gọi `work_item_get` để lấy state mới nhất. External fact ngoài Work Item mà QiQi đã dùng cho semantics vẫn phải inline với provenance/certainty.

## Cài Global Work Item MCP

```bash
cd work-item-template
bash scripts/work-item-template-check.sh
bash scripts/install-user-mcp.sh
```

Default DB:

```text
~/.local/share/agent-work-items/work-items.sqlite3
```

Có thể override bằng `--db-path`.

## Cài/kiểm tra Knowledge MCP

```bash
cd knowledge-template
bash scripts/knowledge-template-check.sh
bash scripts/install-user-mcp.sh --store-root /path/to/shared-knowledge/store
```

Mở fresh agent session sau user-scope MCP registration.

## Workspace mới

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
cd /path/to/multi-repo
herdr integration install codex
herdr integration install claude
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Project `.codex/config.toml` chỉ đăng ký `qiqi_delegate`; `work_item` và `knowledge` là user-scope services.

## Workspace đã cài harness

Không rsync đè template. Dùng migration từ checkout harness:

```bash
bash scripts/migrate-workspace.sh --dry-run /path/to/workspace
bash scripts/migrate-workspace.sh /path/to/workspace
bash scripts/migrate-workspace.sh --status /path/to/workspace
bash scripts/migrate-workspace.sh --verify /path/to/workspace
```

Work Item migration nằm sau migration `0005-knowledge-progressive-disclosure`; nó update workspace/repo policy, remove template-owned workspace task skeleton và không tự ghi user MCP config.

## Acceptance smoke

Sau migration/cài đặt, mở fresh QiQi + fresh child session và xác nhận:

1. QiQi thấy `work_item_*` và Knowledge search/read/write tools.
2. QiQi create/get một test Work Item.
3. Child đọc cùng Work Item, chỉ update current-repo evidence.
4. QiQi reread thấy revision/state mới.
5. Stale Work Item revision bị reject.
6. Knowledge search trả thin cards, exact read trả full content/revision.
7. qiqi_delegate native result/RESUME smoke pass cho agent family thực sự dùng.

## Thiết kế cố ý

- Work Item MCP là task truth duy nhất; không repo-local/workspace-local task copy.
- Knowledge MCP chỉ giữ reusable durable truth, không task-specific mutable state.
- Repo source/test là implementation truth.
- qiqi_delegate SQLite chỉ giữ runtime/session truth.
- QiQi là orchestration/synchronization broker, không memory bus.
