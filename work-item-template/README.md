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

Helper chỉ remove `work_item` nếu registration hiện tại còn trỏ tới legacy managed wrapper; nó từ chối xóa registration cùng tên nhưng không thuộc harness cũ. Sau đó install/update skill bundle và mở fresh sessions:

```bash
bash scripts/install-user-skill.sh
```

Installer quản lý cùng lúc 5 user-scoped skills cho cả Codex và Claude:

```text
work-item
work-item-intake
work-item-investigate
work-item-plan
work-item-review
```

Codex được cài vào native user skill root `$CODEX_HOME/skills`; khi `CODEX_HOME` không set thì path mặc định là `~/.codex/skills`. Claude dùng `~/.claude/skills`. Harness release cũ từng cài Codex skill dưới `~/.agents/skills`; installer mới chỉ xóa các copy cũ có `.agent-knowledge-harness-managed` sau khi native install thành công. Same-name entry không có managed marker sẽ fail closed để tránh xóa hoặc để lại duplicate skill discovery ngoài ý muốn.

Installer preflight toàn bộ bundle trước mutation. Existing unmanaged same-name skill chỉ được adopt khi toàn bộ tree giống source; unrelated skill không bị overwrite.

## Phase clarification skills

`work-item` giữ lifecycle/orchestration và canonical write boundary. Bốn skill bổ trợ chỉ làm rõ uncertainty ở đúng phase:

- `work-item-intake` — mandatory semantic gate cho request mới/material requirement change: understanding, scope, terminology, acceptance và requirement ambiguity.
- `work-item-investigate` — conditional gate khi ownership, repo/module boundary, authoritative source hoặc first investigation target chưa rõ.
- `work-item-plan` — conditional decision gate khi approach/trade-off/risk/verification materially non-obvious.
- `work-item-review` — mandatory acceptance gate trước completion/reporting, dựa trên actual evidence.

Gate vocabulary chung:

```text
ready
needs_user_clarification
needs_discovery
blocked
```

`needs_discovery` = factual/technical/evidence work mà agent có thể tự làm mà chưa cần user quyết định. Nguyên tắc xuyên suốt: **clarify meaning, not mechanics** — hỏi user cho intent/product/domain semantics/material acceptance hoặc irreversible/external-contract trade-off; tự discover repository/module facts và tự quyết normal reversible implementation details khi evidence đủ.

Phase skills không tạo `clarification.md`, history hay file theo turn. Material result được QiQi reconcile vào `WORK_ITEM.md` và các lifecycle documents hiện có.

## Lifecycle

```text
request
→ intake/canonicalize + mandatory intake gate
→ investigate (nếu cần; clarification gate chỉ khi boundary/target chưa rõ)
→ plan/decide (nếu cần; decision gate chỉ khi materially non-obvious)
→ implement/delegate
→ verify/review + mandatory acceptance gate
→ report
→ done
```

Flow được phép quay lại intake/investigation/planning khi evidence hoặc requirement đổi; không encode FSM cứng.

## Verification

```bash
bash scripts/work-item-template-check.sh
```

Operational protocol nằm tại `skills/work-item/SKILL.md`; phase semantics nằm tại các sibling `skills/work-item-*` directories.
