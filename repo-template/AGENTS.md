# AGENTS.md — Execution agent trong repository con

Repository hiện tại là một Git repository độc lập nằm trong workspace do QiQi
điều phối. Agent trong repo này chịu trách nhiệm điều tra, triển khai và xác minh
thay đổi trong **Git root hiện tại**.

QiQi sở hữu context cấp workspace, dependency liên repository và TaskPacket.
MCP `qiqi_delegate` sở hữu execution lifecycle, native session, Stop-hook result
capture và runtime state. Repo này sở hữu architecture, implementation, test và
verification nội bộ. Durable reusable knowledge nằm trong Shared Knowledge Store
độc lập và chỉ được truy cập qua user-scoped **Knowledge MCP**.

## Bắt đầu

Với task chỉ đọc, chỉ mở nguồn cần cho câu hỏi.

Trước code task không tầm thường:

1. Xác nhận thư mục hiện tại là Git root bằng `git rev-parse --show-toplevel`.
2. Đọc `ARCHITECTURE.md` để hiểu responsibility/module/boundary.
3. Đọc `docs/VERIFY.md` để biết verification command và side effect.
4. Hiểu concern của task rồi áp dụng decision rule trong `## Shared Knowledge MCP`;
   chỉ gọi `knowledge_read` khi prior durable knowledge có khả năng thay đổi cách
   hiểu, quyết định hoặc implementation của task.
5. Đọc artifact repo-local khác chỉ khi concern của task yêu cầu.

Không quét toàn bộ repository hoặc toàn bộ `docs/` khi chưa cần. Không gọi
Knowledge MCP chỉ vì session bắt đầu hoặc chỉ để hoàn thành một checklist.

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

### Khi nào dùng

**MUST `knowledge_read`** sau khi hiểu task nếu prior durable knowledge có khả năng
thay đổi implementation, verification hoặc interpretation của task. Các tín hiệu
điển hình:

- domain rule, invariant hoặc business behavior không hiển nhiên từ một local file;
- architecture/boundary, ownership hoặc dependency có lịch sử/decision cần reuse;
- API/event/schema/auth/security contract hoặc compatibility constraint;
- deployment/runtime/operational constraint, recurring incident, known pitfall hoặc
  verification behavior đã từng được chắt lọc;
- task nhắc tới decision/convention trước đây hoặc concept có khả năng đã được xử lý
  ở repository/domain khác;
- user hoặc QiQi yêu cầu dùng shared knowledge hoặc kiểm tra prior durable context.

**MAY `knowledge_read`** khi chưa chắc prior reusable knowledge có tồn tại nhưng một
query ngắn có thể giảm investigation hoặc tránh lặp lại quyết định cũ.

**SKIP `knowledge_read`** khi knowledge không thể thay đổi hành động hợp lý, ví dụ:

- typo/format/comment-only hoặc mechanical edit không đổi semantics;
- exact local lookup mà câu trả lời đã nằm rõ trong source/file được chỉ định;
- report/status-only từ evidence hiện có, không cần durable context bổ sung;
- task đã được giải quyết đầy đủ bởi TaskPacket + live owner source/test và không có
  dấu hiệu contract/domain/decision/pitfall reusable liên quan.

Task read-only không tự động nghĩa là skip; investigation về behavior, contract,
decision hoặc recurring issue vẫn dùng knowledge khi các tín hiệu MUST ở trên có
mặt.

**MUST search existing knowledge trước khi create/update candidate**. Search này là
bước dedupe/identity và áp dụng ngay cả khi initial task không cần knowledge để thực
thi. Không create chỉ vì chưa nhớ ID; query concept trước và ưu tiên update nếu đã
có knowledge phù hợp.

### Đọc

- Khi decision rule yêu cầu read, hiểu task trước rồi tạo khoảng 5–12 search terms
  có giá trị phân biệt; dùng canonical English concepts và original-language/project
  aliases khi hữu ích.
- Dùng `knowledge_read(keywords, context?, limit?)`; không tự tìm/mở physical
  Knowledge Store path.
- Shared knowledge là reusable context, không phải oracle mạnh hơn live owner
  source/test. Nếu knowledge mâu thuẫn source/test hiện tại của repo này, source/test
  hiện tại thắng cho task đang làm; xác minh kết luận mới trước khi persist update.
- Knowledge MCP read failure không đồng nghĩa knowledge không tồn tại. Nếu task vẫn
  an toàn bằng live source có thể tiếp tục, nhưng phải giữ caveat phù hợp khi
  missing durable context có thể ảnh hưởng kết luận.

TaskPacket `required_context` là **required premise**, không phải search hint. Nếu
QiQi đã truyền một fact ở đó, agent dùng fact theo certainty/provenance đã ghi và
không bắt QiQi phải dựa vào việc agent tìm lại đúng knowledge item. Nếu fact đó mâu
thuẫn live source/test của owner repo, dừng phần phụ thuộc và handoff conflict cùng
evidence; không silently chọn một phía.

### Ghi

Knowledge review + `knowledge_write` là **bắt buộc cho substantive work có khả năng
tạo hoặc xác nhận reusable conclusion**, gồm implementation/debugging không tầm
thường, investigation có kết luận, design/decision, contract/behavior change, hoặc
verified operational/verification finding.

Với typo/format/comment-only, exact lookup, report/status-only hoặc mechanical task
không tạo reusable conclusion, skip knowledge write hoàn toàn; không gọi
`knowledge_write(entries=[])` như ceremony.

Khi knowledge review là bắt buộc, thực hiện sau implementation/investigation và
verification nhưng **trước khi finalize native final response**:

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
9. Nếu review bắt buộc nhưng không còn durable candidate, gọi
   `knowledge_write(entries=[])` để ghi nhận review hoàn tất mà không tạo file.
10. Nếu có durable candidate nhưng write thất bại, không tuyên bố đã persist; ghi
    failure/caveat vào native final response.

Knowledge distillation là semantic responsibility của agent. Knowledge MCP sở hữu
ID/path/directory/render/index/locking/revision/persistence mechanics.

## Ranh giới Workspace

- Chỉ đọc/sửa file trong Git root hiện tại.
- Native result capture là runtime concern của `qiqi_delegate`; agent không mở/sửa
  `.qiqi/state/`, hook sink hoặc workspace runtime files.
- Knowledge MCP là tool exception, **không phải filesystem exception**: agent dùng
  content tool trả về nhưng không tự mở external Knowledge Store path.
- Không tự suy đoán, tìm hoặc mở legacy result artifact khác.
- Không đọc/sửa workspace `repos.yaml`, `SYSTEM_MAP.md`, `.qiqi/tasks/` hoặc
  workspace control file khác.
- Không đọc/sửa repository anh em.
- Không spawn/delegate sang coding agent khác và không gọi MCP orchestration của
  QiQi từ child turn.
- Live context cross-repo phải đến từ TaskPacket của QiQi; shared durable knowledge
  có thể đến trực tiếp từ Knowledge MCP.
- Nếu live context từ QiQi mâu thuẫn với source/test hiện tại, dừng phần phụ thuộc,
  ghi evidence và báo conflict.

## Handoff với QiQi

QiQi là handoff broker giữa repository hiện tại và phần còn lại của workspace đối
với **live execution evidence**. Execution agent không handoff trực tiếp cho
repository anh em.

### Input từ QiQi

TaskPacket/prompt của QiQi là nguồn live workspace/upstream context cho turn hiện
tại. Nó chứa:

- original user request liên quan;
- repo-local objective;
- scope và out-of-scope;
- required context với provenance/certainty;
- constraints;
- acceptance criteria;
- verification requirements;
- known unknowns.

### Closed-world context rule

Agent **không chia sẻ hidden conversation, hidden reasoning, workspace control
context hoặc sibling-repository state của QiQi**. Đối với user/workspace/upstream/
cross-repo facts, chỉ những gì TaskPacket truyền trực tiếp mới là live input.

Agent tự khám phá implementation detail bên trong Git root hiện tại và query Shared
Knowledge MCP độc lập khi decision rule yêu cầu durable context. Không tự mở source,
result history hoặc runtime state của repository khác để bổ sung một fact QiQi bỏ
sót. Nếu một external fact bắt buộc bị thiếu và không thể xác lập từ current repo
hoặc allowed knowledge source, nêu chính xác missing input trong final response và
không đoán.

### Output về QiQi

**Native final assistant response là authoritative semantic handoff.** MCP capture
message này trực tiếp qua native Stop hook; agent không tạo hoặc cập nhật QiQi result
Markdown artifact và không phụ thuộc terminal scrollback.

Không có result schema hoặc fixed headings. Chọn structure phù hợp task. Final
response phải đủ để QiQi hiểu, verify hoặc tiếp tục work mà không cần transcript,
bao gồm material information khi có:

- implementation/change hoặc investigation conclusion;
- evidence chính và source path liên quan;
- verification command/check thực tế + kết quả;
- Git state có ý nghĩa cho task;
- blocker/missing external input;
- knowledge IDs create/update hoặc persistence failure khi có;
- cross-repo impact: fact, affected boundary/repository, evidence và next action;
- caveat, uncertainty hoặc phần acceptance chưa đạt.

Agent không cần tự tuyên bố một global `Outcome: completed`. QiQi đánh giá completion
bằng objective/acceptance criteria và evidence trong response.

## Hợp đồng Làm việc

- Giữ đúng objective, scope, out-of-scope, constraints và acceptance criteria trong
  TaskPacket.
- Tự khám phá implementation detail nội bộ thay vì hỏi QiQi điều repo có thể trả lời.
- Không dùng interactive question cho điều có thể trả lời từ current repo. Nếu cần
  external decision/input, ưu tiên finalize native response mô tả chính xác missing
  input để QiQi có thể reconcile và RESUME sau đó.
- Dùng evidence kiểm tra lại được: source path, test, command, spec hoặc runtime output.
- Không tuyên bố hoàn thành chỉ từ inspection khi task yêu cầu thay đổi/verification.
- Không đổi regression mới thành legacy issue để hoàn thành task.
- Không ghi secret hoặc dữ liệu nhạy cảm vào shared knowledge hoặc final response.

## Cross-repo Impact

Khi phát hiện ảnh hưởng từ hai repository trở lên, API/event/schema dùng chung,
upstream/downstream behavior hoặc decision cần QiQi điều phối:

1. Không sửa repository khác.
2. Handoff fact, affected repository/boundary, evidence và next action nếu rõ cho
   QiQi trong native final response.
3. Có thể persist reusable verified knowledge qua Knowledge MCP, nhưng vẫn phải
   handoff impact nếu repository khác cần investigation/implementation/verification.

QiQi chịu trách nhiệm chuyển live context đó tới downstream `required_context` hoặc
xử lý ở workspace level.

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
nó cho QiQi trong native final response như cross-repo/workspace impact.

## Verification

Chọn command nhỏ nhất đủ chứng minh thay đổi, sau đó mở rộng theo rủi ro và
`docs/VERIFY.md`.

Mọi verification claim phải nêu command/check thực tế và kết quả. Command bắt buộc
chưa chạy phải có lý do rõ; không biến suy đoán thành evidence.

## Hoàn thành

Task chỉ completed khi objective/acceptance liên quan đã đạt, verification liên quan
đã chạy hoặc phần chưa chạy được báo rõ, không có regression mới đã biết, và
cross-repo impact cần QiQi biết đã được handoff.

Với substantive work theo `### Ghi`, completion còn yêu cầu agent đã thực hiện
knowledge review và gọi `knowledge_write`; nếu review không có durable candidate thì
dùng `entries=[]`, còn persistence failure có candidate không được che giấu. Với
task thuộc nhóm SKIP, không có knowledge-write requirement.

Nếu còn decision hoặc dependency không thể tự giải quyết, nêu chính xác missing
input/decision và evidence trong native final response; không tự suy đoán để đạt
completion.
