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

`~` không hợp lệ trong canonical ID components nên separator mapping không tạo collision cú pháp. External-id có phân biệt hoa/thường trong khi filesystem macOS/Windows thường không, vì vậy toàn workspace MUST enforce **casefold-unique directory keys**: trước create/read/write, reject sibling entry khác spelling nhưng có `name.casefold()` trùng directory key dự kiến. Nếu dossier đã tồn tại, `00_WORK_ITEM.md` MUST có front-matter `id` khớp **exact canonical ID** trước khi coi đó là task truth. Sau khi resolve path, MUST verify nó vẫn nằm dưới resolved `<workspace>/work-items`; reject separator/traversal/non-canonical IDs thay vì normalize âm thầm.

## Storage contract

Parent-side canonical path là `<workspace>/work-items`. Resolve `<workspace>` từ active workspace context; khi cần filesystem discovery, walk upward tới nearest directory chứa cả `repos.yaml` và `identity.md`.

Trong delegated runtime, qiqi_delegate mount cùng Work Items root bằng native additional-dir contract. `QIQI_WORK_ITEMS_DIR` chỉ là internal runtime alias; child continuity MUST NOT depend on inheriting env này.

Per task:

```text
<directory-key>/
├── 00_WORK_ITEM.md
├── 10_intake.md?
├── 20_investigation.md?
├── 30_plan.md?
├── 40_review.md?
├── references/?
└── 90_report.textile?
```

Numeric prefixes are part of the canonical filename contract. They make lifecycle order deterministic in file explorers/transcripts and intentionally leave gaps for future material phases. `references/` không đánh số vì nó không phải lifecycle phase.

Legacy unprefixed names (`WORK_ITEM.md`, `intake.md`, `investigation.md`, `plan.md`, `review.md`, `report.textile`) MUST NOT coexist with their numbered canonical targets. Nếu encounter legacy names, migrate the dossier before continuing; do not create a parallel numbered file beside an old one.

`references/` MAY chứa material tra cứu task-specific khi cần. Không tạo mặc định history/turn/execution/checkpoint files.

## Canonical writer

QiQi sở hữu canonical writes. Child MAY read Work Item/lifecycle documents khi tracked-task context được cấp, nhưng không trực tiếp mutate canonical dossier và không tự mark global completion. Child trả material evidence/conclusion/blocker trong native final response; QiQi reconcile rồi rewrite current state.

## `00_WORK_ITEM.md`

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

## Bounded hydration contract

Tracked task **không đồng nghĩa** với hydrate toàn dossier. QiQi MUST establish current-turn scope trước optional lifecycle hydration và MUST dùng bundled bounded reader cho living Work Item documents có thể lớn.

Bundled reader nằm tại `scripts/read.py` tương đối với active `work-item` skill root. Gọi bằng `python3 <work-item-skill-root>/scripts/read.py`; không cần Work Item MCP.

Startup cho existing tracked task:

1. Chạy bounded `00_WORK_ITEM.md` bootstrap bằng `--profile bootstrap`. Surface này chỉ trả front-matter `id/revision/status/phase` cùng Objective, Current Requirements, Acceptance Criteria, Open Questions, Blockers và Current State.
2. Từ current user request + bootstrap, establish **current-turn objective/acceptance slice** trước khi đọc optional lifecycle material. Full product task trong Work Item không tự động mở rộng scope của turn hiện tại.
3. Dùng coverage receipt để biết exact file/sections/range đã quan sát. `complete_file=false` nghĩa là absence ngoài coverage không phải negative evidence.
4. Khi cần lifecycle material, trước tiên có thể dùng `--headings`, sau đó hydrate exact `--section` hoặc bounded `--lines START:END`. Reader không có default full-file mode; line range có hard maximum 120 lines.
5. Reader có hard output budget 8192 bytes. `output_budget_exceeded` phải dẫn tới narrower section/range; không tăng budget hoặc đổi sang broad dump.
6. Nếu một generic filesystem/tool read bị truncation, coi **truncation = incomplete coverage**. Không retry một broad read khác; thu hẹp surface bằng heading/section/range.
7. Khi lifecycle evidence được đọc với known revision, truyền `--expected-revision <n>`. Revision mismatch fail closed và yêu cầu bounded bootstrap lại trước khi promote evidence.

Ví dụ:

```bash
python3 <work-item-skill-root>/scripts/read.py \
  --dossier /absolute/work-items/redmine~116655 \
  --profile bootstrap

python3 <work-item-skill-root>/scripts/read.py \
  --dossier /absolute/work-items/redmine~116655 \
  --file 20_investigation.md \
  --section 'Verified Findings' \
  --section 'Conclusion' \
  --expected-revision 7
```

### Phase-aware hydration matrix

| Current turn | Optional lifecycle hydration | Phase reference |
| --- | --- | --- |
| Stable investigation follow-up, không có material requirement change | Chỉ exact section(s) của `20_investigation.md` khi current slice cần evidence; **không** hydrate `10_intake.md`, `30_plan.md`, `40_review.md` như ceremony | `phases/investigation.md` chỉ khi target/boundary/gate chưa rõ |
| Material requirement change | `10_intake.md` chỉ khi provenance/change context còn material; reconcile prior investigation theo current requirement | `phases/intake.md` mandatory |
| Straightforward implementation/delegation | Exact current evidence cần để tạo TaskPacket; planning/review material không load mặc định | Không đọc planning reference nếu approach obvious/reversible |
| Non-obvious approach/trade-off/verification design | Exact relevant `20_investigation.md` + selected `30_plan.md` surface | `phases/planning.md` just-in-time |
| Acceptance/completion assessment | Selected `40_review.md` + exact acceptance evidence | `phases/review.md` mandatory |
| Report render/verification | Chỉ report material và exact supporting current-state evidence cần cho report | Không hydrate unrelated lifecycle phase |

Scope chỉ được mở rộng ngoài current-turn objective/acceptance slice khi new evidence chứng minh material dependency/boundary cần thiết cho current request. Adjacent historical/task area trong dossier không tự trở thành investigation scope.

## Intake + requirement changes

Khi nhận request đầu tiên:

1. Validate canonical ID và derive safe directory key.
2. Enforce casefold uniqueness trong `<workspace>/work-items`, resolve candidate dossier path và verify path containment, nhưng **không tạo dossier directory mới trước intake gate**.
3. Nếu dossier đã tồn tại, verify exact front-matter `id` trong `00_WORK_ITEM.md` trước khi reuse. Nếu chỉ có legacy unprefixed filenames, migrate trước khi tiếp tục.
4. Read `phases/intake.md` và chạy mandatory intake gate.
5. Với Work Item mới, sau gate MUST materialize một revision-1 `00_WORK_ITEM.md` hợp lệ **trước khi return khỏi turn**, kể cả khi chưa thể tiến hành:
   - `ready` → `status: active`, `phase: intake`; ghi effective requirement/acceptance và có thể tiếp tục investigation sau canonical write.
   - `needs_discovery` → `status: active`, `phase: intake`; ghi current understanding, factual unknowns và exact next discovery action.
   - `needs_user_clarification` → `status: waiting`, `phase: intake`; ghi current understanding, material open question(s) và acceptance/scope đã biết.
   - `blocked` → `status: blocked`, `phase: intake`; ghi blocker/source unavailable và điều kiện unblock.
   Việc materialize tạo dossier directory cùng `00_WORK_ITEM.md`; không để lại empty/orphan dossier.
6. Tạo `10_intake.md` khi original wording/source/material change context có giá trị cho task/report.

Khi có material change request: rerun intake gate, rewrite effective current requirement/current understanding, tăng revision khi state đổi material, và persist gate outcome trước khi pause/continue (`waiting` cho user clarification, `blocked` cho blocker, `active` cho discovery/ready). Giữ trong `10_intake.md` chỉ material change context còn cần, rồi reconcile investigation/plan/review với requirement mới. Original request không phải current truth.

## Multi-turn rule

Multi-turn continuity MUST be represented as **current semantic state**, not chronological turn history. Persist một datum chỉ khi bỏ nó có thể làm turn sau hiểu sai requirement, lặp investigation material, đi sai implementation, đánh giá sai acceptance hoặc report sai. Native session giữ short-term conversational continuity.

## Investigation

`20_investigation.md` là living state: Scope, Verified Findings, Relevant Evidence, Open Questions, Conclusion. Nhiều turn merge/rewrite cùng file; không append turn log.

Nếu target/boundary/ownership/authoritative source đã rõ thì điều tra trực tiếp. Chỉ đọc `phases/investigation.md` khi clarification/discovery boundary thực sự cần.

Requirement change không tự invalidate prior findings. Reconcile từng finding: fact còn đúng → keep; implication đổi → keep + reinterpret; phụ thuộc assumption superseded → revalidate/remove; contradicted by newer authoritative input → replace.

## Plan

`30_plan.md` giữ current approach, remaining steps, risks và verification strategy. Không lưu plan versions. Giữ rejected approach chỉ khi rationale vẫn material để tránh lặp lại.

Nếu approach straightforward, reversible, theo convention và evidence đủ thì không cần planning ceremony. Đọc `phases/planning.md` chỉ khi decision/trade-off materially non-obvious.

## Delegation

TaskPacket vẫn phải đủ nghĩa cho repo-local assignment; Work Item không được dùng như excuse cho incomplete objective/scope/acceptance.

Với tracked Work Item, QiQi SHOULD thêm locator/revision bằng absolute canonical dossier path:

```text
fact: "work_item_path=<absolute-workspace-path>/work-items/<directory-key>; id=<canonical-id>; revision=<revision>"
source: "workspace Work Item"
```

Child đọc `work_item_path/00_WORK_ITEM.md` và relevant numbered lifecycle docs. Không yêu cầu child reconstruct path từ `$QIQI_WORK_ITEMS_DIR` và không yêu cầu env alias survive Herdr server reuse.

Sau child return: nếu runtime state là `blocked`, giữ exact `session_id`, không invent native response, và chỉ RESUME khi exact interactive continuity còn material. Với settled/failed response, so delegated revision với current `00_WORK_ITEM.md`; nếu revision đổi, reconcile finding-by-finding trước khi promote. Persist chỉ material current-state conclusions/evidence/decisions, không lưu transcript/progress log.

## Review + completion

Trước khi mark done hoặc final reporting, MUST đọc `phases/review.md` và chạy acceptance gate. Implementation child nói “done” hoặc test pass riêng lẻ không đủ để mark Work Item done.

Current requirements phải resolved/accepted, acceptance được assessed bằng actual evidence, không còn blocking question, required repo work đã reconciled, required verification/review hoàn tất và required final report đã generated.

`40_review.md` là current acceptance assessment, không phải execution summary.

## Report

Khi workflow yêu cầu report, render `90_report.textile` từ stored current state/evidence, không reconstruct bằng conversation memory. Dùng template tại `templates/90_report.textile`. Không fabricate branch, commit hash, DDL/DML status, test pass hoặc deployment target.

## Shared Knowledge boundary

Work Item là task-specific mutable/current state. Chỉ stable reusable verified conclusion mới là candidate cho Shared Knowledge. Không persist secret, credential, token, customer/private data hoặc raw sensitive evidence vào Work Item, final response hay Shared Knowledge; redact value và giữ tối thiểu locator/type/provenance cần cho investigation.
