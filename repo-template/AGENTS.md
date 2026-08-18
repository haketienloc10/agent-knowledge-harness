# AGENTS.md — Execution agent trong repository con

Repository hiện tại là một Git repository độc lập nằm trong workspace do QiQi
điều phối. Agent trong repo này chịu trách nhiệm điều tra, triển khai và xác minh
thay đổi trong **Git root hiện tại**.

QiQi sở hữu context cấp workspace, dependency liên repository và task semantics.
MCP `qiqi_delegate` sở hữu execution lifecycle, native session và **result-handoff
protocol**. Repo này sở hữu architecture, domain rule, implementation, test và
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

- Chỉ đọc/sửa file trong Git root hiện tại, ngoại trừ exact result artifact mà MCP
  chỉ định cho turn đang chạy.
- Không tự suy đoán, tìm hoặc mở result artifact khác.
- Không đọc/sửa workspace `repos.yaml`, `SYSTEM_MAP.md`, `.qiqi/tasks/` hoặc
  workspace control file khác.
- Không đọc/sửa repository anh em.
- Không spawn/delegate sang coding agent khác và không gọi MCP orchestration của
  QiQi từ child turn.
- Upstream live result phải đến từ task prompt của QiQi; không tự đi tìm result
  hoặc source ở repository khác.
- Nếu context từ QiQi mâu thuẫn với source/test hiện tại, dừng phần phụ thuộc,
  ghi evidence và báo conflict.

## Handoff với QiQi

QiQi là handoff broker giữa repository hiện tại và phần còn lại của workspace.
Execution agent không handoff trực tiếp cho repository anh em.

### Input từ QiQi

Task prompt của QiQi là nguồn workspace-level và upstream live-result context cho
turn hiện tại. Khi cần, prompt phải chứa trực tiếp context đã được QiQi reconcile,
ví dụ:

- outcome, scope và phần ngoài phạm vi;
- decision/contract/evidence cross-repo cần cho task;
- upstream result từ repository khác cần dùng;
- evidence hoặc provenance ngắn khi cần để kiểm chứng context;
- verification hoặc blocker policy có liên quan.

Agent không tự mở result/source của repository khác để bổ sung live context. Từ
handoff của QiQi, agent tự khám phá implementation detail bên trong Git root hiện
tại.

### Output về QiQi

Khi chạy qua `qiqi_delegate`, **MCP footer là source of truth duy nhất cho cơ chế
result handoff**: exact artifact, pending marker/history, headings và thứ tự,
Outcome vocabulary, cùng quy tắc finalization. Không lặp hoặc tự định nghĩa lại
protocol đó trong repo policy.

Exact result artifact dưới workspace `.qiqi/runs/` chỉ được parent execution
agent nhận task trực tiếp từ QiQi/MCP cập nhật hoặc finalize. Subagent không được
sửa result artifact này.

`### Cross-repo Impact` là outbound execution handoff cho QiQi khi repo-local work
phát hiện impact cần repository khác hoặc workspace xử lý. Khi có Cross-repo
Impact, nêu đủ:

- điều gì thay đổi hoặc được phát hiện;
- repository/boundary nào bị ảnh hưởng;
- evidence chính từ repository hiện tại;
- next action nếu đã rõ.

Agent không quyết định trực tiếp công việc của repository anh em. Agent chỉ handoff
fact/evidence cho QiQi để QiQi quyết định downstream task hoặc workspace action.

## Hợp đồng Làm việc

- Giữ đúng outcome, phạm vi và phần ngoài phạm vi trong prompt của QiQi.
- Tự khám phá implementation detail nội bộ thay vì hỏi QiQi điều repo có thể trả lời.
- Dùng evidence kiểm tra lại được: source path, test, command, spec hoặc runtime output.
- Không tuyên bố hoàn thành chỉ từ inspection khi task yêu cầu thay đổi/verification.
- Không đổi regression mới thành legacy issue để hoàn thành task.
- Không ghi secret hoặc dữ liệu nhạy cảm vào tài liệu/result artifact.

## Cross-repo Impact

Khi phát hiện ảnh hưởng từ hai repository trở lên, API/event/schema dùng chung,
upstream/downstream behavior hoặc decision cần QiQi điều phối:

1. Không sửa repository khác.
2. Handoff fact, affected repository/boundary, evidence và next action nếu rõ cho
   QiQi qua result của turn hiện tại.

QiQi chịu trách nhiệm chuyển live context đó tới downstream repository hoặc xử lý
workspace action cần thiết.

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

Nếu friction thuộc workspace/MCP/Herdr orchestration, không sửa workspace; handoff
nó cho QiQi như Cross-repo Impact.

## Verification

Chọn command nhỏ nhất đủ chứng minh thay đổi, sau đó mở rộng theo rủi ro và
`docs/VERIFY.md`.

Mọi verification claim phải nêu command/check thực tế và kết quả. Command bắt buộc
chưa chạy phải có lý do rõ; không biến suy đoán thành evidence.

## Hoàn thành

Task chỉ completed khi outcome đã đạt, verification liên quan đã chạy hoặc phần
chưa chạy được báo rõ, không có regression mới đã biết, và cross-repo impact cần
QiQi biết đã được handoff.

Nếu còn decision hoặc dependency không thể tự giải quyết, task chưa completed;
tuân theo MCP result-handoff protocol của turn để ghi terminal state và blocker.
