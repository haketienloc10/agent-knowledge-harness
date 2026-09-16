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

Filesystem không dùng raw ID. Directory key thay colon separator đầu tiên bằng `~`:

```text
redmine:116655 -> work-items/redmine~116655/
```

`~` giải quyết collision cú pháp do separator. Để portable qua filesystem case-insensitive, toàn `work-items/` còn phải **casefold-unique**: hai canonical IDs không được tạo directory keys khác spelling nhưng có cùng `casefold()`. Dossier tồn tại chỉ được reuse nếu `WORK_ITEM.md` có exact front-matter `id` khớp canonical ID. Resolved directory phải nằm dưới resolved `<workspace>/work-items`; reject traversal/separator/non-canonical IDs.

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

Trước khi gỡ legacy `work_item` MCP registration, export dữ liệu cũ:

```bash
python3 scripts/export-legacy-work-items.py --workspace /absolute/path/to/workspace
```

Exporter đọc mặc định `~/.local/share/agent-work-items/work-items.sqlite3` hoặc `WORK_ITEM_DB_PATH`. Nếu legacy installer dùng `--db-path`, truyền **đúng path đó** bằng `--db /absolute/path/to/work-items.sqlite3`; exporter fail nếu selected DB không tồn tại.

Exporter lấy Work Item + artifact/section/chunk trong một SQLite read snapshot, preflight toàn bộ output, reject casefold-equivalent directory keys, materialize latest lifecycle artifact theo legacy ordering và lưu full legacy JSON/artifact metadata dưới:

```text
<workspace>/.qiqi/migration-backups/v0024/legacy-work-items/
```

Backup directory/file dùng permission hạn chế (`0700`/`0600`). Source SQLite không bị sửa/xóa. Imported dossier giữ current handoff/repo verification/next-action ownership; investigation/plan/review giữ `based_on_work_item_revision`; report giữ Textile section shape. Partial artifact schema, target conflict hoặc cross-platform key alias đều fail trước filesystem write.

Legacy canonical records có thể chứa provenance/evidence extension fields và không có Acceptance Criteria section tương đương protocol mới. Vì vậy imported dossier có `legacy_reconciliation_required: true` và protected archive locator. QiQi phải reconcile material legacy metadata/acceptance/provenance trước substantive implementation/completion/report, rewrite current state + increment revision rồi bỏ flag.

Trong lúc export, không chạy thêm legacy Work Item mutation. Sau export thành công và kiểm tra dossiers cần thiết, remove registration cũ bằng helper verified:

```bash
bash scripts/remove-legacy-user-mcp.sh
```

Helper chỉ remove `work_item` nếu registration hiện tại còn trỏ tới legacy managed wrapper; nó từ chối xóa registration cùng tên nhưng không thuộc harness cũ. Sau đó install/update skill và mở fresh sessions:

```bash
bash scripts/install-user-skill.sh
```

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

## Verification

```bash
bash scripts/work-item-template-check.sh
```

Operational protocol nằm tại `skills/work-item/SKILL.md`.
