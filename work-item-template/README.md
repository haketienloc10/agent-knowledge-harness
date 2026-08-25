# Global Work Item MCP

Global Work Item MCP là source of truth duy nhất cho **mutable product-task state**
được dùng chung bởi QiQi và execution agents trong các repository con.

Nó không thay thế:

```text
Global Work Item MCP   = task truth
Knowledge MCP          = reusable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

## Mục tiêu MVP

Giải quyết continuity cho task kéo dài qua investigation, planning, implementation,
unit test, IT, UAT, fix bug và Q&A mà không yêu cầu người dùng hoặc QiQi kể lại toàn
bộ lịch sử sau mỗi session.

MVP cố ý **không** là project-management product. Không có workflow DSL, event
sourcing, RBAC, notification, UI, Redmine sync hoặc automatic phase transition.
QiQi vẫn quyết định workflow và orchestration.

## Canonical identity

Mỗi product task có một ID ổn định:

```text
redmine:116655
redmine:151921
```

Format là `<source>:<external-id>`.

## Work Item document

Một Work Item lưu snapshot hiện tại và material history cần để tiếp tục công việc:

```yaml
id: redmine:116655
status: active
phase: implementation
summary: Backend đang cập nhật theo requirement mới.

current_requirements:
  - Order detail trả paymentStatus.
  - Order list cũng trả paymentStatus.

questions:
  - id: q1
    status: resolved
    question: paymentStatus unknown có trả field không?
    answer: Có, trả null.
    decision_id: d1

# Decision giữ lý do task hiện tại được hiểu/triển khai như vậy.
decisions:
  - id: d1
    status: active
    summary: paymentStatus luôn xuất hiện; unknown trả null.
    decided_by: customer

# Change ghi requirement/scope evolution, không ghi transcript.
changes:
  - id: c1
    type: requirement_added
    status: accepted
    summary: Thêm paymentStatus vào order list API.

repos:
  backend-api:
    status: done
    summary: Implementation hoàn tất.
    verification:
      - Unit tests passed
  frontend-web:
    status: pending
    summary: ""
    verification: []

blockers: []

handoffs:
  - id: h1
    from: backend-api
    to: frontend-web
    status: pending
    summary: Consume paymentStatus.
    evidence:
      - commit abc123

next_actions:
  - repo: frontend-web
    action: Consume paymentStatus và chạy UT.

checkpoints:
  - repo: backend-api
    summary: Backend implementation + UT hoàn tất.
```

`phase` là descriptive state, không phải finite-state-machine. Task có thể quay từ
UAT về implementation/fix rồi trở lại IT/UAT mà MCP không chặn transition.

`status` MVP có: `active`, `waiting`, `blocked`, `done`, `cancelled`.

Repo status có: `pending`, `active`, `waiting`, `blocked`, `done`, `not_required`.

Requirement change type MVP có: `requirement_added`, `requirement_changed`,
`requirement_removed`, `scope_changed`.

## Snapshot và history

Các field có hai vai trò khác nhau:

```text
summary/current_requirements/status/phase/repos/blockers/next_actions
= snapshot hiện tại để tiếp tục công việc ngay

questions/decisions/changes/checkpoints
= material history giải thích vì sao snapshot hiện tại hình thành
```

Không persist terminal transcript, command-by-command activity hoặc agent reasoning.

## API MVP

```text
work_item_get(id)
work_item_list(status?, repository?, limit?)
work_item_create(id, title, summary?, status?, phase?, current_requirements?, repositories?)
work_item_update(id, expected_revision, changes)
```

`work_item_update` dùng JSON merge-patch semantics:

- nested object merge;
- array replace nguyên tử;
- `null` remove field;
- required field bị remove sẽ fail validation.

Arrays replace nguyên tử là intentional cho MVP: caller phải đọc Work Item hiện tại,
reconcile full intended array, rồi update bằng exact revision.

## Optimistic concurrency

Mọi Work Item có `revision` do MCP sở hữu.

```text
QiQi đọc revision 12
backend đọc revision 12
backend update -> revision 13
QiQi update bằng expected_revision=12 -> conflict
QiQi reread revision 13 -> reconcile -> retry
```

Không có last-write-wins silent overwrite.

SQLite dùng `BEGIN IMMEDIATE`, WAL và revision check để giữ atomicity khi nhiều
process/agent cùng dùng một database.

## Ownership policy

MCP storage không triển khai RBAC trong MVP. Boundary được enforce bởi agent policy.

### QiQi

QiQi sở hữu global orchestration state:

- overall `status` / `phase` / `summary`;
- repo involvement/assignment;
- global `next_actions`;
- reconciliation sau cross-repo handoff;
- quyết định task thực sự `done`.

### Repository execution agent

Agent được đọc toàn bộ Work Item để hiểu context nhưng:

- chỉ investigation/implementation/verification trong Git root hiện tại;
- chỉ cập nhật repo evidence/state mà nó thực sự xác lập;
- có thể ghi blocker, open question, checkpoint và handoff nó phát hiện;
- không đánh dấu sibling repo done;
- không tự xử lý phần việc của repository khác;
- cross-repo remaining work phải được ghi/handoff và trả lại QiQi để điều phối.

## Questions, decisions và changes

Open question tồn tại khi implementation không thể tự chốt một external/product
ambiguity. Agent không đoán để hoàn thành task.

Khi user/customer Q&A trả lời:

```text
question resolved
      ↓
decision active
      ↓
current_requirements được reconcile nếu semantics thay đổi
```

Nếu requirement/scope thực sự thay đổi, ghi thêm `changes[]`.

Decision cũ không bị xóa khi bị đổi. Mark `status: superseded` và trỏ
`superseded_by` sang decision mới để phân biệt "implementation trước sai" với
"requirement sau đã đổi".

## Handoff cross-repo

Handoff nằm trong chính canonical Work Item, không có handoff store thứ hai:

```text
backend agent
  ↓ ghi handoff backend -> frontend + evidence
Work Item
  ↓
QiQi reconcile/delegate
  ↓
frontend agent đọc cùng Work Item
```

Execution agent vẫn không sửa sibling repository.

## Persistence

MCP dùng một SQLite database explicit qua:

```bash
WORK_ITEM_DB_PATH=/absolute/path/work-items.sqlite3
```

Database không phụ thuộc CWD/workspace/repository. Cả QiQi và child agents kết nối
cùng user-scoped MCP registration.

Default installer path:

```text
~/.local/share/agent-work-items/work-items.sqlite3
```

## Cài đặt user scope

```bash
bash scripts/install-user-mcp.sh
```

Hoặc:

```bash
bash scripts/install-user-mcp.sh \
  --db-path /path/to/work-items.sqlite3
```

Installer tạo stable wrapper `~/.local/bin/agent-work-item-mcp` và đăng ký MCP tên
`work_item` cho Codex/Claude CLI đang có. Nếu registration cùng tên trỏ sang runtime
khác, installer fail thay vì overwrite âm thầm.

## Verification

Core tests không cần MCP runtime:

```bash
bash scripts/work-item-template-check.sh
```

Test cover ít nhất:

- create/get/list;
- questions/decisions/requirement changes;
- nested repo state merge;
- stale revision conflict;
- two concurrent writers từ cùng revision không cùng commit;
- immutable metadata;
- validation của semantic handoff/state.

Khi rollout thực tế, cần thêm smoke test trên Codex/Claude user-scoped MCP để xác
nhận cả QiQi và repo child session đều nhìn cùng một database.
