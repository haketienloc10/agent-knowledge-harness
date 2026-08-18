# Thiết lập Repository con cho QiQi Workspace

Tài liệu này dùng khi đưa `repo-template/` vào một Git repository nằm trong
workspace multi-repo. Mục tiêu là giúp execution agent hiểu repo, xác minh thay đổi
và handoff đúng semantics cho QiQi mà không sao chép protocol do MCP sở hữu.

Không sửa source sản phẩm trong quá trình setup, trừ khi người dùng mở rộng phạm
vi rõ ràng.

## Kết quả cần đạt

- `AGENTS.md` định tuyến agent và bảo vệ Git-root boundary;
- `AGENTS.md` mô tả input từ QiQi và semantics cần handoff ngược về QiQi;
- MCP footer vẫn là source of truth cho result artifact và result format;
- `ARCHITECTURE.md` mô tả trách nhiệm, module và boundary nội bộ bằng evidence;
- `docs/VERIFY.md` chứa command thực tế và side effect;
- execution agent không tự đọc sibling repository hoặc sibling result artifact để
  lấy live cross-repo evidence;
- `bash scripts/repo-check.sh` trả `PASS`;
- không còn placeholder dạng `{{...}}` trong artifact bắt buộc.

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
   `ARCHITECTURE.md`, đọc `docs/VERIFY.md`, input từ QiQi và Cross-repo Impact
   semantics.
4. Không sao chép result-handoff mechanics từ MCP footer vào repo instruction.
5. Không ghi đè toàn bộ file hiện có.
6. Báo mọi mâu thuẫn không thể hợp nhất an toàn.

## Bước 3: Khảo sát repository

Thu thập bằng chứng từ:

- manifest và build file;
- source entrypoint;
- module/package structure;
- CI configuration;
- test command;
- config runtime và deployment;
- tài liệu hiện hữu.

Không đoán trách nhiệm, dependency, command hoặc contract chỉ từ tên thư mục.

## Bước 4: Điền `ARCHITECTURE.md`

Hoàn thành tối thiểu:

- repo sở hữu và không sở hữu chức năng gì;
- entrypoint;
- module chính và dependency nội bộ;
- data flow chính;
- external boundary mà repo trực tiếp dùng;
- data ownership và constraint quan trọng;
- source path hoặc command làm evidence.

Không sao chép toàn bộ `SYSTEM_MAP.md` vào repo.

## Bước 5: Điền `docs/VERIFY.md`

Xác nhận từ CI, manifest hoặc lần chạy thực tế:

- prerequisites;
- bootstrap command;
- focused check;
- test liên quan;
- full verification hoặc build;
- side effect và thời gian chạy;
- baseline failure đã được chứng minh nếu có.

Command chưa chạy phải được ghi rõ là chưa xác minh; không biến command dự đoán
thành source of truth.

## Bước 6: Hiểu handoff với QiQi

Execution agent nhận workspace-level và upstream live-result context từ task prompt
của QiQi. Agent không tự đi đọc result artifact hoặc source của repository anh em.

Khi chạy qua `qiqi_delegate`, MCP footer cung cấp exact result artifact và format
cần ghi. Repo instruction không cần định nghĩa lại headings, thứ tự, marker,
history preservation hoặc Outcome vocabulary.

`### Cross-repo Impact` là outbound execution handoff khi work hiện tại tạo ra
impact cần QiQi điều phối. Khi có Cross-repo Impact, nêu affected
repository/boundary, evidence chính và next action nếu đã rõ. Agent không tự giao
task cho repository anh em.

## Bước 7: Chạy checker

```bash
bash scripts/repo-check.sh
```

Checker chỉ kiểm tra cấu trúc harness, placeholder, ownership và handoff semantics.
Nó không kiểm tra lại MCP result format, không chạy test dự án và không thay thế
verification trong `docs/VERIFY.md`.

## Bước 8: Fresh-session test

Mở một agent mới tại Git root và xác nhận agent có thể trả lời:

1. Repo sở hữu chức năng gì?
2. Command kiểm tra nhanh và đầy đủ là gì?
3. Agent được phép đọc/sửa phạm vi nào?
4. Workspace/upstream live-result context đến từ đâu?
5. Khi nào phải handoff Cross-repo Impact và cần mang theo evidence gì?
6. Agent có được tự đọc result hoặc source của repo khác không?
7. Thành phần nào sở hữu exact result format? — MCP footer, không phải repo policy.

Chỉ báo repo sẵn sàng khi checker pass, artifact đã có evidence và instruction
hiện có không còn mâu thuẫn chưa xử lý.
