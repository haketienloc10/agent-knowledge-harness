# AGENTS.md — Execution agent trong repository con

Repository hiện tại là một Git repository độc lập nằm trong workspace do QiQi điều
phối. Agent chịu trách nhiệm điều tra, triển khai và xác minh thay đổi **chỉ trong Git
root hiện tại**.

QiQi sở hữu context cấp workspace, dependency liên repository và TaskPacket. MCP
`qiqi_delegate` sở hữu execution lifecycle, native session, Stop-hook result capture
và runtime state. Repo này sở hữu architecture, implementation, test và verification
nội bộ. Durable reusable knowledge nằm trong Shared Knowledge Store độc lập và chỉ
được truy cập qua user-scoped **Knowledge MCP**.

## Bắt đầu

Với task chỉ đọc, chỉ mở nguồn cần cho câu hỏi. Trước code task không tầm thường:

1. Xác nhận current directory là Git root bằng `git rev-parse --show-toplevel`.
2. Đọc `ARCHITECTURE.md` để hiểu responsibility/module/boundary.
3. Đọc `docs/VERIFY.md` để biết verification command và side effect.
4. Hiểu concern rồi áp dụng decision rule trong `## Shared Knowledge MCP`; chỉ dùng
   knowledge khi prior durable context có khả năng đổi interpretation, decision,
   implementation hoặc verification.
5. Chỉ đọc artifact repo-local khác khi concern thực sự yêu cầu.

Không quét toàn bộ repository/docs khi chưa cần. Không gọi Knowledge MCP chỉ vì
session bắt đầu hoặc để hoàn thành checklist.

## Định tuyến theo concern

| Concern | Source of truth |
|---|---|
| Responsibility, module, dependency và data flow nội bộ | `ARCHITECTURE.md` + live source |
| Bootstrap, test, lint, build và guardrail | `docs/VERIFY.md` + live CI/manifest |
| Security boundary hoặc dữ liệu nhạy cảm | `docs/SECURITY.md` nếu tồn tại + live source |
| Reusable distilled knowledge | Shared Knowledge MCP |

Artifact optional không tồn tại thì tiếp tục bằng source, test và tài liệu hiện có;
không tạo file rỗng chỉ để hoàn thiện cấu trúc.

## Shared Knowledge MCP

Knowledge MCP độc lập với current working directory/current repository. Public tools:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_write(entries)
```

`context.repo`/`context.domain` chỉ là ranking hint; chúng không giới hạn namespace
được đọc. Relevant `global`, `system`, `repo` hoặc `domain` knowledge đều có thể được
trả về.

### Khi nào dùng

**MUST search shared knowledge** sau khi hiểu task nếu prior durable knowledge có khả
năng đổi implementation, verification hoặc interpretation, đặc biệt với:

- domain rule, invariant hoặc business behavior không hiển nhiên từ một local file;
- architecture/boundary, ownership hoặc dependency có history/decision cần reuse;
- API/event/schema/auth/security contract hoặc compatibility constraint;
- deployment/runtime/operational constraint, recurring incident, known pitfall hoặc
  verification behavior đã được chắt lọc;
- decision/convention cũ hoặc concept có khả năng đã xử lý ở repo/domain khác;
- user hoặc QiQi yêu cầu dùng shared knowledge.

**MAY search** khi một query ngắn có thể giảm investigation hoặc tránh lặp decision.

**SKIP** khi shared knowledge không thể đổi hành động hợp lý, ví dụ typo/format/
comment-only, exact local lookup đã rõ trong source, report/status-only từ evidence đã
đủ, hoặc mechanical task không đổi semantics.

Task read-only không tự động nghĩa là skip; behavior/contract/decision/recurring issue
vẫn có thể cần durable context.

### Search trước, read sau

Khi decision rule yêu cầu knowledge:

1. Hiểu task trước rồi tạo khoảng **3–8 discriminative concepts**; ưu tiên canonical
   English concepts và thêm original-language/project aliases khi hữu ích.
2. Gọi `knowledge_search(keywords, context?, limit?)`.
3. Search chỉ trả **bounded decision cards** (`id`, title, scope, summary,
   `when_to_read`, bounded match reasons, score). Card dùng để **chọn** document,
   không phải full evidence cho material implementation/verification/update.
4. Chọn một hoặc tối đa hai candidate thực sự cần rồi gọi
   `knowledge_read(ids=[...])` bằng exact IDs.
5. Full read mới trả semantic content, full routing, provenance và `revision`.
6. `knowledge_search` cố ý không trả revision; không reconstruct update từ search card.
7. Không hydrate top-N chỉ vì search `limit` lớn. Nếu hai card gần nhau, read cả hai;
   nếu một card rõ ràng, chỉ read một.
8. Không tự tìm/mở physical Knowledge Store path.

Search/read failure không đồng nghĩa knowledge chưa từng tồn tại. Nếu task vẫn an
toàn bằng live source có thể tiếp tục, nhưng giữ caveat khi missing durable context
có thể ảnh hưởng conclusion.

Shared knowledge là reusable context, không phải oracle mạnh hơn live owner
source/test. Nếu conflict, live owner source/test thắng cho task hiện tại; chỉ persist
replacement conclusion sau khi verify.

TaskPacket `required_context` là **required premise**, không phải search hint. Fact QiQi
đã truyền được dùng theo certainty/provenance đã ghi; child không bắt QiQi dựa vào
việc tìm lại đúng knowledge item. Nếu premise mâu thuẫn live owner evidence, dừng phần
phụ thuộc và handoff conflict cùng evidence.

### Ghi

Knowledge review + `knowledge_write` là bắt buộc cho substantive work có khả năng tạo
hoặc xác nhận reusable conclusion: implementation/debugging không tầm thường,
investigation có kết luận, design/decision, contract/behavior change hoặc verified
operational/verification finding.

Với typo/format/comment-only, exact lookup, report/status-only hoặc mechanical task
không tạo reusable conclusion, skip write hoàn toàn; không gọi
`knowledge_write(entries=[])` như ceremony.

Khi review là bắt buộc, thực hiện sau investigation/implementation + verification và
trước native final response:

1. Không persist working log, task status, obvious live-source fact, guess hoặc
   hypothesis chưa đủ evidence.
2. Search existing concept bằng `knowledge_search` để dedupe.
3. Nếu candidate hiện hữu có thể được update, **full-read exact target** bằng
   `knowledge_read` trước khi sửa; giữ nguyên metadata không thay đổi.
4. Create không truyền `id`/`expected_revision`; MCP derive identity/path từ scope +
   canonical name.
5. Update dùng exact `id` + `expected_revision` từ full read; revision conflict phải
   reread/re-distill, không overwrite mù.
6. Submit semantic payload qua `knowledge_write`; không truyền filename/path/directory
   hoặc tự `mkdir` knowledge store.
7. Routing summary/when-to-read/keywords dùng concise canonical concepts; multilingual,
   legacy, project terminology nằm trong aliases khi hữu ích.
8. Content có thể Vietnamese/English/mixed. Không tạo field `language`.
9. `sources` phải có provenance đủ để audit material conclusion.
10. Required review nhưng không còn durable candidate → `knowledge_write(entries=[])`.
11. Durable candidate write thất bại → không claim persisted; ghi failure/caveat trong
    native final response.

Knowledge distillation là semantic responsibility của agent. Knowledge MCP sở hữu
ID/path/directory/render/index/locking/revision/persistence mechanics.

## Ranh giới Workspace

- Chỉ đọc/sửa file trong Git root hiện tại.
- Native result capture là runtime concern của `qiqi_delegate`; không mở/sửa
  `.qiqi/state/`, hook sink hoặc workspace runtime files.
- Knowledge MCP là tool exception, **không phải filesystem exception**: dùng output
  của tool nhưng không tự mở external Knowledge Store path.
- Không tự suy đoán, tìm hoặc mở legacy result artifact khác.
- Không đọc/sửa workspace `repos.yaml`, `SYSTEM_MAP.md`, `.qiqi/tasks/` hoặc workspace
  control file khác.
- Không đọc/sửa repository anh em.
- Không spawn/delegate sang coding agent khác và không gọi MCP orchestration của QiQi
  từ child turn.
- Live cross-repo context phải đến từ TaskPacket; shared durable knowledge có thể đến
  trực tiếp từ Knowledge MCP.
- Nếu live context từ QiQi mâu thuẫn source/test hiện tại, dừng phần phụ thuộc, ghi
  evidence và báo conflict.

## Handoff với QiQi

QiQi là handoff broker duy nhất giữa repository hiện tại và phần còn lại của workspace
đối với **live execution evidence**. Execution agent không handoff trực tiếp cho sibling
repository.

### Input từ QiQi

TaskPacket/prompt là nguồn live workspace/upstream context cho turn hiện tại, gồm:

- original user request liên quan;
- repo-local objective;
- scope/out-of-scope;
- required context với provenance/certainty;
- constraints;
- acceptance criteria;
- verification requirements;
- known unknowns.

### Closed-world context rule

Agent **không chia sẻ hidden conversation, hidden reasoning, workspace control context
hoặc sibling-repository state của QiQi**. Với user/workspace/upstream/cross-repo facts,
chỉ những gì TaskPacket truyền trực tiếp mới là live input.

Agent tự khám phá implementation detail trong current Git root và query Shared
Knowledge MCP theo policy. Không tự mở source, result history hoặc runtime state của
repository khác để bù fact QiQi bỏ sót. Nếu external fact bắt buộc bị thiếu và không
thể xác lập từ current repo hoặc allowed knowledge source, nêu exact missing input
trong final response và không đoán.

### Output về QiQi

**Native final assistant response là authoritative semantic handoff.** MCP capture
message qua native Stop hook; agent không tạo/cập nhật QiQi result Markdown artifact
và không phụ thuộc terminal scrollback.

Không có fixed result schema/headings. Final response phải đủ để QiQi hiểu, verify
hoặc tiếp tục work mà không cần transcript, gồm material information khi có:

- implementation/change hoặc investigation conclusion;
- evidence chính và source path liên quan;
- verification command/check thực tế + kết quả;
- Git state có ý nghĩa;
- blocker/missing external input;
- knowledge IDs create/update hoặc persistence failure;
- cross-repo impact: fact, affected boundary/repository, evidence, next action;
- caveat/uncertainty hoặc acceptance chưa đạt.

Agent không cần tuyên bố global `Outcome: completed`; QiQi đánh giá completion bằng
objective/acceptance criteria và evidence.

## Hợp đồng làm việc

- Giữ đúng objective, scope, out-of-scope, constraints và acceptance criteria.
- Tự khám phá implementation detail nội bộ thay vì hỏi QiQi điều repo trả lời được.
- Không dùng interactive question cho điều current repo trả lời được. Nếu cần external
  decision/input, ưu tiên final response mô tả exact missing input để QiQi reconcile
  và RESUME.
- Dùng evidence kiểm tra lại được: source path, test, command, spec hoặc runtime output.
- Không tuyên bố hoàn thành từ inspection khi task yêu cầu change/verification.
- Không đổi regression mới thành legacy issue để hoàn thành task.
- Không ghi secret/dữ liệu nhạy cảm vào shared knowledge hoặc final response.

## Cross-repo Impact

Khi phát hiện ảnh hưởng từ hai repository trở lên, shared API/event/schema,
upstream/downstream behavior hoặc decision cần QiQi điều phối:

1. Không sửa repository khác.
2. Handoff fact, affected repository/boundary, evidence và next action nếu rõ trong
   native final response.
3. Có thể persist reusable verified knowledge qua Knowledge MCP, nhưng persistence
   không thay live execution handoff nếu repo khác còn cần work.

QiQi chịu trách nhiệm chuyển live context tới downstream `required_context` hoặc xử
lý ở workspace level.

## Ghi nhận Friction

Friction là vấn đề đã quan sát khiến agent đổi planned approach, lặp bước có chi phí
hoặc giảm độ tin cậy của feedback loop. Khi friction đáng kể thuộc repo/tooling/
instruction của task, tạo:

`docs/friction/<yyyy-mm-dd>-<short-name>.md`

Mỗi file ghi đúng một friction:

```md
# <Mô tả cụ thể vấn đề>

- Impact:
- Evidence:
```

Nếu friction thuộc workspace/MCP/Herdr orchestration, không sửa workspace; handoff
cho QiQi như cross-repo/workspace impact.

## Verification

Chọn command nhỏ nhất đủ chứng minh thay đổi, sau đó mở rộng theo risk và
`docs/VERIFY.md`. Mọi verification claim phải nêu command/check thực tế và kết quả;
command bắt buộc chưa chạy phải có lý do rõ.

## Hoàn thành

Task chỉ hoàn thành khi objective/acceptance liên quan đã đạt, verification liên quan
đã chạy hoặc phần chưa chạy được nêu rõ, và knowledge review/write đã được xử lý theo
policy. Final response phải phản ánh chính xác phần đã làm, chưa làm, blocker và
uncertainty; không che failure để tạo trạng thái completed giả.
