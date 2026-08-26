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
sourcing, RBAC, notification, Redmine sync hoặc automatic phase transition. Human CLI
chỉ là read-only observer. QiQi vẫn quyết định workflow và orchestration.

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

decisions:
  - id: d1
    status: active
    summary: paymentStatus luôn xuất hiện; unknown trả null.
    decided_by: customer

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

## Snapshot và material history

Các field có hai vai trò khác nhau:

```text
summary/current_requirements/status/phase/repos/blockers/next_actions
= snapshot hiện tại để tiếp tục công việc ngay

questions/decisions/changes/checkpoints
= material history giải thích vì sao snapshot hiện tại hình thành
```

Không persist terminal transcript, command-by-command activity hoặc agent reasoning.

## Optional task artifacts

Artifact giải quyết detail dài không nên kéo theo mỗi lần đọc task tổng quát, ví dụ:

```text
intake
investigation
plan
review
report
```

Artifact **không bắt buộc**. Agent không tạo artifact như ceremony. Chỉ tạo khi user
explicitly yêu cầu detail artifact hoặc yêu cầu task report/review cần được persist.

Truth precedence:

```text
latest canonical Work Item > artifact dựa trên Work Item revision cũ
```

`work_item_get` chỉ gắn bounded thin artifact index. Full body không nằm trong
`work_items.document_json` và không được trả tự động.

Artifact body được chia section/chunk trong cùng SQLite DB:

```text
work_item_artifacts
work_item_artifact_sections
work_item_artifact_chunks
```

Mỗi append tối đa **16 KiB UTF-8**. Mỗi agent read tối đa **2 chunks / 32 KiB**.
Artifact có revision riêng; append/finalize không tăng Work Item revision.

Chi tiết đầy đủ: `ARTIFACTS.md`.

## Public MCP API

Canonical task state:

```text
work_item_get(id)
work_item_list(status?, repository?, limit?)
work_item_create(id, title, summary?, status?, phase?, current_requirements?, repositories?)
work_item_update(id, expected_revision, changes)
```

Optional detail artifacts:

```text
work_item_artifact_list(id, type?, limit?)
work_item_artifact_get(id, artifact_id)
work_item_artifact_create(id, type, title, based_on_work_item_revision, summary?, artifact_id?)
work_item_artifact_append(id, artifact_id, expected_artifact_revision, section_id, content, section_title?)
work_item_artifact_read(id, artifact_id, section_id, cursor?, limit_chunks?)
work_item_artifact_finalize(id, artifact_id, expected_artifact_revision, summary?)
```

`work_item_artifact_get` chỉ trả metadata + section manifest. Muốn body phải đọc từng
section bằng `work_item_artifact_read` và follow `next_cursor`.

`work_item_update` dùng JSON merge-patch semantics:

- nested object merge;
- array replace nguyên tử;
- `null` remove field;
- required field bị remove sẽ fail validation.

Arrays replace nguyên tử là intentional cho MVP: caller phải đọc Work Item hiện tại,
reconcile full intended array, rồi update bằng exact revision.

Derived artifact index fields do `work_item_get` trả (`artifacts`, `artifact_count`,
`artifacts_truncated`) là read-only view; không được persist bằng `work_item_update`.

## Optimistic concurrency

Mọi Work Item có `revision` do MCP sở hữu.

```text
QiQi đọc revision 12
backend đọc revision 12
backend update -> revision 13
QiQi update bằng expected_revision=12 -> conflict
QiQi reread revision 13 -> reconcile -> retry
```

Artifact có revision độc lập:

```text
Work Item revision 13
report:1 revision 1
append -> report:1 revision 2
append -> report:1 revision 3
finalize -> report:1 revision 4
Work Item vẫn revision 13 nếu task semantics không đổi
```

Không có last-write-wins silent overwrite.

SQLite dùng `BEGIN IMMEDIATE`, WAL và exact revision check để giữ atomicity khi nhiều
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

Artifact không thay ownership này. Một report cũ không override task state hiện hành.

### Repository execution agent

Agent được đọc toàn bộ Work Item để hiểu context nhưng:

- chỉ investigation/implementation/verification trong Git root hiện tại;
- chỉ cập nhật repo evidence/state mà nó thực sự xác lập;
- có thể ghi blocker, open question, checkpoint và handoff nó phát hiện;
- không đánh dấu sibling repo done;
- không tự xử lý phần việc của repository khác;
- cross-repo remaining work phải được ghi/handoff và trả lại QiQi để điều phối.

Nếu user explicit yêu cầu artifact và TaskPacket truyền yêu cầu đó, repo agent có thể
contribute detail thuộc current repo; artifact vẫn không cho phép cross-repo execution.

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

Artifact tables nằm trong cùng DB; DB cũ được nâng schema lazily bằng idempotent table
creation. Existing `work_items` rows/revisions không bị rewrite.

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

Installer tạo:

```text
~/.local/bin/agent-work-item-mcp   # MCP runtime cho agents
~/.local/bin/agent-work-item       # strictly read-only human CLI
```

MCP registration tên `work_item` vẫn trỏ vào `agent-work-item-mcp`. Human CLI không
được đăng ký thành MCP tool/server.

Human commands:

```bash
agent-work-item list
agent-work-item show redmine:113387
agent-work-item artifact redmine:113387 report:1 --manifest
agent-work-item artifact redmine:113387 report:1
```

Chi tiết human UX: `CLI.md`.

## Verification

```bash
bash scripts/work-item-template-check.sh
```

Test/check cover ít nhất:

- Work Item create/get/list/update;
- questions/decisions/requirement changes;
- nested repo state merge;
- stale Work Item revision conflict;
- concurrent Work Item writers;
- artifact DB upgrade không đổi Work Item revision;
- artifact create/list/get manifest;
- exact `based_on_work_item_revision`;
- 16 KiB UTF-8 append bound;
- 2-chunk bounded read + cursor;
- independent artifact revision conflict;
- draft -> complete lifecycle và complete immutability;
- concurrent artifact writers;
- thin/truncated artifact index;
- human CLI full/section streaming;
- human CLI read-only invariant;
- MCP vẫn expose đúng 4 task tools + 6 artifact tools.

Khi rollout thực tế, cần smoke test trên fresh Codex/Claude process để xác nhận tool
schema mới được reload và QiQi/repo child cùng nhìn một DB/artifact set.
