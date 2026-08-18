# Thiết lập Repository con cho QiQi Workspace

Tài liệu này dùng khi đưa `repo-template/` vào một Git repository nằm trong
workspace multi-repo. Mục tiêu là giúp execution agent hiểu repo, xác minh thay đổi,
dùng Shared Knowledge MCP và handoff đúng semantics cho QiQi mà không sao chép
protocol do MCP sở hữu.

Không sửa source sản phẩm trong quá trình setup, trừ khi người dùng mở rộng phạm
vi rõ ràng.

## Kết quả cần đạt

- `AGENTS.md` định tuyến agent và bảo vệ Git-root boundary;
- `AGENTS.md` yêu cầu `knowledge_read` đầu work turn và `knowledge_write` trước
  finalize;
- Shared Knowledge MCP đã được đăng ký ở **user scope** của agent CLI nên child
  session thấy được dù CWD là Git root hiện tại;
- MCP footer vẫn là source of truth cho result artifact và result format;
- `ARCHITECTURE.md` mô tả trách nhiệm, module và boundary nội bộ bằng evidence;
- `docs/VERIFY.md` chứa command thực tế và side effect;
- execution agent không tự đọc sibling repository hoặc sibling result artifact để
  lấy live cross-repo evidence;
- `bash scripts/repo-check.sh` trả `PASS`;
- không còn placeholder dạng `{{...}}` trong artifact bắt buộc.

Shared knowledge store/runtime được setup ở workspace theo
`docs/KNOWLEDGE_STORE.md`; repo template không chứa knowledge store riêng.

## Bước 1: Xác nhận Git root

```bash
pwd
git rev-parse --show-toplevel
git status --short
```

Chỉ tiếp tục khi thư mục cài template đúng bằng Git root. Không chạy Git ở
workspace root để suy luận trạng thái repository này.

## Bước 2: Kiểm tra instruction hiện có

Nếu repo đã có `AGENTS.md` hoặc instruction tương đương:

1. Đọc và phân loại các quy tắc hiện có.
2. Giữ workflow đặc thù của repo.
3. Gộp các nguyên tắc tối thiểu từ template: Git-root boundary, đọc
   `ARCHITECTURE.md`, đọc `docs/VERIFY.md`, Shared Knowledge lifecycle, input từ
   QiQi và Cross-repo Impact semantics.
4. Không thêm repo-local knowledge store hoặc yêu cầu agent tự chọn knowledge
   path/filename/directory.
5. Không sao chép result-handoff mechanics từ MCP footer vào repo instruction.
6. Không ghi đè toàn bộ file hiện có.
7. Báo mọi mâu thuẫn không thể hợp nhất an toàn.

## Bước 3: Khảo sát repository

Thu thập bằng chứng từ manifest/build, source entrypoint, module/package structure,
CI, tests, runtime config và tài liệu hiện hữu. Không đoán responsibility,
dependency, command hoặc contract chỉ từ tên thư mục.

## Bước 4: Điền `ARCHITECTURE.md`

Hoàn thành tối thiểu repository responsibility, entrypoint, module/dependency,
internal flow, external boundary, data ownership, constraints và evidence. Không
sao chép toàn bộ `SYSTEM_MAP.md` vào repo.

## Bước 5: Điền `docs/VERIFY.md`

Xác nhận từ CI, manifest hoặc lần chạy thực tế: prerequisites, bootstrap, focused
check, related tests, full verification/build, side effects và baseline failures đã
được chứng minh. Command chưa chạy phải ghi rõ là chưa xác minh.

## Bước 6: Xác nhận Shared Knowledge MCP

Knowledge MCP được cấu hình ngoài repo ở user scope. Từ child agent CLI/session,
xác nhận tool `knowledge_read` và `knowledge_write` khả dụng.

Work turn chuẩn:

```text
understand task
→ generate multiple task-relevant search terms
→ knowledge_read
→ repo-local investigation / implementation / verification
→ review reusable verified knowledge
→ knowledge_write (entries=[] nếu không có update)
→ terminal result
```

Rules quan trọng:

- shared knowledge có thể thuộc repo/module/domain khác;
- `context.repo`/`context.domain` chỉ là ranking hint;
- agent không tự mở filesystem knowledge root;
- create/update không truyền storage filename/path/directory;
- routing metadata dùng canonical terminology; aliases có thể đa ngôn ngữ;
- content dùng ngôn ngữ tùy ý và không có field `language`;
- update dùng exact `id` + `expected_revision` từ read;
- live owner-repo source/test thắng shared knowledge stale;
- persistence failure không được báo như đã persist.

## Bước 7: Hiểu handoff với QiQi

Execution agent nhận workspace-level và upstream **live-result** context từ task
prompt của QiQi. Agent không tự đi đọc result artifact hoặc source của repository
anh em. Durable shared knowledge thì agent tự query qua Knowledge MCP.

Khi chạy qua `qiqi_delegate`, MCP footer cung cấp exact result artifact và format
cần ghi. `### Repo-local Knowledge` hiện chỉ là compatibility heading: ghi `None`
nếu shared knowledge review không có update hoặc ghi shared knowledge ID/revision đã
persist; không khôi phục repo-local knowledge lifecycle cũ.

`### Cross-repo Impact` là outbound execution handoff khi work hiện tại tạo ra
impact cần QiQi điều phối. Nó không phải knowledge transport.

## Bước 8: Chạy checker

```bash
bash scripts/repo-check.sh
```

Checker chỉ kiểm tra cấu trúc harness, Git-root boundary, Shared Knowledge policy
và handoff semantics. Nó không chạy test dự án và không thay thế verification trong
`docs/VERIFY.md`.

## Bước 9: Fresh-session test

Mở agent mới tại Git root và xác nhận:

1. `knowledge_read` khả dụng dù session chạy ở repo root.
2. Query bằng canonical English + alias phù hợp trả shared knowledge liên quan.
3. Agent hiểu repo responsibility và verification commands.
4. Agent không được tự đọc sibling result/source.
5. `knowledge_write(entries=[])` hoạt động cho turn không tạo knowledge.
6. Create knowledge không cần/không cho agent chọn storage path.
7. `### Cross-repo Impact` mang live execution impact, không dùng làm knowledge transport.
8. Exact result format thuộc `qiqi_delegate` MCP footer.

Chỉ báo repo sẵn sàng khi checker pass, user-scoped Knowledge MCP được child
session nhìn thấy và instruction hiện có không còn mâu thuẫn chưa xử lý.
