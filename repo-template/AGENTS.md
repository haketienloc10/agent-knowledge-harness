# AGENTS.md — Execution agent trong repository con

Repository hiện tại là một Git repository độc lập nằm trong workspace do QiQi
điều phối. Agent trong repo này chịu trách nhiệm điều tra, triển khai và xác minh
thay đổi trong **Git root hiện tại**.

QiQi sở hữu context cấp workspace, dependency liên repository và task semantics.
MCP `qiqi_delegate` sở hữu execution lifecycle, native session và **result-handoff
protocol**. Repo này sở hữu architecture, implementation, test và verification
nội bộ. Durable reusable knowledge nằm trong Shared Knowledge Store độc lập và chỉ
được truy cập qua user-scoped **Knowledge MCP**.

## Bắt đầu

Với task chỉ đọc, chỉ mở nguồn cần cho câu hỏi.

Trước code task không tầm thường:

1. Xác nhận thư mục hiện tại là Git root bằng `git rev-parse --show-toplevel`.
2. Đọc `ARCHITECTURE.md` để hiểu responsibility/module/boundary.
3. Đọc `docs/VERIFY.md` để biết verification command và side effect.
4. Hiểu concern của task, tạo nhiều search terms có giá trị phân biệt rồi gọi
   `knowledge_read`. Dùng canonical English concepts và original-language/project
   aliases khi hữu ích.
5. Đọc artifact repo-local khác chỉ khi concern của task yêu cầu.

Không quét toàn bộ repository hoặc toàn bộ `docs/` khi chưa cần.

## Định tuyến theo concern

| Concern | Source of truth |
|---|---|
| Responsibility, module, dependency và data flow nội bộ | `ARCHITECTURE.md` + live source |
| Bootstrap, test, lint, build và guardrail | `docs/VERIFY.md` + live CI/manifest |
| Security boundary hoặc dữ liệu nhạy cảm | `docs/SECURITY.md` nếu tồn tại + live source |
| Reusable distilled knowledge | Shared Knowledge MCP |

Artifact optional không tồn tại thì tiếp tục bằng source, test và tài liệu hiện
có. Không tạo file rỗng chỉ để hoàn thiện cấu trúc.

## Shared Knowledge MCP

Knowledge MCP độc lập với current working directory và current repository.
`context.repo`/`context.domain` chỉ là ranking hint; chúng không giới hạn namespace
được đọc. Agent ở repo hiện tại được phép nhận relevant `global`, `system`, `repo`
hoặc `domain` knowledge khác qua tool.

### Đọc

- Dùng `knowledge_read(keywords, context?, limit?)`; không tự tìm/mở physical
  Knowledge Store path.
- Shared knowledge là reusable context, không phải oracle mạnh hơn live owner
  source/test. Nếu knowledge mâu thuẫn source/test hiện tại của repo này, source/test
  hiện tại thắng cho task đang làm; xác minh kết luận mới trước khi persist update.
- Knowledge MCP read failure không đồng nghĩa knowledge không tồn tại. Nếu task vẫn
  an toàn bằng live source có thể tiếp tục, nhưng phải giữ caveat phù hợp.

### Ghi

Sau implementation/investigation và verification, nhưng **trước khi finalize
terminal result**, review knowledge đã thực sự được xác nhận trong turn.

1. Không persist working log, task status, điều hiển nhiên đọc trực tiếp từ source,
   guess hoặc hypothesis chưa đủ evidence.
2. Search existing shared knowledge trước khi create; ưu tiên update để tránh
   duplicate.
3. Submit semantic payload qua `knowledge_write`; không truyền filename, path,
   directory hoặc tự `mkdir` knowledge store.
4. Create không truyền `id`/`expected_revision`; MCP derive identity + canonical
   path từ `scope` + `canonical_name`.
5. Update phải dùng exact `id` + `expected_revision` từ `knowledge_read`; revision
   conflict phải reread/re-distill, không overwrite mù.
6. Routing summary/when-to-read/keywords dùng concise canonical concepts, thường
   là English; multilingual/legacy/project terminology nằm trong aliases khi hữu ích.
7. Content có thể Vietnamese, English hoặc mixed. Không tạo field `language`.
8. `sources` phải có provenance đủ để kiểm tra conclusion.
9. Nếu không có durable candidate, gọi `knowledge_write(entries=[])` để ghi nhận
   finalization review hoàn tất mà không tạo file.
10. Nếu có durable candidate nhưng write thất bại, không tuyên bố đã persist; ghi
    failure/caveat vào terminal result.

Knowledge distillation là semantic responsibility của agent. Knowledge MCP sở hữu
ID/path/directory/render/index/locking/revision/persistence mechanics.

## Ranh giới Workspace

- Chỉ đọc/sửa file trong Git root hiện tại, ngoại trừ exact result artifact mà MCP
  chỉ định cho turn đang chạy.
- Knowledge MCP là tool exception, **không phải filesystem exception**: agent dùng
  content tool trả về nhưng không tự mở external Knowledge Store path.
- Không tự suy đoán, tìm hoặc mở result artifact khác.
- Không đọc/sửa workspace `repos.yaml`, `SYSTEM_MAP.md`, `.qiqi/tasks/` hoặc
  workspace control file khác.
- Không đọc/sửa repository anh em.
- Không spawn/delegate sang coding agent khác và không gọi MCP orchestration của
  QiQi từ child turn.
- Live context cross-repo phải đến từ task prompt của QiQi; shared durable knowledge
  có thể đến trực tiếp từ Knowledge MCP.
- Nếu live context từ QiQi mâu thuẫn với source/test hiện tại, dừng phần phụ thuộc,
  ghi evidence và báo conflict.

## Handoff với QiQi

QiQi là handoff broker giữa repository hiện tại và phần còn lại của workspace đối
với **live execution evidence**. Execution agent không handoff trực tiếp cho
repository anh em.

### Input từ QiQi

Task prompt của QiQi là nguồn live workspace/upstream context cho turn hiện tại.
Khi cần, prompt phải chứa trực tiếp context đã được QiQi reconcile, ví dụ:

- outcome, scope và phần ngoài phạm vi;
- decision/contract cross-repo cần cho task;
- upstream result từ repository khác cần dùng;
- evidence hoặc provenance ngắn khi cần để kiểm chứng context;
- verification hoặc blocker policy có liên quan.

Agent không tự mở result/source của repository khác để bổ sung live context. Từ
handoff của QiQi, agent tự khám phá implementation detail bên trong Git root hiện
tại và query Shared Knowledge MCP độc lập khi cần durable context.

### Output về QiQi

Khi chạy qua `qiqi_delegate`, **MCP footer là source of truth duy nhất cho cơ chế
result handoff**: exact artifact, pending marker/history, headings và thứ tự,
Outcome vocabulary, cùng quy tắc finalization. Không lặp hoặc tự định nghĩa lại
protocol đó trong repo policy.

Exact result artifact dưới workspace `.qiqi/runs/` chỉ được parent execution
agent nhận task trực tiếp từ QiQi/MCP cập nhật hoặc finalize. Subagent không được
sửa result artifact này.

`### Repo-local Knowledge` là **legacy heading name** do current `qiqi_delegate`
contract giữ để bảo toàn compatibility. Dưới architecture mới, section này ghi:

- Knowledge MCP IDs đã `created`/`updated` trong turn, hoặc
- `None` khi `knowledge_write(entries=[])`/không có persisted change, hoặc
- persistence failure cụ thể nếu candidate đáng lưu nhưng write không thành công.

Section này không tạo nghĩa vụ ghi knowledge file vào Git repository hiện tại.

Repo policy bổ sung semantics cho **Cross-repo Impact**: fact/evidence vượt boundary
repo hiện tại và cần QiQi điều phối execution.

Khi có Cross-repo Impact, nêu đủ:

- điều gì thay đổi hoặc được phát hiện;
- repository/boundary nào bị ảnh hưởng;
- evidence chính từ repository hiện tại;
- next action nếu đã rõ.

Agent không quyết định trực tiếp công việc của repository anh em. Agent chỉ handoff
fact/evidence cho QiQi để QiQi quyết định downstream task hoặc workspace update.
Knowledge persistence không thay thế Cross-repo Impact khi repo khác còn cần work.

## Hợp đồng Làm việc

- Giữ đúng outcome, phạm vi và phần ngoài phạm vi trong prompt của QiQi.
- Tự khám phá implementation detail nội bộ thay vì hỏi QiQi điều repo có thể trả lời.
- Dùng evidence kiểm tra lại được: source path, test, command, spec hoặc runtime output.
- Không tuyên bố hoàn thành chỉ từ inspection khi task yêu cầu thay đổi/verification.
- Không đổi regression mới thành legacy issue để hoàn thành task.
- Không ghi secret hoặc dữ liệu nhạy cảm vào shared knowledge hoặc result artifact.

## Cross-repo Impact

Khi phát hiện ảnh hưởng từ hai repository trở lên, API/event/schema dùng chung,
upstream/downstream behavior hoặc decision cần QiQi điều phối:

1. Không sửa repository khác.
2. Handoff fact, affected repository/boundary, evidence và next action nếu rõ cho
   QiQi qua result của turn hiện tại.
3. Có thể persist reusable verified knowledge qua Knowledge MCP, nhưng vẫn phải
   handoff impact nếu repository khác cần investigation/implementation/verification.

QiQi chịu trách nhiệm chuyển live context đó tới downstream repository hoặc xử lý
ở workspace level.

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
chưa chạy được báo rõ, không có regression mới đã biết, agent đã thực hiện
knowledge review và gọi `knowledge_write` kể cả `entries=[]`, persistence failure
có durable candidate không bị che giấu, và cross-repo impact cần QiQi biết đã được
handoff.

Nếu còn decision hoặc dependency không thể tự giải quyết, task chưa completed;
tuân theo MCP result-handoff protocol của turn để ghi terminal state và blocker.
