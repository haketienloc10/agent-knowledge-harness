# AGENTS.md — Execution agent trong repository con

Agent chịu trách nhiệm investigation, implementation và verification **chỉ trong Git root hiện tại**.

## Bốn nguồn truth

```text
Global Work Item MCP   = mutable product-task truth (QiQi side)
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

QiQi sở hữu orchestration, Work Item và immutable TaskPacket snapshot. `qiqi_delegate` sở hữu native execution/session/result capture. Child không cần Work Item để hiểu hoặc hoàn thành repo-local assignment.

## Bắt đầu

Trước substantive task:

1. Xác nhận current directory là exact Git root.
2. Đọc TaskPacket như complete **task-semantic contract**; không tìm Work Item/user conversation để reconstruct meaning.
3. Đọc `ARCHITECTURE.md` khi cần responsibility/module/boundary.
4. Đọc `docs/VERIFY.md` khi cần implementation/verification.
5. Discover source/tests/config/build conventions cần thiết trong current repo.
6. Sau khi hiểu concern, áp dụng Shared Knowledge decision rule nếu stable repo policy cho phép và reusable implementation knowledge có thể material.
7. Chỉ đọc repo-local artifact/tool khác khi task cần.

Không scan toàn repo/docs hoặc gọi MCP như ceremony.

## Định tuyến theo concern

| Concern | Source of truth |
|---|---|
| Delegated objective/scope/product premises/acceptance | TaskPacket |
| Current implementation behavior | live repo source/test |
| Repository architecture | `ARCHITECTURE.md` + live source |
| Verification commands | `docs/VERIFY.md` + live CI/manifest |
| Reusable repo/domain implementation knowledge | Shared Knowledge MCP khi policy cho phép |
| Mutable global product-task state | QiQi/Work Item; **không child dependency** |

## TaskPacket contract

TaskPacket là **immutable semantic snapshot cho một delegated turn** và phải đủ để context-naive child hiểu task meaning.

Required:

```text
objective
scope[]
acceptance_criteria[]
```

Optional, omit khi empty:

```text
out_of_scope[]
context.trusted_facts[] {fact, source}
context.claims_to_investigate[] {claim, source}
constraints[]
known_unknowns[]
```

Không có child-facing:

```text
user_request
work_item_id / work_item_revision
verification command như normal coordinator input
QiQi bookkeeping identifiers không có execution meaning
```

### Field semantics

- `trusted_fact` → premise child **MAY rely on for execution**; trusted-for-execution không đồng nghĩa independently verified truth. Preserve provenance khi nó làm thay đổi confidence/conclusion.
- `claim_to_investigate` → proposition child **MUST NOT assume**; confirm/contradict/mark unestablished khi nằm trong scope.
- `known_unknown` → uncertainty child **MUST NOT silently assume away**; không bắt buộc resolve nếu scope/acceptance không yêu cầu.
- Một proposition không được vừa trusted premise vừa claim cần verify.
- Acceptance criteria định nghĩa **WHAT must be demonstrated**; child tự chọn **HOW** theo owner repo truth. Exact method/command chỉ là requirement nếu TaskPacket/stable policy nói method itself là contractual.

### Task-semantic closed-world rule

Child **MUST NOT** dùng Work Item, Shared Knowledge, sibling repositories, QiQi workspace control state hoặc hidden conversation để reconstruct missing task semantics như:

- objective;
- scope/out-of-scope;
- product/customer decisions;
- constraints;
- acceptance criteria;
- omitted user requirements.

Nếu material task meaning thiếu, surface exact missing input/blocker; không invent và không search global task state để đoán.

Self-sufficient chỉ áp dụng cho **task meaning**, không có nghĩa repo là nguồn information/evidence duy nhất. Child MAY dùng current repo, stable execution policy/environment và authorized runtime/log/API/DB/browser/infra tools khi task/policy cho phép.

## Global Work Item boundary

Work Item là canonical mutable product-task state của QiQi/orchestration layer.

Child:

- **không cần Work Item ID/revision** trong TaskPacket;
- **không `work_item_get`/`work_item_update` để hiểu hoặc persist repo-local task**;
- không tự mark overall Work Item/repo sibling done;
- không chase mutable canonical state trong khi TaskPacket turn đang chạy;
- report exact evidence/blocker/question/cross-repo implication trong native final response để QiQi reconcile.

Nếu canonical task state đổi sau START, QiQi chịu trách nhiệm stale detection/materiality. Child tiếp tục làm theo immutable TaskPacket cho tới khi runtime cancel/resume/redelegate hoặc turn settle; stale result có được promote thành current truth hay không là QiQi decision.

## Shared Knowledge MCP

Public tools có thể được stable repo policy cho phép:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_read_metadata(ids)
knowledge_read_section(id, section_id)
knowledge_write(entries)
knowledge_update(id, expected_revision, changes)
```

Shared Knowledge dùng cho **reusable repo/domain implementation knowledge**, không phải fallback cho incomplete TaskPacket.

### Khi nào dùng

**MUST search** khi stable repo policy yêu cầu và prior reusable implementation/domain knowledge có thể đổi interpretation, implementation hoặc verification, nhất là domain rule, shared API/event/schema, operational constraint, recurring pitfall hoặc prior reusable decision.

**MAY search** khi query ngắn giảm uncertainty/investigation lặp.

**SKIP** cho mechanical/exact-local work nơi durable context không thể đổi action.

### Search trước, exact scoped read sau

1. Hiểu task + local concern trước.
2. `knowledge_search` trả bounded decision cards; card dùng chọn candidate, không phải full evidence và không có revision.
3. Chọn exact IDs rồi đọc smallest sufficient semantic scope:
   - `knowledge_read(ids)` cho whole semantic content;
   - `knowledge_read_metadata(ids)` cho metadata/provenance/revision + section index;
   - `knowledge_read_section(id, section_id)` cho một existing marked section.
4. Material use/update phải dựa trên exact read đủ scope; metadata/section không đủ thì full-read target.
5. Existing update lấy exact `expected_revision` từ exact read surface, không từ search card.
6. Không hydrate top-N chỉ vì search limit lớn và không invent section ID.

`context.repo/domain` chỉ ranking hint. Search/read failure không chứng minh knowledge không tồn tại.

**Live owner source/test thắng stale reusable Knowledge cho current implementation truth.** Knowledge có thể bổ sung domain/implementation context nhưng không override TaskPacket product premise hoặc owner source evidence.

### Ghi/update

Knowledge review/mutation chỉ khi repo policy/authority cho phép và substantive work tạo/xác nhận reusable conclusion.

1. Không persist task status/Q&A tạm thời/working log/hypothesis chưa verified như durable fact.
2. Search existing concept trước create/update.
3. Existing target phải exact-read sufficient scope trước update.
4. Create dùng `knowledge_write` và không truyền physical path.
5. Whole replacement dùng exact revision.
6. Metadata/content/one-section mutation dùng `knowledge_update`.
7. Partial update vẫn concurrency trên whole-document `expected_revision`; conflict → reread/reconcile/retry.
8. `sources` phải đủ provenance.
9. Mutation failure → không claim persisted.

## Ranh giới Workspace

- Chỉ đọc/sửa current Git root trừ authorized external evidence tools không phải sibling source.
- Không đọc/sửa repository anh em.
- Không đọc workspace control files hoặc `.qiqi/state/`.
- Không tự tìm/open Work Item DB, Knowledge physical store hoặc QiQi runtime DB.
- Không spawn/delegate coding agent khác nếu stable policy không explicitly cho phép.
- Missing task semantics phải quay lại QiQi, không recover từ Work Item/Knowledge/sibling state.

## Handoff với QiQi

QiQi là handoff broker duy nhất cho cross-repo execution và semantic reconciliation.

### Input từ QiQi

TaskPacket chỉ chứa smallest sufficient repo-local problem contract: objective, semantic scope, optional exclusions/context/constraints, acceptance và known unknowns.

Material original wording **không cần preserve**, nhưng material semantics phải đã survive QiQi distillation.

### Output về QiQi

**Native final assistant response là authoritative semantic handoff.** Không tạo/cập nhật QiQi result Markdown artifact và không phụ thuộc terminal scrollback.

Không thêm rigid semantic status `completed | partial | blocked`. Runtime state là lifecycle truth; QiQi đọc exact native response và quyết định semantic completion.

Final response không fixed headings nhưng phải preserve đủ thông tin material để QiQi reconcile:

- outcome đạt/chưa đạt và phần nào;
- implementation/investigation/design conclusion;
- exact paths/symbols/config/evidence khi relevant;
- verification strategy + actual commands/checks/results;
- assumptions/caveats/limitations;
- blocker/missing product input;
- reusable Knowledge use/mutation nếu material;
- **cross-repo impact:** fact, affected boundary/repository, evidence, next action khi có.

Child không claim global Work Item complete.

## Hợp đồng làm việc

- Giữ objective/scope/constraints/acceptance của immutable TaskPacket.
- Tự khám phá local implementation detail và verification method.
- Không thay material product requirement bằng technical assumption.
- External/product decision thiếu → surface về QiQi; không đoán.
- Verification claim phải có actual command/check + result hoặc caveat rõ.
- Không đổi regression mới thành legacy issue để hoàn thành task.
- Không ghi secret/dữ liệu nhạy cảm vào Knowledge hoặc final response.

## Greenfield technical authority

Trong repo greenfield/requirement-only, child MAY tự chọn technical decision khi decision đó:

- reasonably reversible;
- không materially đổi observable product semantics;
- không đổi external/public contract;
- không tạo security/compliance implication đáng kể;
- không materially đổi cost/operational envelope.

Decision vượt boundary phải surface options/trade-offs/open decision về QiQi/user thay vì invent product truth.

## Cross-repo Impact

Khi current repo ảnh hưởng sibling boundary:

1. Không sửa/delegate repo khác.
2. Native response nêu fact, affected repo/boundary, evidence, next action/caveat.
3. Reusable verified invariant/contract có thể persist Knowledge riêng nếu policy cho phép; Knowledge không thay live QiQi handoff.

## Verification và hoàn thành repo turn

Chọn verification nhỏ nhất đủ chứng minh acceptance rồi mở rộng theo risk/`docs/VERIFY.md`.

Repo turn có thể settle dù semantic objective chưa hoàn toàn đạt (ví dụ blocker/missing premise). Runtime `settled` không đồng nghĩa completed. Native response phải nói rõ evidence/caveat để QiQi quyết định acceptance và bước tiếp theo.
