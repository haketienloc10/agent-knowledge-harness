# Thiết lập Repository con cho QiQi Workspace

Tài liệu này dùng khi đưa `repo-template/` vào một Git repository nằm trong
workspace multi-repo. Shared Knowledge MCP phải được cài ở user/global scope trước
để fresh repo agent thấy `knowledge_read` / `knowledge_write` independent CWD.

## Kết quả cần đạt

- `AGENTS.md` bảo vệ Git-root/sibling boundaries;
- `ARCHITECTURE.md` và `docs/VERIFY.md` có live evidence;
- execution agent nhận original user intent + live upstream context từ structured
  TaskPacket của QiQi, không tự đọc sibling source/runtime state;
- execution agent hiểu task rồi áp dụng Shared Knowledge decision rule, không query
  MCP như ceremony ở mọi turn;
- substantive work có khả năng tạo reusable conclusion được knowledge review/write,
  còn trivial/mechanical/report-only work được phép skip;
- agent không tự mở external Knowledge Store filesystem path và không tự chọn
  knowledge filename/directory;
- native final assistant response là handoff về QiQi; repo policy không ép fixed
  result headings hoặc Markdown result artifact;
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
knowledge_read
knowledge_write
```

CLI registration có thể kiểm tra:

```bash
codex mcp get knowledge      # nếu dùng Codex
claude mcp get knowledge     # nếu dùng Claude
```

Không tạo `.mcp.json`/project knowledge config riêng chỉ để repo này có tool. Store
phải dùng cùng user-scoped service đã được cài từ `knowledge-template/`.

Knowledge MCP access không nới filesystem boundary: agent dùng content tool trả về,
không tự tìm/open external store path.

## Bước 3: Merge instruction hiện có

Nếu repo đã có `AGENTS.md` hoặc instruction tương đương:

1. giữ workflow đặc thù của repo;
2. gộp Git-root boundary, `ARCHITECTURE.md`, `docs/VERIFY.md`, QiQi live handoff,
   closed-world TaskPacket boundary, Shared Knowledge decision rule/lifecycle và
   cross-repo impact semantics;
3. không sao chép qiqi_delegate runtime/Stop-hook mechanics;
4. không yêu cầu agent ghi result artifact hoặc fixed result schema;
5. không tạo repo-local knowledge store/index mới;
6. không ghi đè toàn bộ instruction hiện có nếu có thể merge an toàn.

## Bước 4: Khảo sát và điền live docs

Thu thập evidence từ manifest/build, source entrypoint, module/package structure,
CI/test/config/runtime và docs hiện hữu.

`ARCHITECTURE.md` phải mô tả responsibility/module/data flow/boundary bằng evidence.
`docs/VERIFY.md` phải mô tả command thực tế, side effect và known verified baseline.

Shared Knowledge Store không thay thế hai live docs này.

## Bước 5: Knowledge read behavior

Sau khi hiểu concern của task, agent áp dụng `AGENTS.md` decision rule:

- **MUST read** khi prior durable knowledge có khả năng thay đổi implementation,
  verification hoặc interpretation;
- **MAY read** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- **SKIP read** cho typo/format/comment-only, exact local lookup, report/status-only
  hoặc mechanical task nơi durable context không thể đổi hành động hợp lý.

Khi read:

1. tạo nhiều search terms, ưu tiên canonical English concepts;
2. giữ original-language/project aliases nếu hữu ích;
3. gọi `knowledge_read`;
4. `context.repo/domain` chỉ là ranking hint, không permission filter;
5. relevant knowledge namespace khác vẫn được dùng;
6. nếu knowledge mâu thuẫn current owner source/test, live source/test thắng sau khi
   verify.

Read failure không được hiểu thành “knowledge không tồn tại”. Task read-only cũng
không tự động skip nếu concern là behavior/contract/decision reusable.

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

Execution agent không chia sẻ hidden conversation, hidden reasoning, workspace
control context hay sibling state của QiQi. External live fact không có trong
TaskPacket không được giả định là agent đã biết.

Nếu QiQi đã dùng một Shared Knowledge fact làm required premise cho task, fact đó
phải nằm trong `required_context`; child không bắt buộc tự query lại premise. Child
vẫn query Knowledge MCP độc lập để discover/enrich/verify context khác khi policy
yêu cầu.

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
không gọi `knowledge_write(entries=[])` chỉ như ritual.

Khi review là required, sau work + verification và trước native final response:

1. review conclusion thực sự reusable/non-trivial/evidence-backed;
2. search existing knowledge trước create/update để dedupe;
3. create bằng semantic payload, không filename/path/directory;
4. update bằng exact ID + expected revision từ `knowledge_read`;
5. routing metadata dùng canonical concepts, aliases multilingual khi cần;
6. content tự do về ngôn ngữ, không field `language`;
7. sources/provenance bắt buộc;
8. required review nhưng không candidate → `knowledge_write(entries=[])`;
9. write failure có durable candidate → ghi failure/caveat, không claim persisted.

Knowledge IDs/persistence failure được nêu tự nhiên trong native response khi có;
không có heading bắt buộc.

## Bước 8: Native result và cross-repo impact

Native final assistant response là authoritative semantic handoff về QiQi. Agent
chọn structure phù hợp task; không tạo `.qiqi/runs/*.md`, không phụ thuộc terminal
scrollback và không tự định nghĩa result schema.

Khi repo khác còn cần action, response phải nêu đủ:

- fact/change;
- affected repository/boundary;
- evidence từ repo hiện tại;
- next action nếu rõ;
- caveat/uncertainty có thể đổi downstream decision.

Persist shared knowledge không thay thế execution handoff.

## Bước 9: Chạy checker

```bash
bash scripts/repo-check.sh
```

Checker xác nhận Git-root boundary, structured live handoff, Shared Knowledge
lifecycle và native-response ownership. Nó không chạy product tests; verification
thật vẫn theo `docs/VERIFY.md`.

## Bước 10: Fresh-session smoke test

Xác nhận fresh repo agent có thể:

1. đọc architecture/verification đúng scope;
2. hiểu closed-world TaskPacket và không giả định hidden QiQi context;
3. tự áp dụng decision rule và gọi `knowledge_read` khi durable context có thể ảnh
   hưởng task;
4. nhận knowledge ở namespace khác khi keywords match;
5. không đọc sibling source/runtime state;
6. với trivial/no-op/read-only exact lookup không tạo knowledge bừa và không gọi
   empty review như ceremony;
7. với substantive work nhưng không có durable candidate, required finalization
   review dùng `knowledge_write(entries=[])`;
8. với verified reusable candidate, `knowledge_write` tự derive path và trả
   ID/path/revision mà agent không truyền path;
9. stale revision bị reject;
10. final response giữ material evidence/verification/caveat và cross-repo impact
    mà không phụ thuộc fixed headings.

Chỉ coi repo sẵn sàng khi checker pass và fresh-session Knowledge MCP discovery đã
được xác nhận cho agent family thực sự dùng.
