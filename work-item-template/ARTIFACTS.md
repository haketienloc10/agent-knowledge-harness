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

Artifact type là contract cố định của MVP:

```text
intake
investigation
plan
review
report
```

Type không tạo workflow FSM và không bắt buộc task phải có đủ artifact.

**Section/header không phải schema cố định.** `section_id` và `section_title` được caller
chọn khi append chunk đầu tiên của section. Storage chỉ giữ section thực tế đã được tạo.

Repo có default advisory templates cho 5 type tại:

```text
work-item-template/config/artifact-templates.json
```

Default `report` hiện được định hướng cho Redmine Textile với 8 mục:

```text
root-cause-requirement   -> h3. +1. Root-cause/requirement:+
solution                 -> h3. +2. Solution:+
affected                 -> h3. +3. Affected:+
impact-module-analysis   -> h3. +4. Impact Module Analysis+
sql-report               -> h3. +5. SQL_Report+
commits                  -> h3. +6. Commits:+
testcase-ut              -> h3. +7. Testcase /UT:+
deploy                   -> h3. +8. Deploy:+
```

`purpose` của từng section hướng dẫn cách dùng `p((.`/Textile bullets và khóa các
placeholder phải để user tự điền khi chưa có evidence, ví dụ
`<<branch user tự điền>>` và `<<pre4 user tự điền>>`. Đây vẫn là guidance có thể chỉnh
sửa, không phải danh sách section bắt buộc.

## Configurable artifact template guidance

Template config chỉ giúp agent chọn section/header nhất quán. Nó **không** trở thành
canonical artifact state và không biến artifact thành workflow engine.

Mỗi configured type có dạng:

```json
{
  "report": {
    "description": "Redmine-ready final report in Textile style ...",
    "sections": [
      {
        "id": "root-cause-requirement",
        "title": "h3. +1. Root-cause/requirement:+",
        "purpose": "Explain the effective requirement and verified root cause ..."
      }
    ]
  }
}
```

Các key type vẫn phải thuộc 5 MVP type cố định. Một type có thể được bỏ khỏi config;
khi đó create artifact type đó vẫn hợp lệ nhưng `template_guidance` trả `null`.

MCP load và validate config **một lần khi process khởi động**. Sửa config không làm
process đang chạy tự reload; mở/restart MCP session để nhận template mới.

Default path là file trong repo ở trên. Có thể override bằng environment variable:

```bash
export WORK_ITEM_ARTIFACT_TEMPLATES_PATH="$HOME/.config/agent-work-items/artifact-templates.json"
```

Environment variable phải tồn tại ở process mở Codex/Claude/MCP. Stable wrapper không
sanitize environment nên giá trị này được truyền qua. Nếu không set, server dùng repo
default config.

Config dùng JSON để không thêm parser/dependency ngoài stdlib. Startup fail rõ ràng nếu
file không tồn tại, JSON invalid, type/field không hỗ trợ, section id invalid/duplicate,
hoặc config vượt hard bound 64,000 bytes.

`work_item_artifact_create` trả manifest vừa tạo cộng derived guidance:

```json
{
  "artifact_id": "report:1",
  "type": "report",
  "state": "draft",
  "revision": 1,
  "template_guidance": {
    "description": "Redmine-ready final report in Textile style ...",
    "sections": [
      {
        "id": "root-cause-requirement",
        "title": "h3. +1. Root-cause/requirement:+",
        "purpose": "Explain the effective requirement and verified root cause ..."
      }
    ]
  }
}
```

Boundary bắt buộc:

```text
template_guidance
  = advisory startup config

stored artifact sections
  = actual artifact truth
```

Template **không**:

- persist vào artifact tables;
- tăng artifact/Work Item revision;
- bắt buộc section phải tồn tại;
- cấm section ngoài template;
- ép section order/title;
- làm finalize fail vì thiếu section template.

Artifact đã tạo trước khi sửa config không thay đổi. Config mới chỉ thay guidance của
`work_item_artifact_create` trong MCP process khởi động sau đó. Không cần database
migration khi chỉ sửa template config.

## Progressive disclosure

`work_item_get` chỉ trả thin artifact index: id/type/state/title/summary/revision,
`based_on_work_item_revision`, section count và size. Không trả artifact body hoặc
template guidance.

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
artifact template config: <= 64,000 bytes
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
agent-work-item artifact redmine:113387 report:1 --section solution
```

Human CLI mở SQLite bằng `mode=ro`. Text-mode artifact view stream từng stored chunk
trực tiếp ra terminal; nó không materialize toàn artifact trong RAM. Chỉ explicit
`--json` mới materialize full selected artifact để in JSON. Cả hai path đều read-only
và không kéo body vào LLM/MCP context.

Human CLI là diagnostic/inspection view và có metadata/counter riêng quanh từng section;
nó **không** phải raw Redmine Textile renderer. Redmine formatting trong default
`report` template là guidance cho agent khi tạo/report artifact content. Nếu sau này cần
copy-paste nguyên artifact thành một Textile document không có CLI decoration, đó nên là
một explicit raw/render command riêng thay vì thay đổi read-only diagnostic output hiện
tại.
