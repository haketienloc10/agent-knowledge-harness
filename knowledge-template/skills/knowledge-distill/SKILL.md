---
name: knowledge-distill
description: Dùng ngay trước mọi Shared Knowledge finalization review hoặc knowledge_write. Chắt lọc kết luận reusable đã được evidence xác nhận; tách fact, inference và uncertainty; không biến premise chưa xác minh của task/bug thành durable knowledge.
---

# Knowledge Distillation

Dùng procedure này khi policy yêu cầu durable knowledge review và trước mọi
`knowledge_write`, kể cả empty review.

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

### 5. Search trước, hydrate sau

Trước create/update, luôn dedupe theo **candidate meaning** bằng progressive disclosure:

1. Gọi `knowledge_search` với khoảng 3–8 discriminative concepts; ưu tiên canonical
   English concepts và thêm project/original-language aliases khi hữu ích.
2. Search result là **decision card** phục vụ chọn document, không phải evidence đủ để
   implementation, verification hay update. Card chỉ chứa bounded routing metadata.
3. Nếu một hoặc hai candidate có vẻ liên quan, gọi `knowledge_read(ids=[...])` với exact
   ID đã chọn để hydrate full semantic content.
4. Không dựa vào search summary/card như durable fact cuối cùng khi conclusion material
   cần content, provenance hoặc uncertainty của document.
5. `knowledge_search` cố ý không trả revision. Update chỉ được dùng exact `id` +
   `expected_revision` từ full `knowledge_read`.
6. Nếu nhiều card gần nhau, read tối đa one or two candidate mỗi call; không hydrate
   top-N chỉ vì search `limit` lớn.

Ưu tiên update existing concept thay vì create duplicate. Revision conflict phải
`knowledge_read` lại rồi re-distill.

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
field riêng. Khi update, giữ nguyên metadata không thay đổi thay vì reconstruct từ
search card.

### 8. Routing phục vụ future retrieval

Build một nested `routing` object:

- `summary`: reusable distinction/boundary quan trọng nhất và critical limitation nếu
  bỏ nó sẽ gây hiểu sai;
- `when_to_read`: future situations nơi knowledge này có thể đổi decision;
- `keywords`: concise canonical concepts, thường English;
- `aliases`: multilingual, legacy, acronym, ticket, symbol và project terms hữu ích.

`routing.summary` là retrieval abstract, không phải overflow storage cho investigation.

### 9. Build typed write payload

- Create: omit `id` và `expected_revision`.
- Update: exact `id` + `expected_revision` từ full `knowledge_read`.
- Không truyền `path`, `filename`, `directory`, `index_path`, `index` hoặc filesystem
  routing field khác.
- `content` có thể Vietnamese / English / mixed; không có field `language`.
- Knowledge MCP sở hữu ID/path/render/index/locking/revision/persistence mechanics.

### 10. Run payload readiness before calling knowledge_write

Viết `content` trước. Draft `routing.summary` và `sources[].note` sau cùng.

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
entry phải có non-empty `sources` list.

Trước call, xác nhận ít nhất:

1. candidate phản ánh evidence đã established, không phải task premise;
2. `routing` nested và summary nằm trong budget;
3. `sources` non-empty, notes nằm trong budget, provenance đủ audit;
4. detailed evidence/uncertainty nằm trong `content`;
5. update identity/revision đến từ full `knowledge_read`;
6. không có filesystem-owned/unsupported field;
7. `scope.id` và `canonical_name` dùng đúng separator.

Nếu validation fail, inspect typed schema/error, **repair only the fields** được nêu,
rồi retry một lần. Do not weaken verified claim chỉ để validation pass.

#### Tool-call JSON serialization recovery

`input JSON failed to parse` / `could not be parsed as JSON` xảy ra trước MCP body và
không chứng minh candidate nào đã persisted.

Nếu multi-entry write gặp lỗi serialization:

- không resend cùng multi-entry batch;
- retry surviving candidates từng entry bằng typed `knowledge_write` call;
- giữ exact update `id` + `expected_revision` từ `knowledge_read`;
- không manually construct/paste JSON string;
- nếu single-entry vẫn không serialize, report candidate là **not persisted** và dừng
  probing payload shapes.

### 11. Quyết định có write hay không

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
