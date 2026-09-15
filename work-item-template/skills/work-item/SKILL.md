---
name: work-item
description: >
  Filesystem-native protocol for tracking a task from request through investigation,
  implementation, verification and final report. Use for an identified tracked task,
  when the user asks to track a task, or when continuing an existing work-items/<id> dossier.
---

# Work Item lifecycle protocol

Work Item là shared **current-state task dossier** tại `$QIQI_WORK_ITEMS_DIR/<id>/`. Không dùng MCP/SQLite và không biến Work Item thành execution history.

## Activation

Apply khi:

- request có canonical/tracked task ID cần theo dõi xuyên turn;
- user yêu cầu tạo/dùng Work Item;
- conversation tiếp tục một existing `$QIQI_WORK_ITEMS_DIR/<id>`;
- workflow yêu cầu final report từ task state/evidence.

Không tự tạo Work Item cho mọi câu hỏi nhỏ/mechanical task.

## Storage contract

`QIQI_WORK_ITEMS_DIR` phải trỏ tới workspace `work-items/` và được runtime mount cho supported child agents.

Per task:

```text
<id>/
├── WORK_ITEM.md
├── intake.md? 
├── investigation.md?
├── plan.md?
├── review.md?
└── report.textile?
```

Không tạo mặc định history/turn/execution/checkpoint files.

## Canonical writer

QiQi sở hữu canonical writes. Child MAY read Work Item/lifecycle documents khi tracked-task context được cấp, nhưng không trực tiếp mutate canonical dossier và không tự mark global completion. Child trả exact evidence/conclusion/blocker trong native final response; QiQi reconcile rồi rewrite current state.

## `WORK_ITEM.md`

Phải giữ tối thiểu:

```yaml
---
id: <stable-id>
revision: <integer >= 1>
status: active | blocked | done | cancelled
phase: intake | investigation | planning | implementation | verification | reporting
---
```

Body current-state đề nghị:

```text
Objective
Current Requirements
Acceptance Criteria
Scope
Decisions
Open Questions
Blockers
Current State
Next Actions
```

Chỉ giữ current semantic state. `revision` tăng khi canonical task meaning hoặc completion-relevant state đổi material.

## Intake + requirement changes

Khi nhận request đầu tiên:

1. Resolve/create `<id>/`.
2. Materialize `WORK_ITEM.md` revision 1 từ effective requirement.
3. Tạo `intake.md` khi original wording/source/material change context có giá trị cho task/report.

Khi có change request:

- rewrite `WORK_ITEM.md` thành **effective current requirement**;
- tăng revision;
- `intake.md` chỉ giữ material change context còn cần, không append chronology;
- reconcile investigation/plan/review với requirement mới.

Original request không phải current truth.

## Multi-turn rule

Multi-turn continuity MUST be represented as **current semantic state**, not chronological turn history.

Trước khi persist một datum, hỏi:

> Nếu bỏ datum này, turn sau có thể hiểu sai requirement, lặp investigation material, đi sai implementation, đánh giá sai acceptance hoặc report sai không?

Nếu không → không persist.

Native session giữ short-term conversational continuity; Work Item chỉ giữ durable material continuity.

## Investigation

`investigation.md` là living state:

```text
Scope
Verified Findings
Relevant Evidence
Open Questions
Conclusion
```

Nhiều turn merge/rewrite cùng file. Không append “turn 1/2/3”.

Requirement change không tự invalidate prior findings. Reconcile từng finding:

- still factually valid → keep;
- valid but solution implication changed → keep + reinterpret;
- dependent on superseded assumption → revalidate/remove;
- contradicted by newer authoritative input → replace.

## Plan

`plan.md` giữ current approach, remaining steps, risks và verification strategy. Không lưu plan versions. Giữ rejected approach chỉ khi rationale vẫn material để tránh lặp lại.

## Delegation

TaskPacket vẫn phải đủ nghĩa cho repo-local assignment; Work Item không được dùng như excuse cho incomplete objective/scope/acceptance.

Với tracked Work Item, QiQi SHOULD thêm một `context.trusted_facts` locator:

```text
fact: "work_item=<id>; revision=<revision>"
source: "QIQI_WORK_ITEMS_DIR"
```

Child có thể đọc `$QIQI_WORK_ITEMS_DIR/<id>/WORK_ITEM.md` và relevant lifecycle documents để lấy current durable continuity, nhưng assignment semantics vẫn do TaskPacket định nghĩa.

Sau child return:

1. Đọc exact native response.
2. So delegated revision với current `WORK_ITEM.md` revision.
3. Nếu revision đổi, reconcile materiality/finding-by-finding trước khi promote.
4. Persist chỉ conclusions/evidence/decisions làm đổi current task understanding hoặc acceptance.
5. Không lưu turn transcript/progress log.

## Review + completion

Implementation child nói “done” không đủ để mark Work Item done.

Trước completion:

- current requirements đã resolved hoặc explicitly accepted otherwise;
- acceptance criteria đã được assessed bằng actual evidence;
- không còn blocking question;
- required repo work đã reconciled;
- required verification/review đã hoàn tất;
- required final report đã generated.

`review.md` là current acceptance assessment, không phải execution summary.

## Report

Khi workflow yêu cầu report, render `report.textile` từ stored current state/evidence. Không reconstruct bằng conversation memory.

Dùng template đi kèm tại `templates/report.textile`. Không fabricate branch, commit hash, DDL/DML status, test pass hoặc deployment target. Preserve explicit user-fill placeholders khi value chưa biết.

## Shared Knowledge boundary

Work Item là task-specific mutable/current state. Chỉ stable reusable verified conclusion mới là candidate cho Shared Knowledge. Không đưa routine task progress, one-off decision hoặc working hypothesis vào Knowledge.
