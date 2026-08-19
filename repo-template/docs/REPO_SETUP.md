# Thiết lập Repository con cho QiQi Workspace

Tài liệu này dùng khi đưa `repo-template/` vào một Git repository nằm trong
workspace multi-repo. Shared Knowledge MCP phải được cài ở user/global scope trước
để fresh repo agent thấy `knowledge_read` / `knowledge_write` independent CWD.

## Kết quả cần đạt

- `AGENTS.md` bảo vệ Git-root/sibling boundaries;
- `ARCHITECTURE.md` và `docs/VERIFY.md` có live evidence;
- execution agent nhận live upstream context từ QiQi, không tự đọc sibling
  source/result;
- execution agent query Shared Knowledge MCP sau khi hiểu task;
- execution agent review/write durable knowledge trước terminal result;
- agent không tự mở external Knowledge Store filesystem path và không tự chọn
  knowledge filename/directory;
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
   Shared Knowledge lifecycle và Cross-repo Impact semantics;
3. không sao chép qiqi_delegate result mechanics;
4. không tạo repo-local knowledge store/index mới;
5. không ghi đè toàn bộ instruction hiện có nếu có thể merge an toàn.

## Bước 4: Khảo sát và điền live docs

Thu thập evidence từ manifest/build, source entrypoint, module/package structure,
CI/test/config/runtime và docs hiện hữu.

`ARCHITECTURE.md` phải mô tả responsibility/module/data flow/boundary bằng evidence.
`docs/VERIFY.md` phải mô tả command thực tế, side effect và known verified baseline.

Shared Knowledge Store không thay thế hai live docs này.

## Bước 5: Knowledge read behavior

Sau khi hiểu concern của task:

1. tạo nhiều search terms, ưu tiên canonical English concepts;
2. giữ original-language/project aliases nếu hữu ích;
3. gọi `knowledge_read`;
4. `context.repo/domain` chỉ là ranking hint, không permission filter;
5. relevant knowledge namespace khác vẫn được dùng;
6. nếu knowledge mâu thuẫn current owner source/test, live source/test thắng sau khi
   verify.

Read failure không được hiểu thành “knowledge không tồn tại”.

## Bước 6: Live handoff với QiQi

Task prompt của QiQi là nguồn live workspace/upstream context. Repo agent không tự
đọc sibling source/result.

Dependency vẫn là:

```text
repo A result
→ QiQi reconcile
→ inline relevant live fact/evidence
→ repo B prompt
```

Shared Knowledge MCP chỉ cung cấp durable reusable context; nó không phải mailbox
cho in-flight result.

## Bước 7: Knowledge finalization

Sau work + verification và trước terminal result:

1. review conclusion thực sự reusable/non-trivial/evidence-backed;
2. search existing knowledge khi có thể là update;
3. create bằng semantic payload, không filename/path/directory;
4. update bằng exact ID + expected revision từ `knowledge_read`;
5. routing metadata dùng canonical concepts, aliases multilingual khi cần;
6. content tự do về ngôn ngữ, không field `language`;
7. sources/provenance bắt buộc;
8. không candidate → `knowledge_write(entries=[])`;
9. write failure có durable candidate → ghi failure/caveat, không claim persisted.

Current qiqi_delegate result contract vẫn có `### Repo-local Knowledge`. Đây là
legacy label: ghi Knowledge MCP IDs create/update, `None`, hoặc persistence failure;
không tạo nghĩa vụ sửa knowledge docs trong Git repo này.

## Bước 8: Cross-repo Impact

Nếu repo khác còn cần action, vẫn ghi `### Cross-repo Impact` với:

- fact/change;
- affected repository/boundary;
- evidence từ repo hiện tại;
- next action nếu rõ.

Persist shared knowledge không thay thế execution handoff.

## Bước 9: Chạy checker

```bash
bash scripts/repo-check.sh
```

Checker xác nhận Git-root boundary, QiQi live handoff, Shared Knowledge lifecycle và
MCP result ownership. Nó không chạy product tests; verification thật vẫn theo
`docs/VERIFY.md`.

## Bước 10: Fresh-session smoke test

Xác nhận fresh repo agent có thể:

1. đọc architecture/verification đúng scope;
2. gọi `knowledge_read` tại repo root;
3. nhận knowledge ở namespace khác khi keywords match;
4. không đọc sibling source/result;
5. với task no-op/read-only không tạo knowledge bừa và finalization dùng empty
   review khi phù hợp;
6. với verified reusable test candidate, `knowledge_write` tự derive path và trả
   ID/path/revision mà agent không truyền path;
7. stale revision bị reject;
8. Cross-repo Impact vẫn về QiQi khi downstream repo cần work.

Chỉ coi repo sẵn sàng khi checker pass và fresh-session Knowledge MCP discovery đã
được xác nhận cho agent family thực sự dùng.
