# Thiết lập Repository con cho QiQi Workspace

Tài liệu này dùng khi đưa `repo-template/` vào một Git repository nằm trong
workspace multi-repo. Mục tiêu là giúp coding agent hiểu repo, xác minh thay đổi
và trả tri thức đúng tầng cho QiQi.

Không sửa source sản phẩm trong quá trình setup, trừ khi người dùng mở rộng phạm
vi rõ ràng.

## Kết quả cần đạt

- `AGENTS.md` định tuyến agent và bảo vệ Git-root boundary;
- `ARCHITECTURE.md` mô tả trách nhiệm, module và boundary nội bộ bằng evidence;
- `docs/VERIFY.md` chứa command thực tế và side effect;
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
   `ARCHITECTURE.md`, đọc `docs/VERIFY.md`, phân loại local/cross-repo knowledge
   và output contract cho QiQi.
4. Không ghi đè toàn bộ file hiện có.
5. Báo mọi mâu thuẫn không thể hợp nhất an toàn.

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

Không sao chép toàn bộ `SYSTEM_MAP.md` của workspace vào repo.

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

## Bước 6: Chạy checker

```bash
bash scripts/repo-check.sh
```

Checker chỉ kiểm tra cấu trúc harness, placeholder và boundary. Nó không chạy
test dự án và không thay thế verification trong `docs/VERIFY.md`.

## Bước 7: Fresh-session test

Mở một agent mới tại Git root và xác nhận agent có thể trả lời:

1. Repo sở hữu chức năng gì?
2. Command kiểm tra nhanh và đầy đủ là gì?
3. Agent được phép sửa phạm vi nào?
4. Tri thức repo-local được cập nhật ở đâu?
5. Candidate cross-repo phải trả về QiQi theo format nào?

Chỉ báo repo sẵn sàng khi checker pass, artifact đã có evidence và instruction
hiện có không còn mâu thuẫn chưa xử lý.
