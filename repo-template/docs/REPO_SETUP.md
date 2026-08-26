# Thiết lập Repository con cho QiQi Workspace

Tài liệu này dùng khi đưa `repo-template/` vào một Git repository nằm trong workspace
multi-repo. Shared Knowledge MCP phải được cài user/global scope trước để fresh repo
agent thấy đủ ba tools independent CWD:

```text
knowledge_search
knowledge_read
knowledge_write
```

## Kết quả cần đạt

- `AGENTS.md` bảo vệ Git-root/sibling boundaries;
- `ARCHITECTURE.md` và `docs/VERIFY.md` có live evidence;
- execution agent nhận original user intent + live upstream context từ structured
  TaskPacket, không tự đọc sibling source/runtime state;
- agent hiểu task rồi áp dụng Shared Knowledge decision rule, không query MCP như
  ceremony ở mọi turn;
- retrieval dùng progressive disclosure: search cards trước, hydrate tối đa 1–2 exact
  IDs khi thật sự cần;
- substantive work có khả năng tạo reusable conclusion được knowledge review/write;
- agent không mở external Knowledge Store filesystem path hoặc tự chọn filename/path;
- native final assistant response là handoff về QiQi, không fixed result headings hay
  Markdown result artifact;
- `bash scripts/repo-check.sh` trả `PASS`.

## Bước 1: Xác nhận Git root

```bash
pwd
git rev-parse --show-toplevel
git status --short
```

Template phải nằm đúng Git root.

## Bước 2: Xác minh Knowledge MCP user registration

Trong fresh agent session tại repo root, tool inventory phải có:

```text
knowledge_search
knowledge_read
knowledge_write
```

CLI registration có thể kiểm tra:

```bash
codex mcp get knowledge      # nếu dùng Codex
claude mcp get knowledge     # nếu dùng Claude
```

Không tạo `.mcp.json`/project knowledge config riêng chỉ để repo này có tool. Store
phải dùng cùng user-scoped service cài từ `knowledge-template/`.

Knowledge MCP access không nới filesystem boundary: agent dùng output tool, không tự
find/open external store path.

## Bước 3: Merge instruction hiện có

Nếu repo đã có `AGENTS.md` hoặc instruction tương đương:

1. giữ workflow đặc thù của repo;
2. gộp Git-root boundary, `ARCHITECTURE.md`, `docs/VERIFY.md`, QiQi live handoff,
   closed-world TaskPacket boundary, Shared Knowledge lifecycle và cross-repo impact;
3. giữ progressive disclosure `knowledge_search → knowledge_read`;
4. không copy qiqi_delegate runtime/Stop-hook mechanics;
5. không yêu cầu agent ghi result artifact/fixed result schema;
6. không tạo repo-local knowledge store/index;
7. không overwrite toàn bộ product-specific instruction nếu có thể merge an toàn.

## Bước 4: Khảo sát và điền live docs

Thu thập evidence từ manifest/build, source entrypoint, module/package structure,
CI/test/config/runtime và docs hiện hữu.

`ARCHITECTURE.md` mô tả responsibility/module/data flow/boundary bằng live evidence.
`docs/VERIFY.md` mô tả command thực tế, side effect và known verified baseline.
Shared Knowledge Store không thay hai live docs này.

## Bước 5: Knowledge retrieval behavior

Sau khi hiểu concern, agent áp dụng decision rule:

- **MUST search** khi prior durable knowledge có khả năng đổi implementation,
  verification hoặc interpretation;
- **MAY search** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- **SKIP** cho typo/format/comment-only, exact local lookup, report/status-only hoặc
  mechanical task nơi durable context không thể đổi hành động hợp lý.

Khi dùng knowledge:

1. tạo khoảng **3–8 discriminative concepts**, ưu tiên canonical English concepts;
2. thêm original-language/project aliases khi hữu ích;
3. gọi `knowledge_search(keywords, context?, limit?)`;
4. xem returned items là **decision cards** dùng để chọn knowledge, không phải full
   evidence cho material implementation/verification;
5. chọn một hoặc tối đa hai relevant IDs rồi gọi `knowledge_read(ids=[...])`;
6. chỉ full read mới có content, provenance, full routing và revision;
7. `context.repo/domain` chỉ là ranking hint, không permission filter;
8. search cố ý không trả revision; existing knowledge phải full-read trước update;
9. không hydrate top-N chỉ vì search `limit` lớn;
10. nếu knowledge mâu thuẫn current owner source/test, live evidence thắng sau verify.

Search/read failure không được hiểu thành “knowledge không tồn tại”. Task read-only
cũng không tự động skip nếu concern là behavior/contract/decision reusable.

## Bước 6: Structured input từ QiQi

TaskPacket/prompt phải truyền trực tiếp:

- original user request liên quan;
- repo-local objective;
- scope/out-of-scope;
- required context + provenance/certainty;
- constraints;
- acceptance criteria;
- required verification;
- known unknowns.

Execution agent không chia sẻ hidden conversation/reasoning/workspace state hay
sibling state của QiQi. External live fact không có trong TaskPacket không được giả
định là agent đã biết.

Nếu QiQi đã dùng Shared Knowledge fact làm required premise, fact đó phải nằm trong
`required_context`; child không bắt buộc tự query lại premise. Child vẫn dùng
Knowledge MCP để discover/enrich/verify context khác khi repo policy yêu cầu.

Dependency:

```text
repo A native response
→ QiQi reconcile
→ relevant live fact/evidence + provenance
→ repo B required_context
```

Shared Knowledge MCP không phải mailbox cho in-flight result.

## Bước 7: Knowledge finalization

Knowledge review/write là required cho substantive implementation/debugging,
investigation có kết luận, design/decision, contract/behavior change hoặc verified
operational/verification finding có khả năng tạo reusable conclusion.

Trivial/mechanical/report-only work không tạo reusable conclusion được skip write;
không gọi `knowledge_write(entries=[])` như ritual.

Khi review required, sau work + verification và trước native final response:

1. review conclusion reusable/non-trivial/evidence-backed;
2. `knowledge_search` candidate meaning trước create/update để dedupe;
3. nếu có existing candidate phù hợp, `knowledge_read` exact ID trước update;
4. create bằng semantic payload, không filename/path/directory;
5. update bằng exact ID + expected revision từ full `knowledge_read`;
6. giữ full routing/sources/content từ read nếu các field đó không thay đổi, không
   reconstruct từ search card;
7. routing dùng canonical concepts, aliases multilingual khi cần;
8. content tự do về ngôn ngữ, không field `language`;
9. sources/provenance bắt buộc;
10. required review nhưng không candidate → `knowledge_write(entries=[])`;
11. write failure có durable candidate → nêu failure/caveat, không claim persisted.

Knowledge IDs/persistence failure được nêu tự nhiên trong native response khi có;
không có heading bắt buộc.

## Bước 8: Native result và cross-repo impact

Native final assistant response là authoritative semantic handoff về QiQi. Agent
chọn structure phù hợp; không tạo `.qiqi/runs/*.md`, không phụ thuộc terminal
scrollback và không tự định nghĩa result schema.

Khi repo khác còn cần action, response phải nêu đủ fact/change, affected boundary,
evidence, next action nếu rõ và caveat/uncertainty có thể đổi downstream decision.
Persist shared knowledge không thay execution handoff.

## Bước 9: Chạy checker

```bash
bash scripts/repo-check.sh
```

Checker xác nhận Git-root boundary, structured live handoff, progressive Shared
Knowledge lifecycle và native-response ownership. Product verification thật vẫn theo
`docs/VERIFY.md`.

## Bước 10: Fresh-session smoke test

Xác nhận fresh repo agent có thể:

1. thấy đủ `knowledge_search`, `knowledge_read`, `knowledge_write`;
2. áp dụng decision rule sau khi hiểu concern;
3. search trả decision cards mà không trả content/sources/revision/path;
4. hydrate exact một hoặc hai IDs bằng `knowledge_read` khi cần;
5. không mở sibling source/runtime hoặc external knowledge filesystem path;
6. trivial/no-op/exact lookup không tạo knowledge bừa hoặc empty review ceremony;
7. substantive review không candidate dùng `knowledge_write(entries=[])`;
8. verified reusable create để MCP derive path;
9. update dùng revision từ full read và stale revision bị reject;
10. final response giữ material evidence/verification/caveat/cross-repo impact mà
    không phụ thuộc fixed headings.

Chỉ coi repo sẵn sàng khi checker pass và fresh-session Knowledge MCP discovery đã
được xác nhận cho agent family thực sự dùng.
