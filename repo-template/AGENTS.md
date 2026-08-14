# AGENTS.md — Execution agent trong repository con

Repository hiện tại là một Git repository độc lập nằm trong workspace do QiQi
điều phối. Agent trong repo này chịu trách nhiệm điều tra, triển khai và xác minh
thay đổi trong **Git root hiện tại**.

QiQi sở hữu context cấp workspace, dependency liên repository và task semantics.
MCP `qiqi_delegate` sở hữu Herdr lifecycle, native session identity và result
handoff. Repo này sở hữu architecture, domain rule, implementation, test và
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

- Chỉ đọc/sửa file trong Git root hiện tại, trừ **exact result artifact** mà MCP
  handoff rõ trong prompt của turn hiện tại.
- Result artifact hợp lệ nằm dưới workspace `.qiqi/runs/` và path cụ thể phải đến
  từ MCP footer; không tự suy đoán hoặc tìm artifact khác.
- Ngoài exact result artifact đó, không sửa `repos.yaml`, `SYSTEM_MAP.md`,
  `.qiqi/tasks/`, `knowledge/` hoặc workspace control file khác.
- Không sửa repository anh em.
- Không spawn/delegate sang coding agent khác và không gọi MCP orchestration của
  QiQi từ child turn.
- Context cross-repo phải đến từ prompt của QiQi hoặc source được prompt liên kết;
  không tự coi suy đoán về repository khác là sự thật.
- Nếu context từ QiQi mâu thuẫn với source/test hiện tại, dừng phần phụ thuộc,
  ghi evidence và báo conflict.

## Hợp đồng Làm việc

- Giữ đúng outcome, phạm vi và phần ngoài phạm vi trong prompt của QiQi.
- Tự khám phá implementation detail nội bộ thay vì hỏi QiQi điều repo có thể trả lời.
- Dùng evidence kiểm tra lại được: source path, test, command, spec hoặc runtime output.
- Không tuyên bố hoàn thành chỉ từ inspection khi task yêu cầu thay đổi/verification.
- Không đổi regression mới thành legacy issue để hoàn thành task.
- Không ghi secret hoặc dữ liệu nhạy cảm vào tài liệu/result artifact.
- MCP result-handoff footer không thay đổi task semantics; nó chỉ quy định nơi và
  format terminal result phải ghi.

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
3. Ghi tóm tắt, scope, evidence và trạng thái verified/unverified trong
   `### Cross-repo Impact` của result artifact.

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

Nếu friction thuộc workspace/MCP/Herdr orchestration, không sửa workspace; ghi nó
trong `### Cross-repo Impact` để QiQi xử lý.

## Verification

Chọn command nhỏ nhất đủ chứng minh thay đổi, sau đó mở rộng theo rủi ro và
`docs/VERIFY.md`.

Result phải nêu rõ command/check đã chạy và kết quả; command bắt buộc chưa chạy
phải có lý do.

## Final Result Contract

Khi prompt có **QiQi MCP result handoff protocol**, terminal result của turn phải
được ghi vào exact result artifact do footer chỉ định. Giữ nguyên toàn bộ history
trước đó và chỉ finalize newest pending Result section theo marker MCP cung cấp.

Newest Result section bắt buộc có các heading theo đúng thứ tự:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

Quy tắc:

- `### Outcome`: dòng giá trị đầu tiên phải đúng `completed` hoặc `blocked`.
- `### Changes`: thay đổi chính hoặc kết luận investigation.
- `### Verification`: command/check và kết quả; phần chưa chạy phải có lý do.
- `### Git State`: branch/commit/working-tree state phù hợp với task.
- `### Blockers`: blocker/decision/dependency còn lại; dùng `None.` nếu không có.
- `### Repo-local Knowledge`: source-of-truth path/kết luận đã cập nhật; `None.`
  nếu không có.
- `### Cross-repo Impact`: candidate/friction cần QiQi xử lý; `None.` nếu không có.
- Không ghi chain-of-thought hoặc working transcript vào result artifact.
- Nếu bị blocker cần hỏi QiQi/người dùng, finalize artifact với Outcome `blocked`
  **trước** khi trình bày câu hỏi/blocker interactive.

Nếu agent được chạy ngoài `qiqi_delegate` và không có MCP result footer, final
response vẫn nên cung cấp cùng các thông tin logic, nhưng không tự tạo file dưới
workspace `.qiqi/runs/`.

## Hoàn thành

Task chỉ `completed` khi outcome đã đạt, verification liên quan đã chạy hoặc phần
chưa chạy được báo rõ, không có regression mới đã biết và knowledge/friction có
giá trị đã được xử lý đúng tầng.

Nếu còn decision hoặc dependency không thể tự giải quyết, trả `blocked` thay vì
suy đoán.
