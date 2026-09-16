---
name: work-item
description: >
  Workspace-scoped filesystem-native protocol for tracking a task from request through
  investigation, planning, implementation orchestration, verification and final report.
  Use for an identified tracked task when running as the workspace QiQi parent/canonical
  writer. Repository execution children read mounted Work Item context but do not run
  this lifecycle or mutate the canonical dossier.
---

# Work Item lifecycle protocol

Work Item là shared **current-state task dossier** dưới `<workspace>/work-items/`. Không dùng MCP/SQLite cho runtime mới và không biến Work Item thành execution history.

## Role boundary

`$work-item` là **workspace/QiQi protocol**, không phải repo-child execution protocol.

- QiQi ở workspace root sở hữu intake, product-task continuity, phase transitions, canonical writes, cross-repo reconciliation và final completion.
- Repository child nhận TaskPacket, MAY đọc mounted Work Item/lifecycle docs và trả evidence/conclusion/blocker về QiQi.
- Repository child MUST NOT rewrite canonical dossier, tự chạy lifecycle để thay product truth, hoặc tự mark global task done.
- Nếu execution child nhìn thấy skill do môi trường ngoài workspace inject, repo `AGENTS.md` boundary vẫn thắng: dùng TaskPacket + read-only Work Item context, không activate canonical lifecycle.

## Activation

Apply khi QiQi đang ở workspace context và request có canonical/tracked task ID cần theo dõi xuyên turn, user yêu cầu tạo/dùng Work Item, conversation tiếp tục existing dossier, hoặc workflow yêu cầu final report từ task state/evidence. Không tự tạo Work Item cho mọi câu hỏi nhỏ/mechanical task.

## Stable ID + directory key

Canonical Work Item ID MUST match:

```text
^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$
```

Ví dụ: `redmine:116655`.

Không dùng raw ID làm filesystem path. Sau khi validate, derive directory key bằng cách thay **colon separator đầu tiên** bằng separator `~`:

```text
redmine:116655 -> redmine~116655
```

`~` không hợp lệ trong canonical ID components nên separator mapping không tạo collision cú pháp. External-id có phân biệt hoa/thường trong khi filesystem macOS/Windows thường không, vì vậy toàn workspace MUST enforce **casefold-unique directory keys**: trước create/read/write, reject sibling entry khác spelling nhưng có `name.casefold()` trùng directory key dự kiến. Nếu dossier đã tồn tại, `WORK_ITEM.md` MUST có front-matter `id` khớp **exact canonical ID** trước khi coi đó là task truth. Sau khi resolve path, MUST verify nó vẫn nằm dưới resolved `<workspace>/work-items`; reject separator/traversal/non-canonical IDs thay vì normalize âm thầm.

## Storage contract

Parent-side canonical path là `<workspace>/work-items`. Resolve `<workspace>` từ active workspace context; khi cần filesystem discovery, walk upward tới nearest directory chứa cả `repos.yaml` và `identity.md`.

Trong delegated runtime, qiqi_delegate mount cùng Work Items root bằng native additional-dir contract. `QIQI_WORK_ITEMS_DIR` chỉ là internal runtime alias; child continuity MUST NOT depend on inheriting env này.

Per task:

```text
<directory-key>/
├── WORK_ITEM.md
├── intake.md?
├── investigation.md?
├── plan.md?
├── review.md?
├── references/?
└── report.textile?
```

`references/` MAY chứa material tra cứu task-specific khi cần. Không tạo mặc định history/turn/execution/checkpoint files.

## Canonical writer

QiQi sở hữu canonical writes. Child MAY read Work Item/lifecycle documents khi tracked-task context được cấp, nhưng không trực tiếp mutate canonical dossier và không tự mark global completion. Child trả material evidence/conclusion/blocker trong native final response; QiQi reconcile rồi rewrite current state.

## `WORK_ITEM.md`

Phải giữ tối thiểu:

```yaml
---
id: <canonical-id>
revision: <integer >= 1>
status: active | waiting | blocked | done | cancelled
phase: intake | investigation | planning | implementation | verification | reporting
---
```

Body current-state đề nghị: Objective, Current Requirements, Acceptance Criteria, Scope, Decisions, Open Questions, Blockers, Current State, Next Actions. `revision` tăng khi canonical task meaning hoặc completion-relevant state đổi material.

Legacy-imported dossier có thể chứa `legacy_reconciliation_required: true`. Khi flag này còn true, QiQi MUST đọc protected migration archive được dossier trỏ tới và reconcile material legacy metadata/acceptance/provenance trước substantive implementation, completion assessment hoặc final report; sau reconciliation rewrite current state, tăng revision và bỏ flag. Không để archive trở thành runtime history source sau khi reconciliation hoàn tất.

## Phase model + gate vocabulary

Phase clarification là **internal modes của một `$work-item` skill**, không phải các skill độc lập. Chỉ đọc phase reference cần cho action hiện tại:

- `phases/intake.md` — mandatory gate cho Work Item mới và material requirement change.
- `phases/investigation.md` — conditional gate khi ownership/boundary/authoritative source/first target chưa rõ.
- `phases/planning.md` — conditional decision gate khi approach/trade-off/risk/verification materially non-obvious.
- `phases/review.md` — mandatory acceptance gate trước completion/reporting.

Gate vocabulary chung:

```text
ready
needs_user_clarification
needs_discovery
blocked
```

Core decision rule: **clarify meaning, not mechanics**.

- Thiếu user/product/domain intent hoặc material acceptance/irreversible external-contract decision → hỏi user.
- Thiếu factual/repository/module/evidence fact có thể discover → `needs_discovery`, agent tự điều tra.
- Normal reversible implementation choice có đủ evidence/convention → agent tự quyết và ghi rationale khi material.
- External dependency/source unavailable làm không thể tiến hành → `blocked`.

Không load cả bốn phase references như startup ceremony. Read just-in-time theo phase/gate cần thiết.

## Intake + requirement changes

Khi nhận request đầu tiên:

1. Validate canonical ID và derive safe directory key.
2. Enforce casefold uniqueness trong `<workspace>/work-items`, resolve/create dossier và verify path containment.
3. Nếu dossier tồn tại, verify exact front-matter `id` trước khi reuse.
4. Read `phases/intake.md` và chạy mandatory intake gate.
5. Nếu gate cho phép tiến hành, materialize/rewrite `WORK_ITEM.md` từ effective requirement.
6. Tạo `intake.md` khi original wording/source/material change context có giá trị cho task/report.

Khi có material change request: rerun intake gate, rewrite effective current requirement, tăng revision, giữ trong `intake.md` chỉ material change context còn cần, rồi reconcile investigation/plan/review với requirement mới. Original request không phải current truth.

## Multi-turn rule

Multi-turn continuity MUST be represented as **current semantic state**, not chronological turn history. Persist một datum chỉ khi bỏ nó có thể làm turn sau hiểu sai requirement, lặp investigation material, đi sai implementation, đánh giá sai acceptance hoặc report sai. Native session giữ short-term conversational continuity.

## Investigation

`investigation.md` là living state: Scope, Verified Findings, Relevant Evidence, Open Questions, Conclusion. Nhiều turn merge/rewrite cùng file; không append turn log.

Nếu target/boundary/ownership/authoritative source đã rõ thì điều tra trực tiếp. Chỉ đọc `phases/investigation.md` khi clarification/discovery boundary thực sự cần.

Requirement change không tự invalidate prior findings. Reconcile từng finding: fact còn đúng → keep; implication đổi → keep + reinterpret; phụ thuộc assumption superseded → revalidate/remove; contradicted by newer authoritative input → replace.

## Plan

`plan.md` giữ current approach, remaining steps, risks và verification strategy. Không lưu plan versions. Giữ rejected approach chỉ khi rationale vẫn material để tránh lặp lại.

Nếu approach straightforward, reversible, theo convention và evidence đủ thì không cần planning ceremony. Đọc `phases/planning.md` chỉ khi decision/trade-off materially non-obvious.

## Delegation

TaskPacket vẫn phải đủ nghĩa cho repo-local assignment; Work Item không được dùng như excuse cho incomplete objective/scope/acceptance.

Với tracked Work Item, QiQi SHOULD thêm locator/revision bằng absolute canonical dossier path:

```text
fact: "work_item_path=<absolute-workspace-path>/work-items/<directory-key>; id=<canonical-id>; revision=<revision>"
source: "workspace Work Item"
```

Child đọc `work_item_path/WORK_ITEM.md` và relevant lifecycle docs. Không yêu cầu child reconstruct path từ `$QIQI_WORK_ITEMS_DIR` và không yêu cầu env alias survive Herdr server reuse.

Sau child return: nếu runtime state là `blocked`, giữ exact `session_id`, không invent native response, và chỉ RESUME khi exact interactive continuity còn material. Với settled/failed response, so delegated revision với current `WORK_ITEM.md`; nếu revision đổi, reconcile finding-by-finding trước khi promote. Persist chỉ material current-state conclusions/evidence/decisions, không lưu transcript/progress log.

## Review + completion

Trước khi mark done hoặc final reporting, MUST đọc `phases/review.md` và chạy acceptance gate. Implementation child nói “done” hoặc test pass riêng lẻ không đủ để mark Work Item done.

Current requirements phải resolved/accepted, acceptance được assessed bằng actual evidence, không còn blocking question, required repo work đã reconciled, required verification/review hoàn tất và required final report đã generated.

`review.md` là current acceptance assessment, không phải execution summary.

## Report

Khi workflow yêu cầu report, render `report.textile` từ stored current state/evidence, không reconstruct bằng conversation memory. Dùng template tại `templates/report.textile`. Không fabricate branch, commit hash, DDL/DML status, test pass hoặc deployment target.

## Shared Knowledge boundary

Work Item là task-specific mutable/current state. Chỉ stable reusable verified conclusion mới là candidate cho Shared Knowledge. Không persist secret, credential, token, customer/private data hoặc raw sensitive evidence vào Work Item, final response hay Shared Knowledge; redact value và giữ tối thiểu locator/type/provenance cần cho investigation.
