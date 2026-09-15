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

Canonical ID match `^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$`. Filesystem key replace colon separator đầu tiên bằng `~`, ví dụ `redmine:116655 -> redmine~116655`. Vì `~` không thuộc grammar của source/external-id, mapping không collision giữa canonical IDs hợp lệ. `$work-item` phải reject invalid/traversal ID và verify resolved dossier vẫn nằm dưới Work Items root.

## Legacy SQLite cutover

Nếu máy đã có legacy Work Item DB, **export trước khi gỡ user-scoped `work_item` MCP registration**:

```bash
cd agent-knowledge-harness/work-item-template
python3 scripts/export-legacy-work-items.py --workspace /absolute/path/to/workspace
```

Default source là `~/.local/share/agent-work-items/work-items.sqlite3` hoặc `WORK_ITEM_DB_PATH`. Legacy installer từng hỗ trợ `--db-path`; nếu đã dùng option đó, phải truyền exact DB bằng `--db /absolute/path/to/work-items.sqlite3`. Missing selected DB là lỗi, không được coi như export rỗng thành công.

Exporter đọc toàn bộ Work Item + artifact/section/chunk trong một SQLite read snapshot và preflight toàn bộ output trước filesystem write. Current dossier giữ current-state semantics như pending handoff và repository verification; lifecycle docs giữ revision provenance/Textile shape; full raw backup giữ chunk metadata tại `<workspace>/.qiqi/migration-backups/v0024/legacy-work-items/` với permission hạn chế. Source SQLite không bị sửa/xóa và partial artifact schema fail closed.

Không chạy thêm legacy Work Item mutation trong lúc export. Nếu exporter báo conflict/schema error, reconcile trước; chỉ disable/remove legacy registration sau khi export thành công và kiểm tra dossier cần thiết.

## Work Item lifecycle

Cài/update `$work-item` skill từ harness:

```bash
cd work-item-template
bash scripts/install-user-skill.sh
```

Installer chỉ adopt một existing unmanaged `work-item` skill khi **toàn bộ skill tree** (SKILL.md + templates) giống source; matching `SKILL.md` đơn lẻ không đủ.

`WORK_ITEM.md` là current canonical state; lifecycle docs là living semantic state, không append-only history. Requirement change rewrite effective requirements, increment revision và reconcile prior investigation/plan/review theo materiality.

## Repo delegation

TaskPacket vẫn chứa objective/scope/acceptance đầy đủ. Child được đọc exact mounted dossier từ `work_item_path`, nhưng không mutate canonical dossier.

`instructions/model-routing.md` không phải mandatory startup material. Default delegation route là `claude-balanced`; khi một turn thực sự delegate, QiQi đọc route policy just-in-time ngay trước route decision.

## Verification

```bash
bash scripts/workspace-check.sh
```