# Optional Work Item Artifacts

Task artifacts là lớp detail **optional** của Global Work Item. Work Item vẫn là
canonical task state dùng cho orchestration; artifact chỉ materialize khi người dùng
explicitly yêu cầu intake/investigation/plan/review/report detail hoặc yêu cầu workflow
cụ thể cần artifact đó.

Không tạo artifact như progress bookkeeping mặc định.

## Truth boundary

```text
Work Item
  = current task truth: status/phase/requirements/repos/blockers/next actions

Artifact
  = optional detailed material derived from one exact Work Item revision
```

Nếu artifact cũ mâu thuẫn Work Item mới hơn, **Work Item thắng**.

Artifact có revision riêng. Append/finalize artifact không tăng Work Item revision.

## MVP artifact types

```text
intake
investigation
plan
review
report
```

Ví dụ `report` có thể chứa các section:

```text
original-request
requirement-review
investigation
implementation
verification
code-review
final-assessment
```

Type không tạo workflow FSM và không bắt buộc task phải có đủ artifact.

## Progressive disclosure

`work_item_get` chỉ trả thin artifact index: id/type/state/title/summary/revision,
`based_on_work_item_revision`, section count và size. Không trả artifact body.

```text
work_item_artifact_list
  -> thin metadata

work_item_artifact_get
  -> metadata + ordered section manifest

work_item_artifact_read
  -> bounded content của đúng một section
```

Không có MCP call nào đọc toàn artifact body.

`work_item_create` và `work_item_update` không thực hiện post-commit artifact enrichment.
Mutation result phản ánh đúng canonical Work Item write vừa commit; caller cần artifact
index thì đọc lại bằng `work_item_get` hoặc `work_item_artifact_list`.

## Storage

Cùng SQLite canonical store, nhưng tách table:

```text
work_items
work_item_artifacts
work_item_artifact_sections
work_item_artifact_chunks
```

Không tạo Markdown/filesystem artifact store thứ hai.

`artifacts` trong `work_item_get` là **derived metadata**, không phải field được persist
trong `work_items.document_json`; core từ chối create/update nếu caller cố ghi field
này.

Metadata artifact gồm:

```text
work_item_id
artifact_id
type
state: draft | complete
title
summary
based_on_work_item_revision
revision
created_at
updated_at
```

Section giữ order/title/count. Body nằm trong ordered chunks.

## Bounded payload

Hard server limits:

```text
artifact chunk write: <= 32,000 UTF-8 bytes / call
artifact section read: 4..32,000 UTF-8 bytes / call
artifacts / Work Item: <= 50
sections / artifact: <= 100
```

Chunk size kiểm theo UTF-8 bytes, không chỉ character count. Nội dung chunk được lưu
nguyên text input, không `.strip()` nên Markdown/code indentation và leading/trailing
newline được bảo toàn.

Read dùng continuation cursor. Cursor có thể tiếp tục giữa một stored chunk nhưng
server không cắt giữa UTF-8 code point.

Cursor là opaque contract đối với caller và được bind vào **artifact revision**. Một
logical paginated read vì vậy chỉ đọc từ một revision duy nhất:

```text
read revision 5 -> next_cursor(revision 5)
artifact append -> revision 6
read bằng cursor revision 5 -> artifact_revision_conflict
```

Khi conflict, caller đọc lại manifest và restart section read từ revision hiện tại,
không tiếp tục cursor cũ. Điều này tránh trộn page từ hai phiên bản artifact khác nhau.

## Artifact lifecycle

```text
create -> draft revision 1
append -> draft revision N+1
...
finalize -> complete revision N+1
```

Create phải dựa trên **exact current Work Item revision**. Nếu Work Item đã đổi, caller
reread/reconcile trước khi tạo artifact.

Append dùng exact `expected_artifact_revision`. Stale writer bị conflict:

```text
artifact_get -> reconcile -> retry
```

Artifact `complete` immutable trong MVP. Finalize artifact rỗng bị từ chối.

## MCP tools

```text
work_item_artifact_list(id, type?, limit?)
work_item_artifact_get(id, artifact_id)
work_item_artifact_create(
  id,
  type,
  title,
  summary,
  based_on_work_item_revision,
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
  limit_bytes?
)
work_item_artifact_finalize(id, artifact_id, expected_artifact_revision)
```

`section_title` bắt buộc ở chunk đầu tiên tạo section; các append sau có thể bỏ qua.

## Human CLI

Task detail chỉ hiện index:

```bash
agent-work-item show redmine:113387
```

Full artifact chỉ đọc khi yêu cầu:

```bash
agent-work-item artifact redmine:113387 report:1
agent-work-item artifact redmine:113387 report:1 --section code-review
```

Human CLI mở SQLite bằng `mode=ro`. Text-mode artifact view stream từng stored chunk
trực tiếp ra terminal; nó không materialize toàn artifact trong RAM. Chỉ explicit
`--json` mới materialize full selected artifact để in JSON. Cả hai path đều read-only
và không kéo body vào LLM/MCP context.
