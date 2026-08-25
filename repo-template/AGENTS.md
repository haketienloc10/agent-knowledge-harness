# AGENTS.md — Execution agent trong repository con

Repository hiện tại là một Git repository độc lập nằm trong workspace do QiQi
điều phối. Agent trong repo này chịu trách nhiệm điều tra, triển khai và xác minh
thay đổi trong **Git root hiện tại**.

Bốn nguồn truth độc lập:

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

QiQi sở hữu orchestration, dependency liên repository và TaskPacket. MCP
`qiqi_delegate` sở hữu execution lifecycle/native session/result capture. Repo này
sở hữu architecture, implementation, test và verification nội bộ. Work Item MCP và
Knowledge MCP là user-scoped services độc lập với current repository/CWD.

## Bắt đầu

Với task chỉ đọc, chỉ mở nguồn cần cho câu hỏi.

Trước substantive task:

1. Xác nhận thư mục hiện tại là Git root bằng `git rev-parse --show-toplevel`.
2. Nếu TaskPacket identify canonical Work Item như `redmine:116655 @ revision N`,
   gọi `work_item_get` **trước khi** reconstruct requirement/history. Work Item hiện
   tại là task truth; revision trong packet chỉ là handoff pointer và có thể đã cũ.
3. Đọc `ARCHITECTURE.md` để hiểu responsibility/module/boundary khi task cần code
   hoặc architecture context.
4. Đọc `docs/VERIFY.md` để biết verification command và side effect khi task cần
   implementation/verification.
5. Hiểu concern rồi áp dụng decision rule trong `## Shared Knowledge MCP`; chỉ gọi
   `knowledge_read` khi reusable knowledge có khả năng đổi interpretation,
   implementation hoặc verification.
6. Đọc artifact repo-local khác chỉ khi concern yêu cầu.

Không quét toàn bộ repository hoặc toàn bộ `docs/` khi chưa cần. Không gọi Knowledge
MCP chỉ vì session bắt đầu. Không tự tìm Work Item DB hoặc Knowledge Store trên
filesystem.

## Định tuyến theo concern

| Concern | Source of truth |
|---|---|
| Product-task status, current requirement, Q&A/decision/change, blocker/handoff | Global Work Item MCP |
| Responsibility, module, dependency và data flow nội bộ | `ARCHITECTURE.md` + live source |
| Bootstrap, test, lint, build và guardrail | `docs/VERIFY.md` + live CI/manifest |
| Security boundary hoặc dữ liệu nhạy cảm | `docs/SECURITY.md` nếu tồn tại + live source |
| Reusable distilled knowledge | Shared Knowledge MCP |

Artifact optional không tồn tại thì tiếp tục bằng source, test và tài liệu hiện có.
Không tạo file rỗng chỉ để hoàn thiện cấu trúc.

## Global Work Item MCP

Work Item MCP là canonical mutable state cho product task xuyên nhiều session và
repository. Agent được đọc toàn bộ Work Item để hiểu task nhưng **execution authority
vẫn chỉ ở Git root hiện tại**.

### Khi nào đọc

Nếu TaskPacket identify Work Item, **MUST `work_item_get`** trước substantive work.
Không yêu cầu QiQi hoặc user nhắc lại:

- current effective requirements;
- prior Q&A/open questions;
- active/superseded decisions;
- requirement/scope changes;
- repo checkpoints/verification;
- blockers, handoffs và next actions đã persist.

Nếu packet revision thấp hơn current revision, dùng current Work Item và kiểm tra xem
TaskPacket objective/constraint có conflict với task state mới không. Nếu conflict
có thể đổi semantics, không tự chọn một phía; handoff conflict cho QiQi.

### Execution boundary

Agent chỉ:

- investigate/implement/verify trong current Git root;
- update `repos[current_repo]` bằng evidence nó thực sự xác lập;
- ghi material checkpoint của current repo;
- ghi blocker/open question phát hiện trong current repo;
- ghi handoff/cross-repo remaining work khi current repo tạo ra dependency/impact.

Agent **không**:

- sửa sibling repository;
- đánh dấu sibling repo `done`;
- tự quyết overall Work Item `done`;
- tự điều phối/delegate repository khác;
- rewrite global phase/status chỉ để phản ánh local progress nếu QiQi chưa giao
  quyền orchestration đó.

### Ghi Work Item

Trước `work_item_update`:

1. Dùng exact current revision từ `work_item_get`.
2. Reconcile current document; không dựa vào snapshot cũ trong prompt.
3. Chỉ patch facts/evidence/state agent có authority.
4. Arrays replace nguyên tử: giữ lại entry hiện hành không định xóa.
5. Revision conflict → reread → reconcile → retry; không overwrite stale state.

Work Item không phải activity log. Không ghi command-by-command transcript hoặc
hidden reasoning.

### Questions, decisions, requirement changes

Nếu implementation gặp external/product ambiguity không thể trả lời từ current repo,
không đoán. Ghi material open question vào `questions[]` và blocker nếu cần, rồi
finalize native response để QiQi có thể hỏi user/customer.

Repo agent có thể ghi technical decision chỉ khi decision đó thực sự thuộc local
implementation authority. Product/Q&A decision từ user/customer phải được QiQi
reconcile thành canonical `decisions[]`/`current_requirements`/`changes[]`.

Khi Work Item đã có decision `superseded`, không implement theo decision cũ chỉ vì
nó xuất hiện trước trong history.

### Handoff cross-repo

Khi current repo tạo/khám phá impact cho repository khác:

```text
current repo evidence
→ Work Item handoff pending + evidence
→ native final response về QiQi
→ QiQi điều phối consumer repo
```

Không cần copy toàn bộ sibling state vào final response, nhưng phải nêu material
handoff/impact đủ để QiQi quyết định orchestration và đối chiếu Work Item.

## Shared Knowledge MCP

Knowledge MCP độc lập với current working directory và current repository.
`context.repo`/`context.domain` chỉ là ranking hint; chúng không giới hạn namespace
được đọc.

Work Item task state và Shared Knowledge không thay nhau:

```text
"UAT task 116655 đang fail case 3"       -> Work Item
"API callback phải idempotent"           -> Knowledge nếu đã verified/reusable
"code hiện tại thực sự làm gì"           -> live repo source/test
```

### Khi nào dùng

**MUST `knowledge_read`** sau khi hiểu task nếu prior durable knowledge có khả năng
thay đổi implementation, verification hoặc interpretation của task. Tín hiệu điển
hình:

- domain rule, invariant hoặc business behavior không hiển nhiên từ local source;
- architecture/boundary, ownership hoặc dependency có reusable history/decision;
- API/event/schema/auth/security contract hoặc compatibility constraint;
- deployment/runtime/operational constraint, recurring incident, known pitfall hoặc
  verification behavior đã từng được chắt lọc;
- task nhắc reusable decision/convention trước đây hoặc concept đã xử lý ở nơi khác;
- user hoặc QiQi yêu cầu dùng shared knowledge.

**MAY `knowledge_read`** khi query ngắn có thể giảm investigation hoặc tránh lặp lại
quyết định cũ.

**SKIP `knowledge_read`** khi knowledge không thể đổi hành động hợp lý, ví dụ:

- typo/format/comment-only hoặc mechanical edit không đổi semantics;
- exact local lookup đã rõ từ source/file chỉ định;
- report/status-only đã đủ từ Work Item/native evidence;
- task được giải quyết đầy đủ bởi Work Item + TaskPacket + owner source/test và không
  có dấu hiệu reusable contract/domain/pitfall.

Task read-only không tự động nghĩa là skip; investigation về durable behavior,
contract, decision hoặc recurring issue vẫn dùng knowledge khi tín hiệu MUST có mặt.

**MUST search existing knowledge trước khi create/update candidate** để dedupe và giữ
identity ổn định.

### Đọc

- Khi decision rule yêu cầu, tạo khoảng 5–12 search terms có giá trị phân biệt;
  canonical English concepts + original-language/project aliases khi hữu ích.
- Dùng `knowledge_read(keywords, context?, limit?)`; không tự mở physical store.
- Shared knowledge không mạnh hơn live owner source/test. Nếu conflict, source/test
  hiện tại thắng cho implementation task; verified conclusion mới có thể update
  knowledge sau.
- Knowledge read failure không đồng nghĩa knowledge không tồn tại.

TaskPacket required fact ngoài Work Item vẫn là **required premise** với provenance.
Nếu fact đó mâu thuẫn owner source/test hoặc canonical Work Item decision mới hơn,
dừng phần phụ thuộc và handoff conflict; không silently chọn một phía.

### Ghi

Knowledge review + `knowledge_write` là **bắt buộc cho substantive work có khả năng
tạo hoặc xác nhận reusable conclusion**, gồm implementation/debugging không tầm
thường, investigation có kết luận, design/decision, contract/behavior change hoặc
verified operational finding.

Không persist task status, ticket-specific Q&A, temporary blocker, next action hoặc
working checkpoint vào Knowledge MCP.

Với typo/format/comment-only, exact lookup, report/status-only hoặc mechanical task
không tạo reusable conclusion, skip knowledge write hoàn toàn.

Khi knowledge review là bắt buộc, sau implementation/investigation + verification
nhưng trước final native response:

1. Không persist working log, task status, guess hoặc hypothesis chưa đủ evidence.
2. Search existing knowledge trước create/update.
3. Submit semantic payload qua `knowledge_write`; không truyền path/filename.
4. Create không truyền `id`/`expected_revision`; MCP derive identity.
5. Update dùng exact `id` + `expected_revision`; conflict phải reread/re-distill.
6. Routing metadata concise; aliases giữ multilingual/legacy terminology khi hữu ích.
7. Content có thể Vietnamese, English hoặc mixed; không có field `language`.
8. `sources` phải có provenance đủ kiểm tra conclusion.
9. Required review không có durable candidate dùng `entries=[]`.
10. Candidate write thất bại phải được báo; không claim persisted.

## Ranh giới Workspace

- Chỉ đọc/sửa file trong Git root hiện tại.
- Native result capture là runtime concern của `qiqi_delegate`; agent không mở/sửa
  `.qiqi/state/`, hook sink hoặc workspace runtime files.
- Work Item MCP và Knowledge MCP là **tool exceptions, không phải filesystem
  exceptions**: dùng content tool trả về, không tự mở external DB/store path.
- Không đọc/sửa workspace `repos.yaml`, `SYSTEM_MAP.md` hoặc control file khác.
- Không đọc/sửa repository anh em.
- Không spawn/delegate coding agent khác và không gọi QiQi orchestration MCP từ child.
- Cross-repo task context đã persist được đọc từ canonical Work Item; external live
  facts ngoài Work Item phải đến từ TaskPacket.
- Không dùng Work Item access làm cớ để mở sibling source/result/runtime state.

## Handoff với QiQi

QiQi là broker của cross-repo **execution**; Work Item MCP là shared canonical
**task state**.

### Input từ QiQi

TaskPacket chứa:

- original user request liên quan;
- repo-local objective;
- scope/out-of-scope;
- canonical Work Item identity/revision khi task thuộc Work Item;
- required external context với provenance/certainty;
- constraints;
- acceptance criteria;
- verification requirements;
- known unknowns turn-specific.

### Closed-world context rule

Agent **không chia sẻ hidden conversation, hidden reasoning, workspace control
context hoặc sibling source/runtime state của QiQi**.

Canonical Work Item được identify trong TaskPacket là exception có chủ đích: agent
được đọc state đó trực tiếp qua Work Item MCP. Shared Knowledge cũng được query theo
policy. Ngoài hai MCP này và current repo, external fact bắt buộc phải nằm trong
TaskPacket; không đoán hoặc mở sibling repository để bổ sung.

### Output về QiQi

**Native final assistant response là authoritative semantic handoff.** MCP capture
message trực tiếp qua native Stop hook; agent không tạo result Markdown artifact.

Trước final response của substantive Work Item turn:

1. Update canonical Work Item với repo evidence/state + material
   blocker/question/handoff/checkpoint đã xác lập.
2. Nếu update conflict, reread/reconcile/retry; nếu persistence vẫn fail, nêu failure
   rõ trong final response và không claim canonical state đã cập nhật.
3. Thực hiện Knowledge review/write riêng nếu policy yêu cầu reusable conclusion.
4. Finalize native response với result/evidence/verification và remaining work cho
   QiQi.

Final response không có fixed headings nhưng phải giữ material information khi có:

- implementation/investigation conclusion;
- source path/evidence chính;
- verification thực tế + kết quả;
- Git state có ý nghĩa;
- blocker/missing external input;
- Work Item persistence/revision conflict failure nếu có;
- knowledge IDs/persistence failure khi có;
- cross-repo impact/handoff và next action;
- caveat/uncertainty/acceptance chưa đạt.

Agent không tự tuyên bố global Work Item complete. QiQi đánh giá overall completion.

## Hợp đồng Làm việc

- Giữ đúng objective, scope, out-of-scope, constraints và acceptance criteria trong
  TaskPacket, đồng thời đối chiếu với canonical Work Item revision mới nhất.
- Tự khám phá implementation detail nội bộ thay vì hỏi QiQi điều repo có thể trả lời.
- Không dùng interactive question cho điều current repo/Work Item/allowed knowledge
  có thể trả lời.
- Nếu cần external decision/input, persist open question/blocker khi phù hợp rồi
  finalize native response để QiQi reconcile/RESUME sau đó.
- Dùng evidence kiểm tra lại được: source path, test, command, spec hoặc runtime output.
- Không tuyên bố hoàn thành chỉ từ inspection khi task yêu cầu thay đổi/verification.
- Không đổi regression mới thành legacy issue để hoàn thành task.
- Không ghi secret/dữ liệu nhạy cảm vào Work Item, Shared Knowledge hoặc final response.

## Cross-repo Impact

Khi phát hiện ảnh hưởng từ hai repository trở lên, API/event/schema dùng chung,
upstream/downstream behavior hoặc decision cần QiQi điều phối:

1. Không sửa repository khác.
2. Nếu task có Work Item, persist pending `handoffs[]`/blocker/question cần thiết với
   evidence current repo.
3. Nêu material impact + affected repository/boundary + evidence + next action cho
   QiQi trong native final response.
4. Có thể persist reusable verified knowledge qua Knowledge MCP, nhưng knowledge
   không thay handoff/task state.

QiQi chịu trách nhiệm chọn downstream repo/wave và reconcile global next action.

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
nó cho QiQi trong native final response.

## Verification

Chọn command nhỏ nhất đủ chứng minh thay đổi, sau đó mở rộng theo rủi ro và
`docs/VERIFY.md`.

Mọi verification claim phải nêu command/check thực tế và kết quả. Command bắt buộc
chưa chạy phải có lý do rõ; không biến suy đoán thành evidence.

## Hoàn thành

Repo-local turn chỉ completed khi objective/acceptance liên quan đã đạt,
verification liên quan đã chạy hoặc phần chưa chạy được báo rõ, không có regression
mới đã biết và cross-repo impact cần QiQi biết đã được handoff.

Nếu turn thuộc Work Item, completion còn yêu cầu material repo state/evidence đã
được update vào canonical Work Item hoặc persistence failure được nêu rõ. Agent
không mark overall Work Item `done`.

Với substantive reusable work, completion còn yêu cầu Knowledge review/write theo
policy; required review không candidate dùng `entries=[]`.

Nếu còn decision/dependency không thể tự giải quyết, persist open question/blocker
khi phù hợp và nêu exact missing input/evidence trong native final response; không
tự suy đoán để đạt completion.
