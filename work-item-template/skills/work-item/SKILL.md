---
name: work-item
description: >
  Filesystem-native protocol for tracking a task from request through investigation,
  implementation, verification and final report. Use for an identified tracked task,
  when the user asks to track a task, or when continuing an existing workspace Work Item dossier.
---

# Work Item lifecycle protocol

Work Item là shared **current-state task dossier** dưới `<workspace>/work-items/`. Không dùng MCP/SQLite và không biến Work Item thành execution history.

## Activation

Apply khi request có canonical/tracked task ID cần theo dõi xuyên turn, user yêu cầu tạo/dùng Work Item, conversation tiếp tục existing dossier, hoặc workflow yêu cầu final report từ task state/evidence. Không tự tạo Work Item cho mọi câu hỏi nhỏ/mechanical task.

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

`~` không hợp lệ trong canonical ID components nên separator mapping không tạo collision cú pháp. Tuy nhiên external-id có phân biệt hoa/thường trong khi filesystem macOS/Windows thường không. Vì vậy toàn workspace MUST enforce **casefold-unique directory keys**: trước create/read/write, reject nếu một sibling entry khác spelling nhưng có `name.casefold()` trùng directory key dự kiến. Nếu dossier đã tồn tại, `WORK_ITEM.md` MUST có front-matter `id` khớp **exact canonical ID** trước khi coi đó là task truth. Sau khi resolve path, MUST verify nó vẫn nằm dưới resolved `<workspace>/work-items`; reject separator/traversal/non-canonical IDs thay vì normalize âm thầm.

## Storage contract

Parent-side canonical path là `<workspace>/work-items`, không phụ thuộc vào env do MCP child process export. Resolve `<workspace>` từ active workspace context; khi cần filesystem discovery, walk upward tới nearest directory chứa cả `repos.yaml` và `identity.md`.

Trong delegated runtime, qiqi_delegate mount cùng Work Items root bằng native `--add-dir`. `QIQI_WORK_ITEMS_DIR` chỉ là internal runtime alias của qiqi_delegate; child continuity MUST NOT depend on inheriting env này.

Per task:

```text
<directory-key>/
├── WORK_ITEM.md
├── intake.md?
├── investigation.md?
├── plan.md?
├── review.md?
└── report.textile?
```

Không tạo mặc định history/turn/execution/checkpoint files.

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

## Phase clarification gates

`$work-item` là lifecycle/orchestration skill. Bốn skill bổ trợ chỉ làm rõ uncertainty ở đúng phase và MUST NOT tạo thêm lifecycle/history files hoặc tự mutate canonical dossier:

- `$work-item-intake` — **mandatory** cho initial tracked intake và material requirement change; làm rõ understanding, scope, acceptance, terminology và requirement ambiguity.
- `$work-item-investigate` — **conditional** khi investigation target/ownership/repository-module boundary hoặc authoritative source chưa rõ.
- `$work-item-plan` — **conditional** khi approach/trade-off/risk/verification strategy materially non-obvious trước implementation.
- `$work-item-review` — **mandatory** trước completion/reporting; assess acceptance bằng actual evidence và xác định deviation/blocking question.

Các gate dùng vocabulary chung:

```text
ready
needs_user_clarification
needs_discovery
blocked
```

`needs_discovery` nghĩa là agent còn factual/technical/evidence work có thể tự làm mà chưa cần user decision. Với review, nó có thể bao gồm verify, reproduce, fix, gather evidence hoặc re-investigate trước khi acceptance được quyết định.

Nguyên tắc chung: **clarify meaning, not mechanics**. Ask user cho intent/product/domain semantics/material scope/acceptance/irreversible or external-contract trade-off. Tự discover factual/module/repository details. Tự chọn normal reversible implementation detail khi evidence và repo conventions đủ rõ.

Phase skill trả assessment cho `$work-item`; QiQi reconcile only material current truth vào `WORK_ITEM.md`, `intake.md`, `investigation.md`, `plan.md`, `review.md`. Không persist clarification transcript, question/answer chronology hoặc routine reasoning.

## Intake + requirement changes

Khi nhận request đầu tiên:

1. Validate canonical ID và derive safe directory key.
2. Enforce casefold uniqueness trong `<workspace>/work-items`, resolve/create dossier và verify path containment.
3. Nếu dossier tồn tại, verify exact front-matter `id` trước khi reuse.
4. Apply `$work-item-intake` và chỉ canonicalize requirement khi gate cho phép; material user clarification được reconcile thành current truth, không thành transcript.
5. Materialize `WORK_ITEM.md` revision 1 từ effective requirement.
6. Tạo `intake.md` khi original wording/source/material change context có giá trị cho task/report.

Khi có change request: apply intake clarification cho material meaning change, rewrite effective current requirement, tăng revision, giữ trong `intake.md` chỉ material change context còn cần, rồi reconcile investigation/plan/review với requirement mới. Original request không phải current truth.

## Multi-turn rule

Multi-turn continuity MUST be represented as **current semantic state**, not chronological turn history. Persist một datum chỉ khi bỏ nó có thể làm turn sau hiểu sai requirement, lặp investigation material, đi sai implementation, đánh giá sai acceptance hoặc report sai. Native session giữ short-term conversational continuity.

## Investigation

`investigation.md` là living state: Scope, Verified Findings, Relevant Evidence, Open Questions, Conclusion. Nhiều turn merge/rewrite cùng file; không append turn log.

Nếu target/boundary/ownership chưa rõ, apply `$work-item-investigate`; không hỏi user về facts mà repo/docs/tests/config có thể tự establish. Requirement change không tự invalidate prior findings. Reconcile từng finding: fact còn đúng → keep; implication đổi → keep + reinterpret; phụ thuộc assumption superseded → revalidate/remove; contradicted by newer authoritative input → replace.

## Plan

`plan.md` giữ current approach, remaining steps, risks và verification strategy. Không lưu plan versions. Giữ rejected approach chỉ khi rationale vẫn material để tránh lặp lại.

Nếu approach/trade-off materially non-obvious, apply `$work-item-plan`. Technical reversible choice thuộc agent khi evidence đủ; product behavior/public contract/data semantics/irreversible decision cần user khi requirement chưa quyết định.

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

Implementation child nói “done” không đủ để mark Work Item done. Apply `$work-item-review` trước completion/reporting. Trước completion, current requirements phải resolved/accepted, acceptance được assessed bằng actual evidence, không còn blocking question, required repo work đã reconciled, required verification/review hoàn tất và required final report đã generated.

`review.md` là current acceptance assessment, không phải execution summary. Distinguish implemented, verified và accepted; test pass đơn lẻ không tự chứng minh mọi acceptance criterion.

## Report

Khi workflow yêu cầu report, render `report.textile` từ stored current state/evidence, không reconstruct bằng conversation memory. Dùng template tại `templates/report.textile`. Không fabricate branch, commit hash, DDL/DML status, test pass hoặc deployment target.

## Shared Knowledge boundary

Work Item là task-specific mutable/current state. Chỉ stable reusable verified conclusion mới là candidate cho Shared Knowledge. Không persist secret, credential, token, customer/private data hoặc raw sensitive evidence vào Work Item, final response hay Shared Knowledge; redact value và giữ tối thiểu locator/type/provenance cần cho investigation.
