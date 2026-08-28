---
name: knowledge-distill
description: Dùng ngay trước mọi Shared Knowledge finalization review, knowledge_write hoặc knowledge_update. Chắt lọc kết luận reusable đã được evidence xác nhận; tách fact, inference và uncertainty; không biến premise chưa xác minh của task/bug thành durable knowledge.
---

# Knowledge Distillation

Dùng procedure này khi policy yêu cầu durable knowledge review và trước mọi mutation qua
`knowledge_write` hoặc `knowledge_update`, kể cả empty review.

Output của skill là **durable conclusions được evidence hỗ trợ**, không phải bản tóm
tắt task đã dẫn tới investigation.

## Core rule

**Persist what the work established, not what the task assumed.**

Bug report, ticket title, user suspicion, attempted fix, search query hoặc working
hypothesis chỉ là investigation input. Chúng chỉ trở thành durable knowledge khi
evidence thật sự xác lập conclusion tương ứng.

Nếu investigation không xác nhận bug premise ban đầu nhưng xác lập một boundary,
invariant, negative finding, diagnostic rule, ownership fact, contract, operational
constraint hoặc observability gap có tính reusable, persist conclusion đã verify đó
với semantic identity riêng.

## Procedure

### 1. Lập evidence ledger

Trước khi đặt tên candidate, phân loại evidence thành:

- **verified source/code facts**: source, config, schema, static control/data flow;
- **verified test/runtime observations**: test, log, trace, command, runtime artifact;
- **trusted decisions/contracts**: user/architecture/spec/decision evidence có thẩm quyền;
- **inferences**: kết luận hợp lý suy ra từ nhiều facts nhưng chưa trực tiếp quan sát;
- **remaining uncertainty**: câu hỏi material mà evidence chưa giải quyết.

Không trộn các nhóm này chỉ để làm knowledge ngắn hơn.

### 2. Rút durable candidate từ evidence, không từ task title

Với mỗi candidate, kiểm tra:

- Nó có thay đổi future implementation, investigation, verification, design,
  ownership hoặc operational decision không?
- Nó có đủ non-trivial để việc đọc lại source hiện tại không phải con đường rẻ hơn?
- Nó có khả năng sống lâu hơn task/branch/session hiện tại không?
- Evidence có xác lập candidate đủ mạnh để persist không?

Candidate tốt gồm invariant, boundary, contract, ownership, compatibility constraint,
diagnostic interpretation rule, recurring operational behavior, verification rule và
durable decision.

Negative result chỉ hữu ích khi nó thu hẹp một boundary ổn định. `Không reproduce bug
X` tự nó là task status, không phải durable knowledge.

### 3. Calibrate claim theo evidence

**Compression must not increase certainty.**

Distillation được phép ngắn hơn evidence nhưng không được mạnh hơn evidence. Đặc biệt:

- static code-path property không đồng nghĩa runtime delivery guarantee;
- một observed execution không đại diện cho mọi execution;
- absence of evidence không phải evidence of absence;
- chỉ dùng `always`, `never`, `exactly once`, `at most one`, `guarantees`, `impossible`
  khi boundary được cited thực sự chứng minh chúng;
- giữ remaining uncertainty nếu nó có thể đổi future decision.

### 4. Chọn semantic identity từ durable conclusion

Chọn `scope`, `canonical_name`, title theo conclusion đã biết, không theo incident/ticket.

- scope: `global`, `system`, `repo`, `domain`;
- `canonical_name`: lowercase kebab-case;
- `scope.id`: lowercase letters/numbers, chỉ dùng `.` hoặc `-` làm separator;
- không dùng ticket ID, temporary branch hoặc unverified bug hypothesis làm identity.

Legacy/project/multilingual terms hữu ích có thể đặt trong aliases.

### 5. Search trước, hydrate đúng semantic scope sau

Trước create/update, luôn dedupe theo **candidate meaning** bằng progressive disclosure:

1. Gọi `knowledge_search` với khoảng 3–8 discriminative concepts; ưu tiên canonical
   English concepts và thêm project/original-language aliases khi hữu ích.
2. Search result là **decision card** phục vụ chọn document, không phải evidence đủ để
   implementation, verification hay update. Card chỉ chứa bounded routing metadata.
3. Chọn one or two exact IDs cần thiết. Không hydrate top-N chỉ vì search `limit` lớn.
4. Với existing target, đọc ở **smallest sufficient semantic scope**:
   - cần hiểu/re-distill toàn concept hoặc whole-content replacement → `knowledge_read`;
   - chỉ sửa title/routing/sources hoặc cần section index + provenance + exact revision →
     `knowledge_read_metadata`;
   - chỉ sửa/verify một existing marked section đã biết → `knowledge_read_section`.
5. `knowledge_search` cố ý không trả revision. Mutation existing target chỉ dùng exact
   `id` + `expected_revision` từ một exact read surface ở trên.
6. Nếu metadata read cho thấy section cần sửa, dùng exact returned section id; không tự
   invent section id.
7. Nếu một section không đủ evidence/context để kết luận an toàn, escalate sang full
   `knowledge_read` thay vì đoán phần còn lại.

Ưu tiên update existing concept thay vì create duplicate. Revision conflict phải reread
đúng target, reconcile/re-distill với revision mới rồi retry. Không reuse stale revision
chỉ vì phần agent muốn sửa khác với phần concurrent writer vừa đổi.

### 6. Làm provenance đủ mạnh để audit

Mọi material durable claim phải truy được về `sources`.

Với repository evidence, ưu tiên immutable commit/revision trong `ref`. Moving branch
là provenance yếu hơn. `sources[].note` là compact pointer tới behavior/boundary đã
verify, không phải evidence dump.

Không persist guess/hypothesis chỉ vì có source đi kèm.

### 7. Giữ fact, implication và uncertainty trong content

Content phải giúp future reader phân biệt khi material:

- điều gì đã established;
- diagnostic/design implication nào theo sau;
- điều gì vẫn unresolved và cần runtime/owner evidence.

Không viết chronological investigation diary. Chỉ giữ evidence cần để hiểu và audit
durable conclusion.

Full `knowledge_read` trả semantic `content` không chứa canonical H1; title/routing là
field riêng. `knowledge_read_section` trả body của đúng section, không marker/heading.
Metadata-only read không trả content. Khi mutation chỉ chạm một scope, preserve phần
không thay đổi thay vì reconstruct nó từ search card hoặc model memory.

### 8. Stable semantic sections cho knowledge lớn

Section là optional structure bên trong cùng một canonical Markdown document; không phải
chunk store, file riêng hay revision riêng.

Marker contract:

```markdown
<!-- knowledge-section:contract -->
## Contract

...

<!-- knowledge-section:failure-modes -->
## Failure modes

...
```

Rules:

- section id lowercase kebab-case và unique trong document;
- marker phải là standalone exact line, không indent;
- marker phải ngay trước Markdown H2-H6 heading;
- heading là presentation; section id mới là stable identity;
- section boundary chạy marker-to-marker, nên nested headings trong body vẫn hợp lệ;
- small/legacy knowledge không có marker vẫn hợp lệ;
- `knowledge_update(... section=...)` chỉ replace body của existing section, giữ marker
  + heading và không implicit create/delete/reorder section;
- section replacement không được inject marker mới;
- nếu cần thay đổi structure lớn, dùng whole-content replacement sau khi full-read và
  re-distill toàn concept.

Không thêm marker chỉ để chia nhỏ một document vốn đã ngắn và cohesive.

### 9. Routing phục vụ future retrieval

Build một nested `routing` object:

- `summary`: reusable distinction/boundary quan trọng nhất và critical limitation nếu
  bỏ nó sẽ gây hiểu sai;
- `when_to_read`: future situations nơi knowledge này có thể đổi decision;
- `keywords`: concise canonical concepts, thường English;
- `aliases`: multilingual, legacy, acronym, ticket, symbol và project terms hữu ích.

`routing.summary` là retrieval abstract, không phải overflow storage cho investigation.

### 10. Build typed mutation payload

Chọn mutation nhỏ nhất vẫn biểu đạt đúng semantic change:

- **Create:** `knowledge_write`, omit `id` và `expected_revision`.
- **Whole-document replacement:** legacy/full `knowledge_write` update với exact `id` +
  `expected_revision`; dùng khi toàn concept cần re-distill, không phải vì API bắt buộc.
- **Metadata-only:** `knowledge_update(changes.metadata=...)`; chỉ gửi changed title,
  routing fields và/hoặc full intended `sources` list.
- **Whole content only:** `knowledge_update(changes.content=...)`; metadata được server
  preserve.
- **One existing section:** `knowledge_update(changes.section={id, content})`; chỉ gửi
  replacement body, không marker/heading.
- Metadata có thể combine atomically với whole-content hoặc one-section mutation khi
  chúng dựa trên cùng evidence/revision.
- Whole-content và section replacement mutually exclusive trong một call.
- `canonical_name` và `scope` không nằm trong partial patch; canonical identity/path
  không đổi âm thầm.
- Không truyền `path`, `filename`, `directory`, `index_path`, `index` hoặc filesystem
  routing field khác.
- `content` có thể Vietnamese / English / mixed; không có field `language`.
- Knowledge MCP sở hữu ID/path/render/index/locking/revision/persistence mechanics.

Partial mutation vẫn tạo **một SHA-256 revision mới cho whole document**. Không có
metadata revision hay per-section revision riêng.

### 11. Run payload readiness before mutation

Với create/whole rewrite, viết `content` trước. Draft `routing.summary` và
`sources[].note` sau cùng. Với partial update, chỉ regenerate semantic scope thực sự đổi;
không copy lại untouched large content vào request.

#### Summary and source-note budget gate

Trước call:

- `routing.summary`: target **300 characters or less**;
- mỗi `sources[].note`: target **600 characters or less**;
- khi environment hỗ trợ count, đo **deterministically** bằng `len(...)` hoặc equivalent;
- nếu không count chính xác được, dùng fallback chặt hơn khoảng 200/400 chars.

Do not mechanically truncate field quá dài. Rewrite summary thành:

`durable conclusion + critical boundary`

Rewrite source note thành:

`stable provenance location + exact behavior/boundary`

Detailed evidence, ruled-out hypotheses và uncertainty đi vào `content`. Mọi persisted
entry phải có non-empty `sources` list; metadata patch không cần resend sources nếu
sources hiện hành vẫn đúng.

Trước call, xác nhận ít nhất:

1. candidate phản ánh evidence đã established, không phải task premise;
2. exact target + revision đến từ sufficient exact read, không từ search card;
3. mutation scope đủ để preserve untouched canonical content/metadata;
4. `routing` nested và summary nằm trong budget nếu routing đổi;
5. `sources` non-empty, notes nằm trong budget, provenance đủ audit nếu sources đổi;
6. section id đến từ canonical metadata/section read, không invent;
7. không có filesystem-owned/unsupported field;
8. `scope.id` và `canonical_name` dùng đúng separator khi create/full write.

Nếu validation fail, inspect typed schema/error, **repair only the fields** được nêu,
rồi retry một lần. Do not weaken verified claim chỉ để validation pass.

#### Tool-call JSON serialization recovery

`input JSON failed to parse` / `could not be parsed as JSON` xảy ra trước MCP body và
không chứng minh candidate nào đã persisted.

Nếu multi-entry `knowledge_write` gặp lỗi serialization:

- không resend cùng multi-entry batch;
- retry surviving candidates từng entry bằng typed `knowledge_write` call;
- giữ exact update `id` + `expected_revision` từ exact read;
- không manually construct/paste JSON string;
- nếu single-entry vẫn không serialize, report candidate là **not persisted** và dừng
  probing payload shapes.

Nếu `knowledge_update` serialization fail, retry một lần với cùng typed scope nhỏ và
exact revision chỉ khi chưa có evidence tool body đã chạy. Nếu không xác định được write
đã commit hay chưa, reread canonical target trước retry.

### 12. Quyết định có write hay không

Chỉ write candidate vượt qua quality gates.

Reject candidate chỉ là:

- task status / working log;
- obvious fact rẻ hơn khi đọc live source;
- unverified ticket/bug premise;
- root-cause guess/hypothesis chưa đủ evidence;
- temporary implementation detail không có expected reuse;
- `bug not reproduced` nhưng không có durable boundary học được.

Nếu policy yêu cầu review nhưng không còn candidate, gọi
`knowledge_write(entries=[])`. Nếu policy cho phép skip review toàn bộ, không gọi empty
write như ceremony.

## Conflict với live truth

Nếu shared knowledge conflict với current owner source/test hoặc live owner evidence
mạnh hơn, live evidence thắng cho current work. Chỉ update shared knowledge sau khi
replacement conclusion đã được verify.
