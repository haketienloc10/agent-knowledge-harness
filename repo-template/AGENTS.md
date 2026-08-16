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
- Ngoài exact result artifact đó, không đọc/sửa workspace `knowledge/`, result
  artifact của repository/session khác, `repos.yaml`, `SYSTEM_MAP.md`,
  `.qiqi/tasks/` hoặc workspace control file khác.
- Không sửa repository anh em.
- Không spawn/delegate sang coding agent khác và không gọi MCP orchestration của
  QiQi từ child turn.
- Context cross-repo phải đến từ task prompt của QiQi; không tự đọc repository anh
  em hoặc workspace knowledge để bổ sung context.
- Nếu context từ QiQi mâu thuẫn với source/test hiện tại, dừng phần phụ thuộc,
  ghi evidence và báo conflict.

## Handoff với QiQi

QiQi là handoff broker giữa repository hiện tại và phần còn lại của workspace.
Execution agent không handoff trực tiếp cho repository anh em.

### Input từ QiQi

Task prompt của QiQi là nguồn workspace-level duy nhất cho turn hiện tại. Khi cần,
prompt phải chứa trực tiếp:

- outcome, scope và phần ngoài phạm vi;
- decision/contract/knowledge cross-repo đã xác nhận cần cho task;
- upstream result từ repository khác cần dùng;
- evidence hoặc provenance ngắn đủ để hiểu vì sao context đó đáng tin;
- verification hoặc blocker policy có liên quan.

Agent không cần và không được tự mở workspace knowledge hoặc result artifact của
repository khác. Từ context QiQi đã handoff, agent tự khám phá implementation detail
bên trong Git root hiện tại.

### Output về QiQi

Exact result artifact của turn là terminal handoff duy nhất về QiQi.

- `### Repo-local Knowledge`: nêu source-of-truth repo-local đã cập nhật hoặc phát
  hiện có giá trị cho repo này; dùng `None.` nếu không có.
- `### Cross-repo Impact`: nêu thông tin QiQi cần để điều phối repository khác,
  dependency hoặc workspace knowledge; dùng `None.` nếu không có.

Khi `### Cross-repo Impact` có nội dung, nêu ngắn gọn:

- điều gì thay đổi hoặc được phát hiện;
- repository/boundary nào bị ảnh hưởng;
- evidence chính từ repository hiện tại;
- next action nếu đã rõ.

Agent không quyết định trực tiếp công việc của repository anh em. Agent chỉ handoff
fact/evidence cho QiQi để QiQi quyết định downstream task hoặc workspace update.

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

Nếu implementation làm một repo-local source-of-truth document hiện có trở nên
sai hoặc stale, cập nhật document đó trong cùng task hoặc báo blocker/lý do rõ.

## Cross-repo Impact

Khi phát hiện ảnh hưởng từ hai repository trở lên, API/event/schema dùng chung,
upstream/downstream behavior hoặc decision cần QiQi điều phối:

1. Không sửa workspace knowledge.
2. Không sửa repository khác.
3. Ghi fact, affected repository/boundary, evidence và next action nếu rõ vào
   `### Cross-repo Impact` của result artifact.

QiQi chịu trách nhiệm chuyển context đó tới downstream repository hoặc lưu thành
workspace knowledge khi có khả năng dùng lại.

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
- `### Cross-repo Impact`: fact/evidence cần QiQi chuyển tiếp hoặc xử lý ở workspace;
  `None.` nếu không có.
- Không ghi chain-of-thought hoặc working transcript vào result artifact.
- Nếu bị blocker cần hỏi QiQi/người dùng, finalize artifact với Outcome `blocked`
  **trước** khi trình bày câu hỏi/blocker interactive.

Nếu agent được chạy ngoài `qiqi_delegate` và không có MCP result footer, final
response vẫn nên cung cấp cùng các thông tin logic, nhưng không tự tạo file dưới
workspace `.qiqi/runs/`.

## Hoàn thành

Task chỉ `completed` khi outcome đã đạt, verification liên quan đã chạy hoặc phần
chưa chạy được báo rõ, không có regression mới đã biết, repo-local knowledge cần
thiết đã cập nhật và cross-repo impact cần QiQi biết đã được handoff trong result.

Nếu còn decision hoặc dependency không thể tự giải quyết, trả `blocked` thay vì
suy đoán.
