# Thiết lập Repository con cho QiQi Workspace

Repo agent dùng các nguồn truth theo boundary rõ ràng:

```text
TaskPacket            = delegated task semantics
Repo source/test      = current implementation truth
Knowledge MCP         = reusable implementation/domain knowledge khi policy cho phép
qiqi_delegate state   = runtime/session truth
Global Work Item MCP  = mutable product-task truth thuộc QiQi side
```

## Kết quả cần đạt

- `AGENTS.md` bảo vệ Git-root/sibling boundaries;
- child hiểu assignment từ **immutable TaskPacket** mà không cần Work Item/user conversation;
- child tự discover source/test/build/verification trong current repo;
- Shared Knowledge chỉ dùng cho reusable implementation/domain knowledge, không reconstruct missing task semantics;
- authorized runtime/log/API/DB/browser evidence vẫn được phép khi task/policy cần;
- native final assistant response là semantic handoff về QiQi;
- `bash scripts/repo-check.sh` PASS.

## 1. Xác nhận Git root

```bash
pwd
git rev-parse --show-toplevel
git status --short
```

Template phải ở exact Git root.

## 2. TaskPacket behavior

TaskPacket là immutable semantic snapshot cho một delegated turn.

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

Không có normal child-facing `user_request`, Work Item ID/revision hoặc `verification` command field.

- `trusted_fact`: execution premise child MAY rely on; provenance vẫn phải preserve khi ảnh hưởng confidence.
- `claim_to_investigate`: child MUST NOT assume; establish/contradict/unresolved theo scope.
- `known_unknown`: không silently assume away.
- Acceptance nói WHAT phải chứng minh; child discover HOW từ repo/policy. Exact method chỉ bắt buộc khi method itself là contractual requirement.

## 3. Work Item boundary

Work Item là mutable product/orchestration state của QiQi.

Child không cần và không dùng `work_item_get`/`work_item_update` để reconstruct hoặc persist repo-local assignment. Task có Work Item và task không Work Item phải có **child-facing semantics tương đương** khi objective/scope/acceptance giống nhau.

Nếu canonical state đổi trong lúc child chạy, TaskPacket không mutate. QiQi sở hữu stale detection/materiality và quyết định cancel/interrupt/resume/redelegate/reconcile. Materially stale result không được QiQi promote thành current truth.

Work Item MCP có thể vẫn được cài user-scope cho hệ thống chung, nhưng nó không phải execution dependency của repository child.

## 4. Task-semantic closed world

Child MUST NOT dùng Work Item, Shared Knowledge, sibling repo hoặc QiQi workspace state để infer objective/scope/product decision/constraint/acceptance bị thiếu.

Nếu thiếu material task semantics:

```text
surface exact missing input/blocker
→ return/resume through QiQi
```

không phải:

```text
search Work Item/Knowledge
→ reconstruct what user probably meant
```

Self-sufficient chỉ áp dụng cho **task meaning**. Execution có thể dùng current repo, stable execution policy/environment và authorized runtime/log/API/DB/browser/infra evidence khi task/policy cho phép.

## 5. Knowledge progressive disclosure

Knowledge chỉ là legitimate child source khi concern reusable implementation/domain knowledge xuất hiện trong execution và stable policy cho phép.

1. hiểu local concern trước;
2. `knowledge_search` nhận thin decision cards;
3. chọn exact candidate;
4. exact-read smallest sufficient scope:
   - `knowledge_read(ids)` khi cần full content;
   - `knowledge_read_metadata(ids)` khi cần metadata/provenance/revision + section index;
   - `knowledge_read_section(id, section_id)` khi cần một marked section;
5. không dùng search card như full evidence và không lấy revision từ search;
6. live owner source/test thắng stale Knowledge cho current implementation;
7. nếu mutation được policy cho phép, search dedupe + exact-read target trước `knowledge_write`/`knowledge_update` và dùng whole-document revision concurrency.

Knowledge **không phải fallback cho incomplete TaskPacket**.

## 6. Greenfield planning

Trong requirement-only repo, child có thể tự chọn reversible technical decision nếu không materially đổi:

- observable product semantics;
- public/external contract;
- security/compliance semantics;
- significant cost/operational envelope.

Decision vượt boundary phải surface options/trade-offs/open decision về QiQi/user.

## 7. Verification

Child đọc `docs/VERIFY.md`, source/tests/manifests/CI config rồi chọn verification strategy phù hợp. Final response report actual commands/checks/results và caveat.

TaskPacket acceptance criteria không mặc định prescribe unit/integration framework hoặc exact command.

## 8. Native handoff

Native final assistant response là authoritative semantic handoff. Không fixed result headings, result path hoặc Markdown transport artifact.

Runtime state `settled | failed | blocked` chỉ mô tả execution lifecycle; không phải semantic completion. QiQi đọc native response và quyết định task outcome/completion.

Final response giữ đủ:

- outcome/evidence;
- changed/discovered/design facts;
- verification result;
- blocker/missing premise;
- assumptions/caveats;
- cross-repo implication;
- Knowledge use/mutation khi material.

## 9. Checker

```bash
bash scripts/repo-check.sh
```

Checker xác nhận TaskPacket semantic boundary, Work Item independence, legitimate Knowledge usage, current-repo isolation và native-result handoff.

## 10. Fresh-session smoke

1. Delegate same repo-local assignment một lần không Work Item và một lần tracked bởi Work Item; child-facing task meaning phải tương đương.
2. Child bắt đầu bằng TaskPacket + current repo/stable policy, không `work_item_get`.
3. Missing acceptance/product premise → child surface blocker; không search Work Item/Knowledge để recover meaning.
4. Child discover legacy connector rồi dùng `knowledge_search`/exact read nếu repo policy cho phép; việc đó chỉ bổ sung implementation knowledge.
5. Owner source/test thắng stale Knowledge cho current implementation.
6. Runtime/external evidence task có thể dùng authorized log/API/DB/browser tool mà không vi phạm TaskPacket self-sufficiency.
7. Verification strategy do child discover; exact result report trong native final response.
8. Child không mở sibling repo/workspace runtime state.
9. Native response quay lại QiQi; runtime `settled` không tự động nghĩa semantic completed.
