# Optional Work Item artifacts

Task artifact là material chi tiết gắn với một canonical Work Item nhưng **không phải
canonical task state**. Work Item vẫn là nơi QiQi đọc nhanh để biết task đang ở đâu,
đang blocked bởi gì và bước tiếp theo là gì. Artifact chỉ được hydrate khi cần detail.

## Explicit-only / optional

Artifact là optional. Agent **không tự tạo artifact như ceremony**.

Chỉ tạo khi user explicitly yêu cầu một detail artifact hoặc một task report/review cần
được persist, ví dụ:

```text
chỉ investigation và lưu investigation artifact
lập plan và lưu plan artifact
review lại implementation + UT và lưu review artifact
tổng kết task từ intake đến code review thành report
```

Một `$ticket-work-item` bình thường không bắt buộc có artifact nào.

Artifact type MVP:

```text
intake
investigation
plan
review
report
```

## Truth precedence

```text
canonical Work Item latest
        >
artifact detail based on an older Work Item revision
```

Artifact giữ field `based_on_work_item_revision` để biết detail đó được lập dựa trên
snapshot nào. Artifact không được dùng để override current requirements, active decision,
status, phase, blocker hoặc next action mới hơn trong Work Item.

## Progressive disclosure

Agent-facing flow:

```text
work_item_get
  -> task state + bounded thin artifact index only

work_item_artifact_list
  -> thin metadata only

work_item_artifact_get
  -> metadata + ordered section manifest only

work_item_artifact_read
  -> bounded section chunk window
```

Không MCP read nào trả full artifact body.

`work_item_get` chỉ trả tối đa 20 thin artifact entries và thêm:

```text
artifact_count
artifacts_truncated
```

Nếu index bị truncate, dùng `work_item_artifact_list`.

## Large payload contract

Artifact có thể dài hàng chục/hàng trăm KB nên body được ghi theo section/chunk.

Hard limits MVP:

```text
append content: <= 16 KiB UTF-8 / call
read window:    <= 2 stored chunks / call
max read body:  <= 32 KiB UTF-8 / call
```

Server kiểm tra cả MCP schema length và UTF-8 byte size. Unicode nhiều byte vẫn phải
nằm trong 16 KiB UTF-8 thực tế.

Nếu append quá lớn, server trả actionable error `artifact_chunk_too_large`; caller phải
split content, không retry cùng payload.

## Storage

Cùng SQLite database với Work Item nhưng table riêng:

```text
work_items

work_item_artifacts
  work_item_id
  artifact_id
  type
  state
  title
  summary
  based_on_work_item_revision
  revision
  created_at
  updated_at

work_item_artifact_sections
  work_item_id
  artifact_id
  section_id
  title
  position
  created_at
  updated_at

work_item_artifact_chunks
  work_item_id
  artifact_id
  section_id
  chunk_index
  content
  content_bytes
  created_at
```

Không lưu full artifact vào `work_items.document_json` và không tạo filesystem artifact
store. DB cũ được nâng schema lazily bằng `CREATE TABLE IF NOT EXISTS`; existing Work
Item revision/document không bị rewrite.

## Independent revision

Artifact revision độc lập Work Item revision:

```text
Work Item revision 8
create report -> artifact revision 1
append        -> artifact revision 2
append        -> artifact revision 3
finalize      -> artifact revision 4

Work Item vẫn revision 8 nếu task semantics không đổi.
```

`work_item_artifact_create` yêu cầu exact `based_on_work_item_revision` bằng current
Work Item revision tại thời điểm create. Stale value -> normal `revision_conflict` và
caller reread Work Item.

Append/finalize yêu cầu exact `expected_artifact_revision`. Stale value ->
`artifact_revision_conflict`; caller dùng `work_item_artifact_get`, reconcile rồi retry.

## Artifact lifecycle

MVP chỉ có:

```text
draft -> complete
```

`work_item_artifact_create` luôn tạo `draft`.

`work_item_artifact_append`:

- chỉ cho `draft`;
- một call ghi đúng một chunk;
- section mới bắt buộc `section_title`;
- section đã tồn tại không được đổi title âm thầm;
- section/chunk order được server sở hữu.

`work_item_artifact_finalize`:

- yêu cầu artifact có ít nhất một content chunk;
- chuyển sang `complete`;
- có thể cập nhật thin summary cuối;
- `complete` không nhận append thêm.

MVP không có reopen/edit/delete để tránh biến artifact subsystem thành document editor.
Nếu cần version mới, tạo artifact mới như `report:2`.

## Public MCP tools

```text
work_item_artifact_list(id, type?, limit?)
work_item_artifact_get(id, artifact_id)
work_item_artifact_create(
  id,
  type,
  title,
  based_on_work_item_revision,
  summary?,
  artifact_id?
)
work_item_artifact_append(
  id,
  artifact_id,
  expected_artifact_revision,
  section_id,
  content,
  section_title?
)
work_item_artifact_read(
  id,
  artifact_id,
  section_id,
  cursor?,
  limit_chunks?
)
work_item_artifact_finalize(
  id,
  artifact_id,
  expected_artifact_revision,
  summary?
)
```

Nếu `artifact_id` không truyền lúc create, server cấp atomically theo type:

```text
investigation:1
investigation:2
report:1
```

## Read cursor

Mỗi append vào một section tạo `chunk_index` liên tục từ `0`.

Ví dụ section có 3 chunks:

```text
read cursor=0 limit_chunks=2
-> content chunks 0+1
-> next_cursor=2
-> has_more=true

read cursor=2 limit_chunks=2
-> content chunk 2
-> next_cursor=null
-> has_more=false
```

Chunk boundary là transport/storage detail. Nội dung được concatenate exact; caller phải
bao gồm newline/spacing trong chunk content nếu muốn giữ formatting.

## Human CLI

Task detail chỉ hiện thin artifact index:

```bash
agent-work-item show redmine:113387
```

Xem manifest không body:

```bash
agent-work-item artifact redmine:113387 report:1 --manifest
```

Stream full artifact cho human:

```bash
agent-work-item artifact redmine:113387 report:1
```

Chỉ một section:

```bash
agent-work-item artifact redmine:113387 report:1 --section verification
```

Human CLI mở SQLite `mode=ro`; artifact command stream từng stored chunk, không gom full
body trước khi output và không tạo mutation path thứ hai.

## Example report outline

Một report user yêu cầu sau task có thể gồm:

```text
original-request
requirement-review
investigation
implementation
verification
code-review
final-assessment
```

Đây là convention nội dung, không phải schema bắt buộc. Sections để agent/user tổ chức
artifact theo mục đích thực tế mà không thêm workflow DSL vào MCP.
