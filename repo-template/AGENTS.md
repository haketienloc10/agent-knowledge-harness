# AGENTS.md — Execution agent trong repository con

Repository hiện tại là một Git repository độc lập nằm trong workspace do QiQi
điều phối. Agent trong repo này chịu trách nhiệm điều tra, triển khai và xác minh
thay đổi **chỉ trong Git root hiện tại**.

QiQi sở hữu context cấp workspace, quan hệ liên repository và delegation
lifecycle. Repo này sở hữu architecture, domain rule, implementation, test và
verification nội bộ.

## Bắt đầu

Với task chỉ đọc, chỉ mở nguồn cần cho câu hỏi.

Trước code task không tầm thường:

1. Xác nhận thư mục hiện tại là Git root bằng `git rev-parse --show-toplevel`.
2. Đọc `ARCHITECTURE.md` để hiểu responsibility/module/boundary.
3. Đọc `docs/VERIFY.md` để biết verification command và side effect.
4. Đọc artifact khác chỉ khi concern của task yêu cầu.

Không quét toàn bộ repository hoặc toàn bộ `docs/` khi chưa cần.

## Định tuyến theo concern

| Concern | Source of truth |
|---|---|
| Responsibility, module, dependency và data flow nội bộ | `ARCHITECTURE.md` |
| Bootstrap, test, lint, build và guardrail | `docs/VERIFY.md` |
| Domain rule hoặc invariant | `docs/domain/` nếu tồn tại |
| User/API behavior hoặc acceptance criteria | `docs/specs/` nếu tồn tại |
| Quyết định kỹ thuật lâu bền | `docs/decisions/` nếu tồn tại |
| Security boundary hoặc dữ liệu nhạy cảm | `docs/SECURITY.md` nếu tồn tại |

Artifact optional không tồn tại thì tiếp tục bằng source, test và tài liệu hiện
có. Không tạo file rỗng chỉ để hoàn thiện cấu trúc.

## Ranh giới Workspace

- Chỉ đọc và sửa file trong Git root hiện tại, trừ khi prompt cho phép rõ phạm vi
  khác.
- Không sửa `repos.yaml`, `SYSTEM_MAP.md`, `.qiqi/tasks/` hoặc `knowledge/` ở
  workspace root.
- Không sửa repository anh em.
- Không spawn/delegate sang coding agent khác và không gọi MCP orchestration của
  QiQi từ child run.
- Context cross-repo phải đến từ prompt của QiQi hoặc source được prompt liên
  kết; không tự coi suy đoán về repository khác là sự thật.
- Nếu context từ QiQi mâu thuẫn với source/test hiện tại, dừng phần phụ thuộc,
  ghi evidence và báo conflict.

## Hợp đồng Làm việc

- Giữ đúng outcome, phạm vi và phần ngoài phạm vi trong prompt.
- Tự khám phá chi tiết implementation nội bộ thay vì hỏi QiQi những điều repo có
  thể trả lời.
- Dùng evidence kiểm tra lại được: source path, test, command, spec hoặc runtime
  output.
- Không tuyên bố hoàn thành chỉ từ inspection.
- Không đổi regression mới thành legacy issue để hoàn thành task.
- Không ghi secret hoặc dữ liệu nhạy cảm vào tài liệu/báo cáo.

## Tri thức Repo-local

Khi task xác nhận tri thức có khả năng dùng lại và chỉ thuộc repository này, cập
nhật source of truth phù hợp trong cùng thay đổi:

- responsibility/module/data flow → `ARCHITECTURE.md`;
- verification path ổn định → `docs/VERIFY.md`;
- domain rule → `docs/domain/` nếu repo dùng artifact này;
- behavior/contract do repo sở hữu → `docs/specs/` nếu phù hợp;
- quyết định kỹ thuật lâu bền → `docs/decisions/` nếu phù hợp.

Không tạo tài liệu để sao chép điều đã rõ từ source/test. Phát hiện chưa đủ
evidence không được ghi như sự thật.

## Ứng viên Tri thức Cross-repo

Khi phát hiện ảnh hưởng từ hai repository trở lên, API/event/schema dùng chung
hoặc decision cần QiQi điều phối:

1. Không sửa workspace knowledge.
2. Không sửa repository khác.
3. Trả tóm tắt, scope, evidence và trạng thái verified/unverified trong
   `cross_repo_impact` của final result.

QiQi chịu trách nhiệm promote hoặc giữ candidate ở workspace level.

## Ghi nhận Friction

Friction là vấn đề đã quan sát khiến agent đổi planned approach, lặp bước có chi
phí hoặc giảm độ tin cậy của feedback loop.

Khi có friction đáng kể thuộc repository/tooling/instruction của task, tạo:

`docs/friction/<yyyy-mm-dd>-<short-name>.md`

Mỗi file ghi đúng một friction:

```md
# <Mô tả cụ thể vấn đề>

- Impact:
- Evidence:
```

Chỉ ghi nhận friction có evidence. Không có friction đáng kể thì không tạo file.
Nếu friction thuộc workspace/orchestration, không sửa workspace; đưa nó vào
`cross_repo_impact` để QiQi xử lý.

## Verification

Chọn command nhỏ nhất đủ chứng minh thay đổi, sau đó mở rộng theo rủi ro và
`docs/VERIFY.md`.

Final result phải nêu rõ command/check đã chạy và kết quả; command bắt buộc chưa
chạy phải có lý do.

## Final Result Contract

Caller có thể ép output bằng JSON Schema. Dù format cụ thể là JSON hay text,
final result phải cung cấp đủ các field logic sau:

- `outcome`: `completed` hoặc `blocked`;
- `changes`: thay đổi chính hoặc kết luận điều tra;
- `verification`: command/check và kết quả;
- `git_state`: branch/commit/working-tree state phù hợp;
- `blockers`: blocker/decision còn lại, hoặc danh sách rỗng;
- `repo_local_knowledge`: path/kết luận repo-local đã cập nhật, hoặc danh sách
  rỗng;
- `cross_repo_impact`: cross-repo candidate/friction cần QiQi xử lý, hoặc danh
  sách rỗng.

Không kể lại từng tool call hoặc working transcript.

## Hoàn thành

Task chỉ `completed` khi outcome đã đạt, verification liên quan đã chạy hoặc phần
chưa chạy được báo rõ, không có regression mới đã biết và knowledge/friction có
giá trị đã được xử lý đúng tầng. Nếu còn decision hoặc dependency không thể tự
giải quyết, trả `blocked` thay vì suy đoán.
