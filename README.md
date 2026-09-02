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
          search → exact scoped read → whole/partial mutation
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
- `work-item-template/`: user-scoped Global Work Item MCP + shared `$work-item` operational skill.
- `knowledge-template/`: user-scoped progressive Shared Knowledge MCP + store.
- `migrations/`: upgrade definitions cho workspace/repo đã cài harness.

## Global Work Item MCP

MVP tools:

```text
work_item_get(id)
work_item_history_read(id, collection, status?, repository?, cursor?, limit?)
work_item_list(status?, repository?, limit?)
work_item_create(...)
work_item_update(id, expected_revision, mutation)
```

Canonical Work Item vẫn giữ đầy đủ:

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

Agent-facing read/write đều progressive:

```text
work_item_get
  → bounded current-state projection

work_item_history_read
  → exact one-collection history/provenance on demand

work_item_update
  → bounded current-state patch + typed incremental semantic operations
```

`work_item_get` trả current requirements/repos, open questions/blockers, active decisions,
pending handoffs, next actions, history counts và thin artifact metadata. Resolved/
superseded/checkpoint history không hydrate mặc định. Khi thật sự cần provenance, caller
đọc đúng một canonical collection qua `work_item_history_read` với opaque cursor bind vào
Work Item id + exact whole revision + collection + filters. Revision đổi giữa page thì
restart; không mix history từ hai revisions.

`work_item_update` không expose historical full-array replacement. Current state nằm trong
`mutation.state`; questions/decisions/changes/blockers/handoffs/checkpoints đổi qua typed
operations (`question_upsert`, `decision_upsert`, `change_upsert`, `blocker_upsert`,
`handoff_upsert`, `checkpoint_append`). Up to 50 operations commit all-or-nothing dưới
một exact whole Work Item revision và success chỉ trả compact receipt. Stable-id lifecycle
advance monotonic; existing identity/provenance không bị silent rewrite.

Mục tiêu là giữ continuity cho task product xuyên investigation, planning, implementation,
UT, IT, UAT, bug fixing và Q&A mà không bắt user/QiQi kể lại history hoặc đưa accumulated
history vào model context/request/response ở mỗi turn.

`phase` không phải hard workflow engine. Requirement/customer decision evolution được
persist cùng task; decision cũ bị thay được supersede thay vì silent rewrite. Canonical
question/decision lifecycle status là explicit; legacy record thiếu/null status được
migrate một lần thành `open`/`active` thay vì giữ implicit runtime semantics.

### Shared `$work-item` skill

Read/create/revision/reconciliation/artifact mechanics được giữ trong một user-scoped
`$work-item` skill dùng chung cho QiQi và repo execution agents. Workspace/repo
`AGENTS.md` chỉ giữ always-on activation, authority và safety boundaries.

Generic ticket/task không tự động trở thành Work Item. `$work-item` được apply khi
canonical Work Item đã được identify/selected, user explicitly yêu cầu tạo/dùng Work
Item, hoặc trước `work_item_*` tool call.

Workspace-local `$ticket-work-item` entrypoint đã được bỏ; user có thể paste task và
explicitly yêu cầu QiQi tạo Work Item từ nội dung đó.

## Shared Knowledge MCP

Current public API:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_read_metadata(ids)
knowledge_read_section(id, section_id)
knowledge_write(entries)
knowledge_update(id, expected_revision, changes)
```

Progressive disclosure:

```text
search thin decision cards
→ chọn exact target
→ exact-read smallest sufficient scope:
     full document | metadata/provenance | one marked section
→ whole/partial mutation khi cần
```

Search card không phải full evidence và không chứa revision. Existing update target lấy exact whole-document revision từ một exact read surface, không bắt buộc hydrate full content nếu metadata hoặc một marked section đã đủ.

Knowledge storage vẫn giữ invariant **one semantic concept = one canonical Markdown document = one SHA-256 revision**. `knowledge_update` chỉ là mutation convenience: server reconstruct full canonical payload rồi reuse existing whole-document locking/write/index/revision path. Stable section markers không tạo chunk store hay per-section revision.

## Structured input, native output

`qiqi_delegate` nhận structured TaskPacket và trả exact native final assistant response qua Stop hook. Không dùng fixed Markdown result schema, terminal viewport hoặc transcript parser làm semantic transport.

Khi delegation thuộc Work Item, QiQi truyền canonical Work Item ID + revision trong `required_context`; child apply `$work-item` và lấy bounded current state mới nhất từ Work Item MCP, rồi chỉ đọc scoped history khi decision/reconciliation thực sự cần. External fact ngoài Work Item mà QiQi đã dùng cho semantics vẫn phải inline với provenance/certainty.

## Cài Global Work Item MCP

```bash
cd work-item-template
bash scripts/work-item-template-check.sh
bash scripts/install-user-mcp.sh
```

`install-user-mcp.sh` cài/refresh cả MCP/CLI và managed user-scope `$work-item` skill cho
Codex + Claude.

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

Knowledge installer luôn `init` rồi chạy canonical `knowledge check` trên toàn existing store **trước** khi cài skill, tạo wrapper hoặc đổi Codex/Claude MCP registration. Nếu preflight fail, installer dừng để operator sửa canonical document trước; đặc biệt phải fence/escape illustrative text bắt đầu bằng reserved prefix `<!-- knowledge-section:` hoặc chuyển nó thành valid semantic marker + H2–H6 heading. Nếu document đã hợp lệ nhưng index stale, reindex store rồi rerun installer.

Mở fresh agent session chỉ sau khi preflight + user-scope MCP/skill registration hoàn tất. Sau public Knowledge tool change, rerun installer từ checkout mới để fresh session discover đủ 6 tools.

## Workspace mới

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
cd /path/to/multi-repo
herdr integration install codex
herdr integration install claude
uv sync --project mcp/qiqi_delegate
bash scripts/workspace-check.sh
```

Project `.codex/config.toml` chỉ đăng ký `qiqi_delegate`; `work_item`, `$work-item` và `knowledge` là user-scope capabilities.

## Workspace đã cài harness

Không rsync đè template. Dùng migration từ checkout harness:

```bash
bash scripts/migrate-workspace.sh --dry-run /path/to/workspace
bash scripts/migrate-workspace.sh /path/to/workspace
bash scripts/migrate-workspace.sh --status /path/to/workspace
bash scripts/migrate-workspace.sh --verify /path/to/workspace
```

Work Item migrations update workspace/repo policy nhưng không tự ghi user MCP/skill
config. Sau migration Work Item public-contract mới, rerun:

```bash
cd work-item-template
bash scripts/install-user-mcp.sh
```

rồi mở fresh QiQi/child session để load `$work-item` và discover bounded read + incremental
mutation schema mới.

Knowledge public-tool migration cũng chỉ update workspace/repo policy. Operator phải rerun `knowledge-template/scripts/install-user-mcp.sh` với existing `--store-root`; installer preflight toàn store và abort trước user-facing registration nếu legacy content vi phạm reserved-marker/current integrity contract. Chỉ mở fresh sessions sau khi preflight pass.

## Acceptance smoke

Sau migration/cài đặt, mở fresh QiQi + fresh child session và xác nhận:

1. QiQi/child thấy `$work-item`; QiQi thấy `work_item_*` gồm `work_item_history_read` và đủ 6 Knowledge tools.
2. QiQi create/get một test Work Item theo explicit Work Item intent; GET không trả accumulated checkpoint/resolved history.
3. Scoped history read page đúng collection/filter và cursor cũ conflict nếu Work Item revision đổi giữa pages.
4. Append checkpoint bằng `checkpoint_append` không resend historical checkpoints; response là compact receipt.
5. Resolve question bằng partial `question_upsert`; historical full-array replacement không có trong public schema.
6. Stale writer dù sửa semantic record khác vẫn bị whole-revision conflict.
7. Child đọc cùng bounded Work Item qua `$work-item`, chỉ update current-repo evidence.
8. Generic ticket/task không tự động tạo Work Item.
9. Knowledge search trả thin cards; metadata/section/full exact reads trả đúng scope + whole-document revision.
10. `knowledge_update` preserve untouched canonical state và stale Knowledge revision bị reject.
11. qiqi_delegate native result/RESUME smoke pass cho agent family thực sự dùng.

## Thiết kế cố ý

- Work Item MCP là task truth duy nhất; không repo-local/workspace-local task copy.
- Work Item read surface progressive: bounded current state mặc định, exact scoped history on demand.
- Work Item write surface progressive: bounded state patch + typed semantic commands; không full-array historical rewrite.
- Storage vẫn một canonical `document_json` + một whole Work Item revision; không event sourcing/per-record revision.
- `$work-item` là operational protocol, không phải task store hay implicit ticket opt-in.
- Knowledge MCP chỉ giữ reusable durable truth, không task-specific mutable state.
- Knowledge partial update không đổi one-document/one-revision storage model.
- Repo source/test là implementation truth.
- qiqi_delegate SQLite chỉ giữ runtime/session truth.
- QiQi là orchestration/synchronization broker, không memory bus.
