# Filesystem Work Item

Work Item là **current task dossier** dùng chung trong một QiQi workspace. Nó không còn là MCP service, không dùng SQLite và không phải lịch sử thao tác của agent.

Canonical parent-side location trong workspace:

```text
<workspace>/work-items
```

QiQi/$work-item resolve workspace root trực tiếp; không phụ thuộc vào env do MCP child export. Khi delegate repo-local work, qiqi_delegate expose cùng directory cho child qua delegated-runtime alias `QIQI_WORK_ITEMS_DIR` và native `--add-dir`.

Mỗi tracked task có một directory:

```text
work-items/<id>/
├── WORK_ITEM.md
├── intake.md            # material request context, khi cần
├── investigation.md     # living investigation state, khi cần
├── plan.md              # current agreed approach, khi cần
├── review.md            # current acceptance assessment, khi cần
└── report.textile       # final external deliverable, khi workflow cần
```

Không tạo mặc định `history/`, `turns/`, `executions/`, `checkpoints/` hay file theo turn. Số file và kích thước dossier phải tăng theo **độ phức tạp material của task**, không tăng theo số lần agent chạy.

## Truth boundary

```text
WORK_ITEM.md          = current canonical task truth
lifecycle documents  = current material phase state / deliverable
Repo source/test     = implementation truth
Knowledge MCP        = reusable durable truth
.qiqi/state          = runtime/session truth
```

QiQi là canonical writer của `WORK_ITEM.md` và lifecycle documents. Repository child được đọc Work Item được mount qua `--add-dir`, nhưng trả evidence/conclusion bằng native response để QiQi reconcile; child không tự mark global task done.

## Current-state, không phải history

Persist chỉ thông tin mà nếu bỏ đi sẽ làm turn sau:

- hiểu sai requirement/scope/acceptance;
- lặp lại investigation material;
- đi lại vào hướng implementation đã bị loại vì lý do còn hiệu lực;
- đánh giá sai verification/completion;
- tạo sai final report.

Không persist command chronology, agent turn, intermediate attempts, routine progress hoặc redundant summaries.

Requirement change rewrite `WORK_ITEM.md` thành effective requirement hiện tại. `intake.md` chỉ giữ initial request và **material requirement-change context** còn cần để giải thích/không hiểu sai current state; không ghi request timeline.

Investigation/plan/review là living documents: nhiều turn phải merge/rewrite current semantic state, không append turn log.

## Revision

`WORK_ITEM.md` giữ integer `revision`. QiQi tăng revision khi canonical task meaning thay đổi material. Delegation tracked task ghi locator + revision trong TaskPacket context. Khi child trả kết quả dựa trên revision cũ, QiQi reconcile từng finding với current requirement trước khi promote.

Revision ở đây dùng stale detection; không phải database CAS và không tạo history store.

## Lifecycle

Thông thường:

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

Flow được phép quay lại investigation/planning khi evidence hoặc requirement đổi. Không encode FSM cứng.

## Skill

Operational protocol nằm tại:

```text
skills/work-item/SKILL.md
```

Cài skill user-scope:

```bash
bash scripts/install-user-skill.sh
```

Kiểm tra template:

```bash
bash scripts/work-item-template-check.sh
```
