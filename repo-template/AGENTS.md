# AGENTS.md — Coding agent trong repository con

Repository hiện tại là một Git repository độc lập nằm trong workspace do QiQi
điều phối. Agent trong repo này chịu trách nhiệm điều tra, triển khai và xác minh
thay đổi **chỉ trong Git root hiện tại**.

QiQi sở hữu context cấp workspace, quan hệ liên repository, task continuity và
phiên Herdr. Repo này sở hữu kiến trúc, domain rule, implementation, test và
verification nội bộ.

## Bắt đầu

Với task chỉ đọc, giải thích hoặc báo cáo, chỉ mở nguồn cần cho câu hỏi.

Trước code task không tầm thường:

1. Xác nhận thư mục hiện tại là Git root bằng `git rev-parse --show-toplevel`.
2. Đọc `ARCHITECTURE.md` để hiểu trách nhiệm, module và boundary của repo.
3. Đọc `docs/VERIFY.md` để biết command kiểm tra và side effect.
4. Đọc artifact khác chỉ khi concern của task yêu cầu.

Không quét toàn bộ repository hoặc toàn bộ `docs/` khi chưa cần.

## Định tuyến theo concern

| Concern | Source of truth |
|---|---|
| Trách nhiệm, module, dependency và data flow nội bộ | `ARCHITECTURE.md` |
| Bootstrap, test, lint, build và guardrail | `docs/VERIFY.md` |
| Domain rule hoặc invariant | `docs/domain/` nếu tồn tại |
| User behavior, API behavior hoặc acceptance criteria | `docs/specs/` nếu tồn tại |
| Quyết định kỹ thuật lâu bền | `docs/decisions/` nếu tồn tại |
| Security boundary hoặc dữ liệu nhạy cảm | `docs/SECURITY.md` nếu tồn tại |
| Workflow bổ sung của repository | Artifact hiện có được `AGENTS.md` liên kết |

Artifact optional không tồn tại thì tiếp tục bằng source, test và tài liệu hiện
có. Không tạo file rỗng chỉ để hoàn thiện cấu trúc.

## Ranh giới Workspace

- Chỉ đọc và sửa file trong Git root hiện tại, trừ khi prompt của QiQi cho phép
  rõ một phạm vi khác.
- Không sửa `repos.yaml`, `SYSTEM_MAP.md`, `.qiqi/tasks/` hoặc `knowledge/` ở
  workspace root.
- Không sửa repository anh em, kể cả khi phát hiện consumer hoặc producer cần
  thay đổi.
- Không tự điều khiển Herdr, tạo agent khác hoặc mở phiên coding-agent mới.
- Context cross-repo phải đến từ prompt của QiQi hoặc source được prompt liên
  kết. Không tự coi suy đoán về repository khác là sự thật.
- Nếu context từ QiQi mâu thuẫn với source hoặc test hiện tại, dừng phần phụ
  thuộc, ghi evidence và báo conflict; không tự thiết kế lại contract cross-repo.

## Hợp đồng Làm việc

- Giữ đúng mục tiêu, phạm vi và phần ngoài phạm vi trong prompt.
- Tự khám phá chi tiết triển khai nội bộ thay vì hỏi QiQi những điều repository
  có thể trả lời.
- Dùng evidence có thể kiểm tra lại được: source path, test, command, spec hoặc
  runtime output.
- Không tuyên bố hoàn thành chỉ từ inspection.
- Không đổi regression mới thành legacy issue hoặc technical debt để hoàn thành
  task.
- Không ghi secret hoặc dữ liệu nhạy cảm vào tài liệu hay báo cáo.

## Tri thức Repo-local

Khi task phát hiện hoặc xác nhận tri thức có khả năng dùng lại và tri thức đó
thuộc riêng repository này, cập nhật source of truth phù hợp trong cùng thay đổi:

- trách nhiệm, module, dependency hoặc data flow → `ARCHITECTURE.md`;
- command hoặc verification path ổn định → `docs/VERIFY.md`;
- domain rule → `docs/domain/` nếu repository dùng artifact này;
- behavior hoặc contract do repo sở hữu → `docs/specs/` nếu phù hợp;
- quyết định kỹ thuật và trade-off lâu bền → `docs/decisions/` nếu phù hợp.

Không tạo tài liệu để sao chép điều đã rõ từ source hoặc test. Phát hiện chưa đủ
evidence không được ghi vào source of truth như sự thật.

## Ứng viên Tri thức Cross-repo

Khi phát hiện ảnh hưởng từ hai repository trở lên, API/event/schema dùng chung,
hoặc quyết định cần QiQi điều phối:

1. Không sửa knowledge tại workspace.
2. Không sửa repository khác.
3. Ghi ứng viên trong báo cáo cuối với loại, tóm tắt, phạm vi, evidence và target
   workspace được đề xuất.
4. Nêu rõ trạng thái `verified` hoặc `unverified`.

QiQi chịu trách nhiệm kiểm tra candidate, cập nhật task context và tạo proposal
trong workspace khi cần.

## Verification

Chọn command nhỏ nhất đủ chứng minh thay đổi, sau đó mở rộng theo rủi ro và
`docs/VERIFY.md`.

Báo rõ:

- command đã chạy và kết quả;
- command bắt buộc chưa chạy cùng lý do;
- failure có trước hay do thay đổi hiện tại;
- side effect hoặc prerequisite liên quan.

## Báo cáo Cuối

Báo cáo cuối phải có các mục sau; giữ ngắn nhưng không bỏ mục:

```md
## Kết quả

## Thay đổi

## Verification

## Git state

## Repo-local knowledge
- Đã cập nhật: <đường dẫn và nội dung chính>
- Hoặc: Không có.

## Cross-repo knowledge candidate
- Type: system | contract | decision
- Status: verified | unverified
- Summary:
- Scope:
- Evidence:
- Suggested workspace target:
- Hoặc: Không có.

## Blocker hoặc bước tiếp theo
```

Không kể lại từng tool call. Nếu có nhiều candidate, lặp lại khối field cho từng
candidate.

## Hoàn thành

Task chỉ hoàn thành khi mục tiêu đã đạt, verification liên quan đã chạy hoặc
phần chưa chạy được báo rõ, không có regression mới đã biết, tri thức repo-local
đã được cập nhật khi cần và candidate cross-repo đã được trả về QiQi.