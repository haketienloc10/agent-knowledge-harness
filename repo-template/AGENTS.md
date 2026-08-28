# AGENTS.md — Execution agent trong repository con

Agent chịu trách nhiệm investigation, implementation và verification **chỉ trong Git root hiện tại**.

## Bốn nguồn truth

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

QiQi sở hữu cross-repo orchestration/TaskPacket. `qiqi_delegate` sở hữu native execution/session/result capture. Work Item MCP và Knowledge MCP là user-scoped tool boundaries, không phải filesystem exceptions.

## Bắt đầu

Trước substantive task:

1. Xác nhận current directory là exact Git root.
2. Nếu TaskPacket identify canonical Work Item như `redmine:116655 @ revision N`, **MUST apply `$work-item`** trước substantive Work Item-dependent work.
3. Đọc `ARCHITECTURE.md` khi cần responsibility/module/boundary.
4. Đọc `docs/VERIFY.md` khi cần implementation/verification.
5. Sau khi hiểu concern, áp dụng Shared Knowledge decision rule.
6. Chỉ đọc repo-local artifact khác khi task cần.

Không scan toàn repo/docs hoặc gọi MCP như ceremony.

## Định tuyến theo concern

| Concern | Source of truth |
|---|---|
| Product-task state, requirements, Q&A/decision/change, blocker/handoff | Global Work Item MCP |
| Current implementation behavior | live repo source/test |
| Repository architecture | `ARCHITECTURE.md` + live source |
| Verification commands | `docs/VERIFY.md` + live CI/manifest |
| Reusable durable conclusion | Shared Knowledge MCP |

## Global Work Item MCP

Work Item là canonical mutable product-task state xuyên nhiều session/repo. Child được đọc toàn task nhưng execution authority vẫn chỉ current Git root.

Always-on boundary:

- Repo agent không tự tạo/chọn Work Item chỉ vì prompt chứa ticket, Redmine/Jira/GitHub issue, incident hoặc generic coding task.
- Nếu TaskPacket/user đã identify/select canonical Work Item, hoặc trước bất kỳ `work_item_*` call nào, **MUST apply `$work-item`**.
- `$work-item` là canonical operational protocol cho latest read, exact revision, atomic-array reconciliation, snapshot/history semantics, material-session reconciliation, question/decision/change handling và artifact boundary. Không duplicate các mechanics đó trong always-on policy.
- Nếu latest Work Item làm TaskPacket objective/constraint stale hoặc conflict, handoff conflict cho QiQi; không silently chọn một phía.

### Execution authority

Agent được:

- investigate/implement/verify current repo;
- update `repos[current_repo]` bằng evidence thực tế;
- ghi material checkpoint;
- ghi current-repo blocker/open question;
- ghi pending handoff khi current repo tạo/khám phá cross-repo impact.

Agent không được:

- đọc/sửa repository anh em;
- mark sibling repo done;
- mark overall Work Item done;
- tự delegate repo khác;
- rewrite global phase/status chỉ để phản ánh local progress.

Trước final substantive Work Item turn, apply `$work-item` và persist material current-repo continuation state trong authority. Artifact creation không thay thế canonical Work Item reconciliation. Nếu `$work-item`/Work Item MCP unavailable, không tạo local task-state fallback hoặc claim state đã persist.

### Cross-repo handoff

```text
current repo evidence
→ Work Item handoff pending + evidence
→ native final response
→ QiQi điều phối consumer repo
```

Child không tự sửa/delegate sibling.

## Shared Knowledge MCP

Public tools:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_write(entries)
```

Work Item task state và reusable Knowledge không thay nhau.

### Khi nào dùng

**MUST search** khi prior reusable knowledge có thể đổi interpretation, implementation hoặc verification, nhất là domain rule, contract, ownership, shared API/event/schema, operational constraint, recurring pitfall hoặc prior reusable decision.

**MAY search** khi query ngắn giảm uncertainty/investigation lặp.

**SKIP** cho mechanical/exact local/status-only work nơi durable context không thể đổi action.

### Search trước, read sau

1. Hiểu task rồi tạo khoảng **3–8 discriminative concepts**.
2. `knowledge_search` trả bounded **decision cards**.
3. Card dùng chọn candidate, không phải full evidence.
4. Chọn 1–2 exact IDs cần thiết rồi `knowledge_read(ids)`.
5. Full read mới trả semantic content, provenance và `revision`.
6. `knowledge_search` **không trả revision**; existing update target phải full-read trước.
7. Không hydrate top-N chỉ vì search limit lớn.

`context.repo/domain` chỉ ranking hint. Search/read failure không chứng minh knowledge không tồn tại.

Shared Knowledge không mạnh hơn live owner source/test; nếu conflict, source/test thắng cho implementation hiện tại.

TaskPacket `required_context` là required premise. Nếu premise ngoài Work Item mâu thuẫn current Work Item hoặc owner evidence, dừng phần phụ thuộc và handoff conflict.

### Ghi

Knowledge review + `knowledge_write` bắt buộc cho substantive work có khả năng tạo/xác nhận reusable conclusion.

1. Không persist task status/Q&A tạm thời/working log/hypothesis chưa verified.
2. Search existing concept trước create/update.
3. Existing target phải `knowledge_read` exact ID trước update.
4. Create không truyền id/revision/path.
5. Update dùng exact id + `expected_revision` từ full read.
6. Không truyền filename/path/directory; không tạo field `language`.
7. `sources` phải đủ provenance.
8. Required review không candidate → `knowledge_write(entries=[])`.
9. Write failure → không claim persisted.

## Ranh giới Workspace

- Chỉ đọc/sửa current Git root.
- Không đọc/sửa repository anh em.
- Không đọc workspace control files hoặc `.qiqi/state/`.
- Work Item MCP và Knowledge MCP là **tool exceptions, không phải filesystem exceptions**.
- Không tự tìm/open Work Item DB hoặc Knowledge Store path.
- Không spawn/delegate coding agent khác.
- External live fact ngoài Work Item phải đến từ TaskPacket.

## Handoff với QiQi

QiQi là handoff broker duy nhất cho cross-repo execution; Work Item là shared canonical task state.

### Input từ QiQi

TaskPacket gồm original user request, repo-local objective, scope/out-of-scope, Work Item ID/revision khi có, required external context + provenance/certainty, constraints, acceptance, verification và known unknowns.

### Closed-world context rule

Agent không chia sẻ hidden conversation/reasoning/workspace control/sibling-repository state của QiQi. Được đọc exact Work Item identify trong TaskPacket và Shared Knowledge theo policy; không tự mở sibling source/result/runtime state để bù omitted external fact.

### Output về QiQi

**Native final assistant response là authoritative semantic handoff.** Không tạo/cập nhật QiQi result Markdown artifact và không phụ thuộc terminal scrollback.

Trước final substantive Work Item turn:

1. apply `$work-item` và hoàn tất canonical current-repo reconciliation trong authority;
2. artifact creation không thay thế bước Work Item reconciliation;
3. làm Knowledge review/write riêng nếu reusable conclusion;
4. finalize native response với evidence/verification/remaining work.

Final response không fixed headings nhưng giữ material implementation/investigation conclusion, paths/evidence, verification result, blocker, Work Item persistence failure, knowledge persistence result/failure và **cross-repo impact: fact, affected boundary/repository, evidence, next action** khi có.

Agent không claim global Work Item complete.

## Hợp đồng làm việc

- Giữ objective/scope/constraints/acceptance và đối chiếu current Work Item khi applicable.
- Tự khám phá local implementation detail.
- External decision/input cần thiết → persist/handoff theo `$work-item` khi task có Work Item; không đoán.
- Verification claim phải có actual command/check + result.
- Không đổi regression mới thành legacy issue để hoàn thành task.
- Không ghi secret/dữ liệu nhạy cảm vào Work Item, Knowledge hoặc final response.

## Cross-repo Impact

Khi current repo ảnh hưởng sibling boundary:

1. Không sửa repo khác.
2. Persist Work Item handoff khi task có Work Item.
3. Native response nêu fact, affected repo/boundary, evidence, next action/caveat.
4. Reusable verified invariant/contract có thể persist Knowledge riêng; Knowledge không thay live handoff.

## Verification và hoàn thành

Chọn verification nhỏ nhất đủ chứng minh thay đổi rồi mở rộng theo risk/`docs/VERIFY.md`.

Task repo-local chỉ hoàn thành khi objective/acceptance đạt, verification liên quan đã chạy hoặc caveat rõ, Work Item material state đã persist khi applicable theo `$work-item`, và Knowledge review/write đã xử lý theo policy.
