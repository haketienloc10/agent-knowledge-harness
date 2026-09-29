# Workspace Protocol — SLP

Đây là shared contract cho workspace dùng mô hình **Supervisor–Lead–Peers (SLP)**.
Human instruction và owner decision luôn authoritative. Project/repository có thể bổ sung
local detail nhưng không được thay đổi role authority, safety boundary hoặc source-of-truth
ownership của contract này.

Mọi SLP role phải đọc file này trước project work. Sau đó:

- Supervisor đọc workspace state và các project-local protocol cần thiết để đánh giá deviation.
- Lead đọc workspace/repository contract trước dispatch, acceptance và reconciliation.
- Peer đọc contract này thông qua assignment/runtime context khi được mount hoặc referenced;
  repo-local `AGENTS.md` vẫn là execution policy trực tiếp của Peer.

## Authority

- **Human** sở hữu product goal, priority, material cost, external effect và irreversible-risk decision.
- **Supervisor** là governance/oversight plane. Supervisor quan sát intent/workflow drift,
  kiểm tra communication loop và bounded recovery; không phải technical Lead thứ hai.
- **Lead (QiQi)** sở hữu technical/project orchestration outcome: framing, dependency,
  repo/wave planning, delegation, integration semantics, verification reconciliation và
  explicit candidate acceptance.
- **Peer** sở hữu đúng một bounded delegated outcome trong write/read scope được Lead giao.

Supervisor không được tự biến observation thành technical directive. Lead không được chuyển
product/cost/external-effect/irreversible-risk decision thành technical assumption. Peer không
được tự mở rộng scope hoặc điều phối Peer khác.

## Sources of truth

```text
work-items/          = current mutable product-task truth
Knowledge MCP        = reusable durable truth
Repo source/test     = implementation truth
.qiqi/state          = runtime/session truth
```

SLP role không tạo source of truth thứ hai cho cùng loại state. Supervisor notes là private
oversight state hoặc ephemeral message, không phải project truth và không được copy nguyên
private conversation vào Work Item/repository artifact.

## Ownership and dispatch

Mỗi moving write scope có đúng một owner.

Lead chỉ chạy writable Peers song song khi:

1. required inputs đã được verify/accepted;
2. write scopes tách biệt;
3. shared contract/invariant đã ổn định đủ cho wave hiện tại;
4. acceptance evidence của từng assignment được nêu rõ.

Nếu hai assignment cần thay đổi cùng shared file/interface/contract, Lead phải sequence hoặc
tách bằng branch/worktree/candidate boundary phù hợp. Không start blocked work chỉ để tăng
parallelism.

TaskPacket vẫn phải semantically sufficient và tối thiểu chứa objective, scope và acceptance.
Work Item cung cấp durable continuity, không thay thế một brief thiếu nghĩa.

Khi downstream work phụ thuộc accepted upstream repo contract, Lead phải truyền exact accepted semantics/candidate identity qua TaskPacket thay vì buộc downstream Peer tự đọc sibling repo. Provenance/source path chỉ là attribution; nó không cấp filesystem authority. Nếu material upstream detail chưa có hoặc chưa đủ, downstream Peer phải trả `DEPENDENCY_REQUEST` để Lead resolve dependency ở owner repo.

## Peer independent judgment

Peer không phải worker mù. Khi evidence materially phá premise hoặc scope hiện tại, Peer có thể
trả một trong các signal sau trong native response:

- `REOPEN_REQUEST`: technical premise/decision hiện tại không còn đứng vững.
- `DEPENDENCY_REQUEST`: cần prerequisite hoặc ownership ngoài assignment hiện tại.
- `BLOCKED`: không còn safe in-scope progress.

Mỗi signal phải kèm evidence, consequence và decision/dependency cần từ Lead.

Writable Peer handoff phải chỉ ra candidate/snapshot đủ định danh, base khi relevant, changed
paths, verification thực tế, limits/residual risk và trạng thái write ownership. Read-only Peer
review phải chỉ ra exact candidate/snapshot được review, findings, evidence và limits.

## Communication loop

Mọi actionable delegated work phải đóng đủ vòng:

```text
Lead brief
  -> actual Peer response
  -> explicit Lead disposition
```

Lead disposition phải là một trong các hành động có nghĩa: trả lời question, resolve dependency
hoặc ownership, yêu cầu evidence/repair cụ thể, defer với owner + return checkpoint, hoặc
explicit `ACCEPT` / `REJECT` exact candidate với reason.

`DONE`, runtime settled, passing tests hoặc completion message chỉ là evidence; chúng không tự
đóng communication loop và không tự đồng nghĩa technical acceptance.

Dependent dispatch/acceptance phải chờ unresolved actionable response. Unrelated ready work
vẫn tiếp tục.

## Supervisor oversight

Supervisor kiểm tra actual Lead brief, actual Peer response và Lead disposition; không dùng
Lead summary một mình làm bằng chứng loop đã đóng.

Supervisor can thiệp khi có concrete deviation như:

- Human intent hoặc accepted requirement bị drift;
- dependency chưa accepted nhưng work đã dispatch;
- write-scope ownership overlap;
- shared contract bị thay đổi ngoài boundary;
- Peer blocker/request bị bỏ quên;
- candidate được dùng tiếp khi chưa có explicit Lead disposition;
- evidence không match promised outcome.

Intervention đi qua Lead và nên là observation + open question grounded in current evidence.
Supervisor không viết thay Peer response, không ACCEPT/REJECT candidate, không chạy
repo-local implementation/verification thay Lead/Peer và không tạo second command chain.

Nếu host/runtime chưa có direct Supervisor→Lead channel, Supervisor phải surface concise
decision-ready finding cho Human/operator thay vì ghi lén directive vào project artifact.

## Evidence and acceptance

Evidence phải match outcome được hứa. Passing unit tests có thể chứng minh code path nhưng
không tự chứng minh UI usability, playback quality, save/reopen behavior hoặc cross-repo
integration semantics.

Lead giữ riêng:

- verified behavior;
- untested scope;
- failed checks;
- unknowns;
- Human permission to proceed despite a known limitation.

Human permission không biến unmet criterion thành pass.

## Continuity

Sau acceptance, Lead reconcile current Work Item/project status, usable downstream inputs,
remaining limits và affected assumptions/dependencies trước khi chọn next frontier.

Khi requirement material thay đổi, Work Item revision tăng và prior findings phải được reconcile
finding-by-finding. Native session giữ short-term continuity; durable task truth nằm trong
Work Item, reusable verified truth nằm trong Knowledge MCP.

## Waiting and monitoring

Ưu tiên finish/error/attention/decision events thay vì polling unchanged state. Supervisor chỉ
claim ongoing monitoring khi runtime thực sự có wake-up/event/heartbeat mechanism phù hợp;
nếu không có, phải nói rõ monitoring gap.

Keep handoffs concise, evidence-based và decision-ready.
