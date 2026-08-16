# Thiết lập Repository con cho QiQi Workspace

Tài liệu này dùng khi đưa `repo-template/` vào một Git repository nằm trong
workspace multi-repo. Mục tiêu là giúp execution agent hiểu repo, xác minh thay đổi
và handoff kết quả đúng tầng cho QiQi.

Không sửa source sản phẩm trong quá trình setup, trừ khi người dùng mở rộng phạm
vi rõ ràng.

## Kết quả cần đạt

- `AGENTS.md` định tuyến agent và bảo vệ Git-root boundary;
- `AGENTS.md` mô tả rõ input từ QiQi và terminal output về QiQi;
- `ARCHITECTURE.md` mô tả trách nhiệm, module và boundary nội bộ bằng evidence;
- `docs/VERIFY.md` chứa command thực tế và side effect;
- execution agent không tự đọc workspace knowledge, sibling repository hoặc sibling
  result artifact để lấy cross-repo context;
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
   `ARCHITECTURE.md`, đọc `docs/VERIFY.md`, input/output handoff với QiQi,
   repo-local knowledge ownership và final result contract.
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

Không sao chép toàn bộ `SYSTEM_MAP.md` hoặc workspace knowledge vào repo.

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

Execution agent nhận workspace-level context **chỉ từ task prompt của QiQi**.
Prompt có thể chứa relevant workspace knowledge, upstream result và decision đã
xác nhận. Agent không tự đi đọc workspace `knowledge/`, result artifact của repo
khác hoặc source của repository anh em.

Sau khi làm việc trong repo hiện tại, agent handoff về QiQi qua exact result
artifact:

```text
### Repo-local Knowledge
### Cross-repo Impact
```

- `Repo-local Knowledge`: source of truth nội bộ đã cập nhật hoặc kết luận có giá
  trị cho repo hiện tại.
- `Cross-repo Impact`: fact/evidence QiQi cần để điều phối downstream repository
  hoặc workspace.

Khi có cross-repo impact, nêu affected repository/boundary, evidence chính và next
action nếu đã rõ. Agent không tự giao task cho repository anh em.

## Bước 7: Chạy checker

```bash
bash scripts/repo-check.sh
```

Checker chỉ kiểm tra cấu trúc harness, placeholder và handoff/boundary policy. Nó
không chạy test dự án và không thay thế verification trong `docs/VERIFY.md`.

## Bước 8: Fresh-session test

Mở một agent mới tại Git root và xác nhận agent có thể trả lời:

1. Repo sở hữu chức năng gì?
2. Command kiểm tra nhanh và đầy đủ là gì?
3. Agent được phép đọc/sửa phạm vi nào?
4. Workspace/upstream context đến từ đâu?
5. Tri thức repo-local được cập nhật ở đâu?
6. `Cross-repo Impact` phải handoff về QiQi với thông tin nào?
7. Agent có được tự đọc workspace knowledge hoặc result của repo khác không?

Chỉ báo repo sẵn sàng khi checker pass, artifact đã có evidence và instruction
hiện có không còn mâu thuẫn chưa xử lý.
