# Workspace setup

## Layout

```text
<workspace>/
├── AGENTS.md
├── identity.md
├── repos.yaml
├── SYSTEM_MAP.md
├── work-items/
├── instructions/
├── mcp/qiqi_delegate/
└── scripts/
```

`work-items/` là workspace-level current task resource. Runtime mới không cài Global Work Item MCP và không tạo SQLite Work Item DB.

## Runtime

Parent QiQi/$work-item resolve canonical task resource trực tiếp tại `<workspace>/work-items`; parent không dựa vào environment variable được một MCP child process export.

`scripts/qiqi-mcp-server.sh` resolve workspace root, `mkdir -p work-items`, export `QIQI_WORK_ITEMS_DIR=<workspace>/work-items` cho qiqi_delegate và start MCP. qiqi_delegate dùng alias này để inject native `--add-dir` cho Codex/Claude.

Child **không phụ thuộc vào env inheritance từ Herdr server**. Với tracked task, TaskPacket truyền absolute dossier locator:

```text
work_item_path=<absolute-workspace-path>/work-items/<directory-key>; id=<canonical-id>; revision=<n>
```

## Work Item ID/path

Canonical ID match `^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$`. Filesystem key replace colon separator đầu tiên bằng `~`, ví dụ `redmine:116655 -> redmine~116655`.

`~` loại bỏ collision do separator, nhưng canonical external-id phân biệt hoa/thường trong khi filesystem macOS/Windows thường không. Vì vậy Work Items root dùng contract **casefold-unique**: không được có hai directory key khác spelling nhưng cùng `casefold()`. Trước create/read/write `$work-item` phải reject sibling casefold-equivalent; nếu dossier đã tồn tại thì front-matter `WORK_ITEM.md.id` phải khớp exact canonical ID. Đồng thời reject invalid/traversal ID và verify resolved dossier vẫn nằm dưới Work Items root.

## Legacy SQLite cutover

Nếu máy đã có legacy Work Item DB, **export trước khi gỡ user-scoped/global `work_item` MCP registration**:

```bash
cd agent-knowledge-harness/work-item-template
python3 scripts/export-legacy-work-items.py --workspace /absolute/path/to/workspace
```

Default source là `~/.local/share/agent-work-items/work-items.sqlite3` hoặc `WORK_ITEM_DB_PATH`. Legacy installer từng hỗ trợ `--db-path`; nếu đã dùng option đó, phải truyền exact DB bằng `--db /absolute/path/to/work-items.sqlite3`. Missing selected DB là lỗi, không được coi như export rỗng thành công.

Exporter đọc toàn bộ Work Item + artifact/section/chunk trong một SQLite read snapshot và preflight toàn bộ output trước filesystem write. Current dossier giữ current-state semantics như pending handoff và repository verification; lifecycle docs giữ revision provenance/Textile shape; full raw backup giữ chunk metadata tại `<workspace>/.qiqi/migration-backups/v0024/legacy-work-items/` với permission hạn chế. Source SQLite không bị sửa/xóa và partial artifact schema fail closed. Export cũng reject canonical IDs có directory keys casefold-equivalent để kết quả portable qua case-sensitive lẫn case-insensitive filesystems.

Legacy model cho phép một số decision provenance/evidence extension fields và không có Acceptance Criteria section tương đương protocol mới. Vì vậy imported `WORK_ITEM.md` có `legacy_reconciliation_required: true` và trỏ tới protected archive. Trước substantive continuation/completion/report, QiQi phải reconcile material legacy acceptance/provenance từ archive vào living state, increment revision rồi bỏ flag; archive không trở thành runtime history source sau reconciliation.

Không chạy thêm legacy Work Item mutation trong lúc export. Nếu exporter báo conflict/schema error, reconcile trước. Sau export thành công, kiểm tra dossiers cần thiết rồi **gỡ registration cũ một cách verified**:

```bash
cd agent-knowledge-harness/work-item-template
bash scripts/remove-legacy-user-mcp.sh
```

Helper chỉ remove registration `work_item` khi current definition còn trỏ tới managed legacy `agent-work-item-mcp`/`work-item-mcp-server.sh`; nếu cùng tên nhưng là registration khác, script fail thay vì xóa. Với CLI không cài trên máy, script cảnh báo để user kiểm tra client đó riêng. Sau cleanup, mở fresh agent sessions để stale MCP discovery không còn tồn tại.

## Work Item lifecycle

Cài/update `$work-item` skill từ harness:

```bash
cd work-item-template
bash scripts/install-user-skill.sh
```

Installer chỉ adopt một existing unmanaged `work-item` skill khi **toàn bộ skill tree** (SKILL.md + templates) giống source; matching `SKILL.md` đơn lẻ không đủ.

`WORK_ITEM.md` là current canonical state; lifecycle docs là living semantic state, không append-only history. Requirement change rewrite effective requirements, increment revision và reconcile prior investigation/plan/review theo materiality.

## Herdr + qiqi_delegate readiness

Fresh workspace phải cài integrations cho các native adapters trước delegation:

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
uv sync --project mcp/qiqi_delegate
```

`herdr integration status` phải báo `codex: current` và `claude: current` (hoặc mọi adapter được cấu hình trong `instructions/agent-routing.yaml`). `delegate_repo_task` cũng fail closed nếu integration không current, nên đây là setup prerequisite chứ không chỉ troubleshooting step.

## Repo delegation

TaskPacket vẫn chứa objective/scope/acceptance đầy đủ. Child được đọc exact mounted dossier từ `work_item_path`, nhưng không mutate canonical dossier.

`instructions/model-routing.md` không phải mandatory startup material. Default delegation route là `claude-balanced`; khi một turn thực sự delegate, QiQi đọc route policy just-in-time ngay trước route decision.

## Verification

Sau khi `repos.yaml` đã được materialize thành repository thực và Herdr integrations đã cài:

```bash
bash scripts/workspace-check.sh
```

Checker verify repository registry shape, `required_for`/`depends_on`, duplicate/unknown/self dependencies, dependency cycles, relative paths, exact Git roots, duplicate roots, qiqi_delegate tests và Herdr integration readiness. Harness CI dùng `QIQI_TEMPLATE_CHECK=1` chỉ để validate unmaterialized template placeholders mà không giả vờ kiểm machine-local Git roots/Herdr state.
