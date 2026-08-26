# Global Work Item MCP

Global Work Item MCP là source of truth duy nhất cho **mutable product-task state**
được dùng chung bởi QiQi và execution agents trong các repository con.

```text
Global Work Item MCP   = task truth + optional task-detail artifacts
Knowledge MCP          = reusable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

## Mục tiêu MVP

Giải quyết continuity cho task kéo dài qua investigation, planning, implementation,
unit test, IT, UAT, fix bug và Q&A mà không yêu cầu người dùng hoặc QiQi kể lại toàn
bộ lịch sử sau mỗi session.

MVP cố ý **không** là project-management product. Không có workflow DSL, event
sourcing, RBAC, notification, Redmine sync, automatic phase transition hay web
dashboard. Human CLI chỉ là read-only observer của canonical store.

## Canonical Work Item

Mỗi product task có một ID ổn định:

```text
redmine:116655
redmine:151921
```

Format là `<source>:<external-id>`.

Work Item snapshot/material history gồm:

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

blockers: []
handoffs: []
next_actions: []
checkpoints: []
```

`phase` là descriptive state, không phải finite-state-machine. Task có thể quay từ
UAT về implementation/fix rồi trở lại IT/UAT.

Global status MVP:

```text
active | waiting | blocked | done | cancelled
```

Repo status:

```text
pending | active | waiting | blocked | done | not_required
```

## Snapshot và material history

```text
summary/current_requirements/status/phase/repos/blockers/next_actions
= snapshot hiện tại để tiếp tục công việc ngay

questions/decisions/changes/checkpoints
= material history giải thích vì sao snapshot hiện tại hình thành
```

Không persist terminal transcript, command-by-command activity hoặc agent reasoning.

## Optional task artifacts

Một số detail như intake, investigation, plan, review hoặc final report có thể rất dài
và không cần hydrate mỗi lần đọc task status. Chúng được lưu thành **optional task
artifacts** trong cùng SQLite canonical store.

```text
Work Item
  = current task truth / orchestration state

Artifact
  = optional detailed material derived từ một exact Work Item revision
```

Artifact chỉ được materialize khi người dùng explicitly yêu cầu loại detail đó hoặc
workflow explicit yêu cầu artifact. Không tạo artifact như progress bookkeeping mặc
định.

MVP types:

```text
intake | investigation | plan | review | report
```

`work_item_get` chỉ trả thin artifact metadata, không trả body. Full detail dùng
progressive disclosure:

```text
artifact_list -> artifact_get manifest -> artifact_read bounded section chunks
```

Artifact revision độc lập với Work Item revision. Artifact append/finalize không làm
Work Item revision tăng và không cạnh tranh optimistic writer với task-state update.

Hard payload/storage bounds:

```text
write chunk        <= 32,000 UTF-8 bytes/call
read section       4..32,000 UTF-8 bytes/call
artifacts/item     <= 50
sections/artifact  <= 100
```

Artifact lifecycle:

```text
create -> draft
append -> draft revision N+1
finalize -> complete, immutable trong MVP
```

Create artifact phải dựa trên exact current Work Item revision qua
`based_on_work_item_revision`. Nếu artifact cũ mâu thuẫn Work Item mới hơn, Work Item
thắng.

Chi tiết đầy đủ: `ARTIFACTS.md`.

## MCP API

Canonical Work Item tools:

```text
work_item_get(id)
work_item_list(status?, repository?, limit?)
work_item_create(id, title, summary?, status?, phase?, current_requirements?, repositories?)
work_item_update(id, expected_revision, changes)
```

Optional artifact tools:

```text
work_item_artifact_list(id, type?, limit?)
work_item_artifact_get(id, artifact_id)
work_item_artifact_create(id, type, title, summary, based_on_work_item_revision, artifact_id?)
work_item_artifact_append(id, artifact_id, expected_artifact_revision, section_id, content, section_title?)
work_item_artifact_read(id, artifact_id, section_id, cursor?, limit_bytes?)
work_item_artifact_finalize(id, artifact_id, expected_artifact_revision)
```

`work_item_update` dùng JSON merge-patch semantics:

- nested object merge;
- array replace nguyên tử;
- `null` remove field;
- required field bị remove sẽ fail validation;
- derived `artifacts` metadata không được write qua `work_item_update`.

## Optimistic concurrency

Work Item revision:

```text
QiQi đọc revision 12
backend đọc revision 12
backend update -> revision 13
QiQi update expected_revision=12 -> conflict
QiQi reread revision 13 -> reconcile -> retry
```

Artifact có optimistic revision riêng:

```text
artifact revision 4
writer A append -> revision 5
writer B append expected_artifact_revision=4 -> conflict
writer B artifact_get -> reconcile -> retry
```

Không có silent last-write-wins.

SQLite dùng WAL, `BEGIN IMMEDIATE` và exact revision checks cho mutation paths.

## Ownership policy

Storage không triển khai RBAC trong MVP. Boundary được enforce bởi agent policy.

QiQi sở hữu global orchestration state: overall status/phase/summary, repo assignment,
next actions, cross-repo reconciliation và final completion.

Repo agent:

- chỉ execute trong current Git root;
- chỉ update repo evidence/state nó thực sự xác lập;
- có thể ghi blocker, open question, checkpoint và handoff nó phát hiện;
- không mark sibling repo done;
- không tự xử lý repository khác.

Artifact không thay đổi ownership rule. Detail artifact không được dùng để override
newer canonical Work Item state.

## Persistence

Explicit database path:

```bash
WORK_ITEM_DB_PATH=/absolute/path/work-items.sqlite3
```

Default installer path:

```text
~/.local/share/agent-work-items/work-items.sqlite3
```

Tables:

```text
work_items
work_item_artifacts
work_item_artifact_sections
work_item_artifact_chunks
```

Không có filesystem/Markdown task-artifact store thứ hai.

## Human CLI

```bash
agent-work-item list
agent-work-item show redmine:113387
agent-work-item artifact redmine:113387 report:1
agent-work-item artifact redmine:113387 report:1 --section code-review
```

`show` chỉ hiển thị thin artifact index. `artifact` mới đọc full body cho human terminal.
CLI mở SQLite bằng `mode=ro` và không có mutation path.

Chi tiết: `CLI.md`.

## Cài đặt user scope

```bash
bash scripts/install-user-mcp.sh
```

Hoặc custom DB:

```bash
bash scripts/install-user-mcp.sh \
  --db-path /path/to/work-items.sqlite3
```

Installer tạo:

```text
~/.local/bin/agent-work-item-mcp  # MCP runtime
~/.local/bin/agent-work-item      # read-only human CLI
```

và đăng ký MCP tên `work_item` cho Codex/Claude CLI đang có. Existing registration
cùng tên nhưng trỏ runtime khác làm installer fail thay vì overwrite âm thầm.

## Verification

```bash
bash scripts/work-item-template-check.sh
```

Test/check cover ít nhất:

- create/get/list/update Work Item;
- semantic Q&A/decision/change/repo state;
- stale Work Item revision và concurrent writers;
- artifact create/list/get manifest;
- stale artifact revision;
- artifact revision độc lập Work Item revision;
- exact Work Item revision khi tạo artifact;
- UTF-8 byte write/read limits + continuation cursor;
- exact preservation của Markdown/code whitespace;
- finalize empty bị reject và complete artifact immutable;
- human CLI thin artifact index/full explicit artifact view;
- human CLI không ghi SQLite;
- static invariant cho MCP tool count, bounded payload và read-only boundary.

Sau rollout thực tế, mở fresh Codex/Claude session để MCP client discover tool surface
mới và smoke test QiQi + repository child trên cùng database.
