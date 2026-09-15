# Filesystem Work Item

Work Item là **current task dossier** dùng chung trong một QiQi workspace. Nó không còn là MCP service, không dùng SQLite cho runtime mới và không phải lịch sử thao tác của agent.

Canonical parent-side location:

```text
<workspace>/work-items
```

Canonical ID giữ dạng `source:external-id`, ví dụ `redmine:116655`, và MUST match:

```text
^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$
```

Filesystem không dùng raw ID. Directory key được derive bằng cách thay colon separator đầu tiên bằng `--`:

```text
redmine:116655 -> work-items/redmine--116655/
```

Resolved task directory phải nằm dưới resolved `<workspace>/work-items`; reject traversal/separator/non-canonical IDs.

Mỗi tracked task có:

```text
work-items/<directory-key>/
├── WORK_ITEM.md
├── intake.md?
├── investigation.md?
├── plan.md?
├── review.md?
└── report.textile?
```

Không tạo mặc định `history/`, `turns/`, `executions/`, `checkpoints/` hay file theo turn. Dossier tăng theo độ phức tạp material của task, không theo số agent turn.

## Truth boundary

```text
WORK_ITEM.md          = current canonical task truth
lifecycle documents  = current material phase state / deliverable
Repo source/test     = implementation truth
Knowledge MCP        = reusable durable truth
.qiqi/state          = runtime/session truth
```

QiQi là canonical writer. Repository child đọc dossier đã được mount bằng `--add-dir`, nhưng locator được truyền bằng absolute `work_item_path=...` trong TaskPacket context; child không phụ thuộc vào việc inherit `QIQI_WORK_ITEMS_DIR` từ Herdr server.

## Current-state, không phải history

Persist chỉ thông tin mà nếu bỏ đi sẽ làm turn sau hiểu sai requirement/scope/acceptance, lặp investigation material, đi lại vào hướng implementation đã bị loại, đánh giá sai completion hoặc tạo sai report. Không persist command chronology, agent turn, intermediate attempts hoặc routine progress.

Requirement change rewrite effective current state. Investigation/plan/review là living documents và được merge/rewrite qua nhiều turn.

## Legacy SQLite cutover

Trước khi gỡ user-scoped legacy `work_item` MCP registration, export dữ liệu cũ:

```bash
python3 scripts/export-legacy-work-items.py --workspace /absolute/path/to/workspace
```

Exporter đọc mặc định `~/.local/share/agent-work-items/work-items.sqlite3` (hoặc `WORK_ITEM_DB_PATH`), tạo current filesystem dossiers, materialize latest lifecycle artifact của mỗi type, và lưu full legacy JSON + toàn bộ artifact content dưới:

```text
<workspace>/.qiqi/migration-backups/v0024/legacy-work-items/
```

Source SQLite DB không bị sửa/xóa. Nếu target dossier hoặc backup đã tồn tại, exporter fail thay vì overwrite. Chỉ remove legacy MCP registration sau khi export thành công và kiểm tra dossier cần thiết.

## Lifecycle

```text
request
→ intake/canonicalize
→ investigate (nếu cần)
→ plan/decide (nếu cần)
→ implement/delegate
→ verify/review
→ report
→ done
```

Flow được phép quay lại investigation/planning khi evidence hoặc requirement đổi; không encode FSM cứng.

## Skill + verification

```bash
bash scripts/install-user-skill.sh
bash scripts/work-item-template-check.sh
```

Operational protocol nằm tại `skills/work-item/SKILL.md`.
