# Global Work Item MCP

Global Work Item MCP là source of truth duy nhất cho **mutable product-task state**
được dùng chung bởi QiQi và execution agents trong các repository con.

Nó không thay thế:

```text
Global Work Item MCP   = task truth + optional task-detail artifacts
Knowledge MCP          = reusable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

## Mục tiêu MVP

Giải quyết continuity cho task kéo dài qua investigation, planning, implementation,
unit test, IT, UAT, fix bug và Q&A mà không yêu cầu người dùng hoặc QiQi kể lại toàn
bộ lịch sử sau mỗi session.

MVP cố ý **không** là project-management product. Không có workflow DSL, event
sourcing, RBAC, notification, Redmine sync, automatic phase transition hoặc web
dashboard. Human CLI chỉ là read-only observer của canonical store.

## Canonical identity

Mỗi product task có một ID ổn định:

```text
redmine:116655
redmine:151921
```

Format là `<source>:<external-id>`.

## Work Item document

Một Work Item lưu snapshot hiện tại và material history cần để tiếp tục công việc:

```yaml
id: redmine:116655
status: active
phase: implementation
summary: Backend đang cập nhật theo requirement mới.

current_requirements:
  - Order detail trả paymentStatus.
  - Order list cũng trả paymentStatus.

questions:
  - id: q1
    status: resolved
    question: paymentStatus unknown có trả field không?
    answer: Có, trả null.
    decision_id: d1

decisions:
  - id: d1
    status: active
    summary: paymentStatus luôn xuất hiện; unknown trả null.
    decided_by: customer

changes:
  - id: c1
    type: requirement_added
    status: accepted
    summary: Thêm paymentStatus vào order list API.

repos:
  backend-api:
    status: done
    summary: paymentStatus đã được expose theo current requirement; không còn repo-local work.
    verification:
      - Unit tests passed
  frontend-web:
    status: pending
    summary: Chưa consume paymentStatus.
    verification: []

blockers: []

handoffs:
  - id: h1
    from: backend-api
    to: frontend-web
    status: pending
    summary: Consume paymentStatus.
    evidence:
      - commit abc123

next_actions:
  - repo: frontend-web
    action: Consume paymentStatus và chạy UT.

checkpoints:
  - repo: backend-api
    kind: implementation
    summary: Backend implementation hoàn tất; paymentStatus được expose theo requirement.
  - repo: backend-api
    kind: verification
    summary: Focused unit tests pass.
  - repo: backend-api
    kind: review
    artifact_id: review:1
    summary: Review xác nhận implementation, không có blocking finding.
```

`phase` là descriptive state, không phải finite-state-machine. Task có thể quay từ
UAT về implementation/fix rồi trở lại IT/UAT mà MCP không chặn transition.

`status` MVP có: `active`, `waiting`, `blocked`, `done`, `cancelled`.

Repo status có: `pending`, `active`, `waiting`, `blocked`, `done`, `not_required`.

Requirement change type MVP có: `requirement_added`, `requirement_changed`,
`requirement_removed`, `scope_changed`.

Canonical `questions[]` và `decisions[]` luôn có lifecycle `status` explicit. Store cũ
thiếu hoặc có `status: null` được migrate một lần thành `question=open`,
`decision=active` và Work Item revision được advance; runtime không giữ implicit
lifecycle semantics lâu dài.

## Progressive disclosure: snapshot và history

Stored document vẫn chứa đầy đủ current state + material history, nhưng public read
surface không hydrate toàn canonical document mặc định.

`work_item_get(id)` là **bounded current-state projection**:

```text
id / revision / title / status / phase / summary
current_requirements / repos / next_actions
open_questions / active_decisions / open_blockers / pending_handoffs
thin artifact metadata
history counts
```

Nó không trả mặc định resolved questions, superseded decisions, accepted/rejected
changes, resolved blockers/handoffs hoặc checkpoint records. Tên field lifecycle được
đổi thành `open_*` / `active_*` / `pending_*` để caller không nhầm projection subset với
full canonical collection.

Material history đọc riêng bằng đúng semantic collection:

```text
work_item_history_read(
  id,
  collection,
  status?,
  repository?,
  cursor?,
  limit?
)
```

Mỗi call chỉ đọc **một** collection trong:

```text
questions | decisions | changes | checkpoints | blockers | handoffs
```

`status` chỉ hợp lệ cho lifecycle collections. `repository` hiện chỉ hợp lệ cho
`checkpoints`, vì đó là collection có canonical `repo` field. Filter không hợp semantic
collection sẽ fail validation thay vì bị silently ignore.

History giữ canonical array order. Cursor là opaque và bind vào canonical Work Item id,
exact whole Work Item revision, collection và filters. Nếu Work Item đổi giữa hai page,
caller phải restart history read từ revision mới; server không bao giờ silently mix hai
revisions hoặc dùng cursor của Work Item khác.

`work_item_get.history` chỉ là deterministic counts (`total`, và `current`/`hidden` khi
có lifecycle subset), không phải synthesized prose và không chứa checkpoint references.

`repos[repo].summary` là **current effective repo truth** sau tất cả work đã biết. Nó
không phải narrative của session mới nhất. Nếu fresh session không thể tiếp tục từ
`summary`, `repos`, current requirements và lifecycle subset thì phải sửa current
snapshot, không chữa bằng cách hydrate history mặc định.

`checkpoints[]` vẫn là accumulated material phase/milestone history; future reader có
thể reconstruct major progression bằng scoped history read mà không bắt buộc mở artifact.

Checkpoint có thể thêm:

```text
kind        = optional free-form descriptive milestone label
artifact_id = optional detail artifact reference
```

`kind` không phải enum/FSM. Ví dụ hữu ích: `investigation`, `implementation`,
`verification`, `review`, `decision`, `report`, `completion`.

Không persist terminal transcript, command-by-command activity hoặc agent reasoning.

## Typed incremental mutation

Read progressive disclosure chỉ giải quyết read amplification. Write path cũng không
được bắt model hydrate/resend accumulated history chỉ để sửa một record.

Public `work_item_update` nhận một `WorkItemMutation`:

```text
WorkItemMutation
  state       = bounded current-state patch
  operations  = typed semantic commands (<= 50/call)
```

### `mutation.state`

Current effective fields duy nhất được patch trực tiếp:

```text
title / status / phase / summary
current_requirements
repos
next_actions
```

- `repos` merge nested object theo supplied fields.
- `current_requirements` và `next_actions` là bounded current arrays và replace nguyên tử.
- State patch giữ JSON merge-patch null/omission semantics.
- Historical semantic collections **không tồn tại** như full-array replacement fields
  trong public state schema.

Điều này làm accidental deletion do caller reconstruct thiếu history trở thành lỗi
**không thể biểu diễn bằng public mutation schema**, thay vì chỉ dựa vào discipline.

### `mutation.operations`

Operation algebra cố ý nhỏ và domain-specific:

```text
checkpoint_append
question_upsert
decision_upsert
change_upsert
blocker_upsert
handoff_upsert
```

Không dùng generic JSON Patch và không tạo một MCP tool riêng cho từng collection. Một
product decision có thể cần resolve question + create/supersede decision + update current
requirement + append checkpoint; tất cả phải commit atomically trong **một** Work Item
revision.

Operation list:

- tối đa 50 operations/call;
- apply theo caller order;
- duplicate stable-id target trong cùng call bị reject;
- all-or-nothing trong cùng `BEGIN IMMEDIATE` transaction;
- stale `expected_revision` luôn conflict, kể cả khi writer khác sửa record/collection
  hoàn toàn khác;
- server không auto-rebase stale semantic operation.

### Stable-id lifecycle semantics

`upsert` không có nghĩa arbitrary overwrite. Nó nghĩa create record mới hoặc advance
lifecycle/provenance hợp lệ của stable id hiện tại.

```text
question:  open -> resolved
decision:  active -> superseded
blocker:   open -> resolved
handoff:   pending -> resolved

change:
  proposed -> accepted | rejected | superseded
  accepted -> superseded
  rejected/superseded terminal
```

Reverse transitions bị reject. Nếu blocker/handoff cũ đã resolved nhưng cùng concern tái
xuất hiện, tạo stable id mới thay vì reopen history cũ.

Identity/provenance được giữ monotonic:

- `questions[].question` immutable; `answer` / `decision_id` là write-once resolution.
- `decisions[].summary` immutable; `superseded_by` là write-once.
- `changes[].type` và `changes[].summary` immutable.
- `blockers[].summary` immutable.
- `handoffs[].from`, `.to`, `.summary` immutable.
- existing provenance/evidence extension chỉ được giữ nguyên hoặc thêm mới; không silent
  rewrite established provenance.
- `checkpoints[]` chỉ có append path; không có checkpoint upsert/edit API.

Cross-record reference được validate trên **final candidate document** sau khi toàn bộ
operation list đã apply. Vì vậy một atomic mutation có thể:

```text
create decision d7
+ supersede d3 -> d7
+ resolve question q2 -> d7
```

nhưng commit sẽ rollback toàn bộ nếu `decision_id` / `superseded_by` cuối cùng reference
missing decision hoặc decision tự supersede chính nó.

### Compact mutation receipt

`work_item_update` success không trả full canonical document:

```json
{
  "updated": true,
  "id": "redmine:116655",
  "revision": 42,
  "changed": ["repos.backend-api", "decisions:d7", "questions:q2", "checkpoints"]
}
```

`changed` là bounded diagnostic labels, không phải mutation path language. Nếu caller cần
current state sau commit thì gọi lại `work_item_get` khi quyết định kế tiếp thật sự cần.
Mutation success tự nó không bơm history/full document vào model context.

Expected update-domain failures (`work_item_validation`, `revision_conflict`, missing
Work Item) trả structured result với `updated=false`. Revision conflict yêu cầu reread
current snapshot, reconcile và retry; không hydrate full history trừ khi exact provenance
thực sự cần cho quyết định.

## Material session reconciliation

Mọi substantive Work Item session established material state phải reconcile canonical
Work Item trước khi kết thúc. **Artifact creation không thay thế Work Item update.**

Generic rule:

```text
repos[repo].summary
  = current effective repository state

repos[repo].verification
  = concrete verification evidence hiện đã established

checkpoints[]
  = material phase/milestone history

artifact
  = optional detailed material
```

Phase-specific guardrails chỉ áp dụng nơi failure mode đặc biệt:

- **Implementation:** persist current implemented outcome qua state patch và append một
  material checkpoint khi có milestone mới; không đọc/resend historical checkpoints.
- **Review:** review artifact giữ detail; checkpoint giữ material finding. Không overwrite
  implementation-oriented repo summary thành `Review code...` narrative nếu review chỉ
  xác nhận current implementation.
- **Report:** report artifact là presentation/detail; preserve prior repo state/history,
  rồi QiQi reconcile global summary/status/phase/next action.

Investigation, planning và verification dùng generic rule trên; không tạo hard workflow
machine hoặc event log.

## Shared `$work-item` operational skill

Các rule read/write/revision/reconciliation ở trên được ship thành một **single
user-scoped Agent Skill** tại:

```text
work-item-template/skills/work-item/SKILL.md
```

QiQi và repository execution agents dùng cùng `$work-item` protocol. Workspace/repo
`AGENTS.md` chỉ giữ always-on activation, authority, filesystem/cross-repo và safety
invariants; không giữ thêm một bản copy của operational mechanics.

Activation vẫn explicit:

- canonical Work Item đã được identify/selected → apply `$work-item`;
- user explicitly yêu cầu tạo/dùng Work Item → apply `$work-item`;
- trước bất kỳ `work_item_*` tool call nào → apply `$work-item`;
- generic ticket/task/incident **không** tự động tạo/chọn Work Item.

Không còn `$ticket-work-item` workflow skill. Muốn tạo task mới từ nội dung paste thì
user explicitly yêu cầu QiQi tạo Work Item từ nội dung đó; `$work-item` xử lý get-first,
create-if-missing và reconciliation theo role authority.

## Optional task artifacts

Một số detail như intake, investigation, plan, review hoặc final report có thể rất dài
và không cần hydrate mỗi lần đọc task status. Chúng được lưu thành **optional task
artifacts** trong cùng SQLite canonical store.

```text
Work Item
  = current task truth / orchestration state

Artifact
  = optional detailed material derived từ một exact Work Item revision
```

Artifact chỉ được materialize khi người dùng explicitly yêu cầu loại detail đó hoặc
workflow explicit yêu cầu artifact. Không tạo artifact như progress bookkeeping mặc
định và không dùng artifact như replacement cho canonical continuation state.

MVP types vẫn cố định:

```text
intake | investigation | plan | review | report
```

Section/header **không cố định**. Repo có advisory config dễ chỉnh tại:

```text
work-item-template/config/artifact-templates.json
```

Config chỉ gợi ý `section.id`, `title`, `purpose` cho từng type. Server load/validate
config một lần khi MCP process khởi động; `work_item_artifact_create` trả derived
`template_guidance`, nhưng guidance không persist và không bắt buộc/cấm/reorder section.
Artifact cũ không thay đổi khi config được sửa.

Có thể dùng custom config path:

```bash
export WORK_ITEM_ARTIFACT_TEMPLATES_PATH="$HOME/.config/agent-work-items/artifact-templates.json"
```

Env phải tồn tại lúc Codex/Claude/MCP process được mở. Không set thì dùng repo default.
Sửa config chỉ cần restart/fresh MCP process, **không cần database migration**.

`work_item_get` trả bounded current-state projection cùng **thin artifact index**. Index
này là derived metadata, không được persist trong `work_items.document_json`. Core từ
chối create nếu caller cố persist field `artifacts`; mutation state schema không expose
field này.

Full artifact detail dùng progressive disclosure:

```text
artifact_list -> artifact_get manifest -> artifact_read bounded section chunks
```

Không có MCP read call nào trả toàn artifact body. `work_item_create` và
`work_item_update` cũng không làm post-commit artifact enrichment; mutation success
phản ánh đúng canonical write vừa commit.

Artifact revision độc lập với Work Item revision. Artifact append/finalize không làm
Work Item revision tăng và không cạnh tranh optimistic writer với task-state update.

Hard payload/storage bounds:

```text
Work Item semantic ops <= 50/call
artifact write chunk   <= 32,000 UTF-8 bytes/call
artifact read section  4..32,000 UTF-8 bytes/call
artifacts/item         <= 50
sections/artifact      <= 100
template config file   <= 64,000 bytes
```

Artifact lifecycle:

```text
create -> draft
append -> draft revision N+1
finalize -> complete, immutable trong MVP
```

Create artifact phải dựa trên exact current Work Item revision qua
`based_on_work_item_revision`. Continuation cursor của artifact read được bind vào
artifact revision; nếu draft thay đổi giữa hai page, caller phải reread manifest và
restart section read thay vì trộn content từ hai revision.

Nếu artifact cũ mâu thuẫn Work Item mới hơn, Work Item thắng.

Chi tiết: `ARTIFACTS.md`.

## API MVP

Canonical Work Item tools:

```text
work_item_get(id)
work_item_history_read(id, collection, status?, repository?, cursor?, limit?)
work_item_list(status?, repository?, limit?)
work_item_create(id, title, summary?, status?, phase?, current_requirements?, repositories?)
work_item_update(id, expected_revision, mutation: WorkItemMutation)
```

Optional artifact tools:

```text
work_item_artifact_list(id, type?, limit?)
work_item_artifact_get(id, artifact_id)
work_item_artifact_create(id, type, title, summary, based_on_work_item_revision, artifact_id?)
work_item_artifact_append(id, artifact_id, expected_artifact_revision, section_id, content, section_title?)
work_item_artifact_read(id, artifact_id, section_id, cursor?, limit_bytes?)
work_item_artifact_finalize(id, artifact_id, expected_artifact_revision)
```

Một update có thể kết hợp current state và semantic operations:

```json
{
  "state": {
    "summary": "Backend implementation hoàn tất.",
    "repos": {
      "backend-api": {
        "status": "done",
        "verification": ["unit tests passed"]
      }
    }
  },
  "operations": [
    {
      "op": "checkpoint_append",
      "value": {
        "repo": "backend-api",
        "kind": "verification",
        "summary": "Focused unit tests passed."
      }
    }
  ]
}
```

Resolve một existing question chỉ cần target transition, không cần resend question hoặc
full collection:

```json
{
  "operations": [
    {
      "op": "question_upsert",
      "value": {
        "id": "q1",
        "status": "resolved",
        "decision_id": "d7"
      }
    }
  ]
}
```

Các nested mutation record cho phép provenance/evidence mở rộng như `source`, `evidence`,
`decided_by`, `caused_by_decision`; established extension không được silently rewrite.
Semantic mutation explicit `null` bị reject: field không đổi thì omit.

## Optimistic concurrency

Mọi Work Item có một whole-document `revision` do MCP sở hữu.

```text
QiQi đọc revision 12
backend đọc revision 12
backend checkpoint_append -> revision 13
QiQi blocker_upsert bằng expected_revision=12 -> conflict
QiQi reread revision 13 -> reconcile -> retry
```

Writer thứ hai vẫn conflict dù sửa collection khác. Incremental mutation giảm payload,
**không** thay đổi concurrency model thành per-record revision và không silently merge
stale commands.

History pagination dùng cùng whole Work Item revision:

```text
history page 1 @ revision 12 -> cursor(revision 12)
Work Item update -> revision 13
history page 2 bằng cursor revision 12 -> history_revision_conflict
caller restart history read @ revision 13
```

Artifact có optimistic revision riêng:

```text
artifact revision 4
writer A append -> revision 5
writer B append expected_artifact_revision=4 -> conflict
writer B artifact_get -> reconcile -> retry
```

Không có last-write-wins silent overwrite.

SQLite Work Item mutation dùng `BEGIN IMMEDIATE`, exact revision check, apply state +
operations trên in-memory candidate, validate final canonical document/cross-record
references, rồi persist document **một lần** và advance revision **một lần**. Operation
N fail thì toàn transaction rollback.

Read/history và incremental mutation vẫn operate trên canonical `document_json`; không
thêm event store, per-record persistence hoặc revision model thứ hai.

## Ownership policy

MCP storage không triển khai RBAC trong MVP. Boundary được enforce bởi agent policy.

### QiQi

QiQi sở hữu global orchestration state:

- overall `status` / `phase` / `summary`;
- repo involvement/assignment;
- global `next_actions`;
- reconciliation sau cross-repo handoff;
- product/customer decisions;
- quyết định task thực sự `done`.

### Repository execution agent

Agent đọc bounded current Work Item để hiểu context và chỉ đọc scoped history khi thật
sự cần provenance. Nó vẫn:

- chỉ investigation/implementation/verification trong Git root hiện tại;
- chỉ cập nhật repo evidence/state mà nó thực sự xác lập;
- có thể append material checkpoint hoặc advance blocker/open question/handoff nó phát hiện;
- không đánh dấu sibling repo done;
- không tự xử lý phần việc của repository khác;
- cross-repo remaining work phải được ghi/handoff và trả lại QiQi để điều phối.

Typed incremental operations không thay đổi authority model.

## Questions, decisions và changes

Open question tồn tại khi implementation không thể tự chốt một external/product
ambiguity. Agent không đoán để hoàn thành task.

Khi user/customer Q&A trả lời, một atomic mutation có thể thực hiện:

```text
decision_upsert(new decision)
      ↓
question_upsert(open -> resolved)
      ↓
state.current_requirements reconcile nếu semantics thay đổi
      ↓
change_upsert nếu requirement/scope thực sự đổi
```

Decision cũ không bị rewrite khi requirement đổi. Advance nó `active -> superseded` và
trỏ `superseded_by` sang decision mới để phân biệt "implementation trước sai" với
"requirement sau đã đổi".

## Handoff cross-repo

Handoff nằm trong chính canonical Work Item, không có handoff store thứ hai:

```text
backend agent
  ↓ handoff_upsert pending + evidence
Work Item
  ↓
QiQi reconcile/delegate
  ↓
frontend agent đọc cùng Work Item
```

Execution agent vẫn không sửa sibling repository.

## Persistence

MCP dùng một SQLite database explicit qua:

```bash
WORK_ITEM_DB_PATH=/absolute/path/work-items.sqlite3
```

Database không phụ thuộc CWD/workspace/repository. Cả QiQi và child agents kết nối
cùng user-scoped MCP registration.

Default installer path:

```text
~/.local/share/agent-work-items/work-items.sqlite3
```

Tables:

```text
work_items
work_item_artifacts
work_item_artifact_sections
work_item_artifact_chunks
```

Bounded snapshot/history read và incremental Work Item mutation không thêm persistence
table. One-time lifecycle migration sử dụng SQLite `PRAGMA user_version` làm store-version
marker và chỉ materialize explicit question/decision status trong existing
`document_json`.

Artifact template config là startup advisory file, **không phải persistence table/store**.
Không có filesystem/Markdown task-artifact store thứ hai.

## Human CLI

```bash
agent-work-item list
agent-work-item show redmine:113387
agent-work-item artifact redmine:113387 report:1
agent-work-item artifact redmine:113387 report:1 --section code-review
agent-work-item artifact redmine:113387 report:1 --raw
```

Human CLI vẫn là read-only observer của canonical store. CLI `show` có thể giữ
full-document diagnostic behavior riêng; agent-facing progressive disclosure contract nằm
ở MCP `work_item_get` / `work_item_history_read`. Text-mode `artifact` stream stored
chunks trực tiếp từ read-only SQLite connection; `--raw` stream copy/paste-ready titles +
bodies; chỉ explicit `--json` mới materialize full selected artifact. CLI không có
mutation path.

Chi tiết: `CLI.md`.

## Cài đặt user scope

```bash
bash scripts/install-user-mcp.sh
```

Hoặc:

```bash
bash scripts/install-user-mcp.sh \
  --db-path /path/to/work-items.sqlite3
```

Installer tạo/cập nhật managed user-scope capability:

```text
~/.agents/skills/work-item/SKILL.md   # Codex user skill
~/.claude/skills/work-item/SKILL.md   # Claude user skill
~/.local/bin/agent-work-item-mcp      # MCP runtime
~/.local/bin/agent-work-item          # read-only human CLI
```

Nếu skill cùng tên tồn tại nhưng không do harness quản lý (và không identical), installer
fail thay vì overwrite âm thầm. Có thể refresh riêng skill bằng:

```bash
bash scripts/install-user-skill.sh
```

Installer cũng đăng ký MCP tên `work_item` cho Codex/Claude CLI đang có. Nếu registration
cùng tên trỏ sang runtime khác, installer fail thay vì overwrite âm thầm. Wrapper chỉ
set `WORK_ITEM_DB_PATH` và giữ inherited environment, nên optional
`WORK_ITEM_ARTIFACT_TEMPLATES_PATH` được truyền qua nếu set khi client/MCP được mở.

Sau thay đổi skill/policy/public schema, rerun installer từ checkout mới và mở fresh
QiQi/child session để client discover user-scope MCP tool schema + skill mới. Workspace
migration không tự ghi vào user home.

## Verification

```bash
bash scripts/work-item-template-check.sh
```

Test/check cover ít nhất:

- create/get/list Work Item + compact incremental update receipt;
- bounded `work_item_get` current-state projection không hydrate accumulated history;
- open/active/current lifecycle subsets + deterministic history counts;
- scoped single-collection history read + typed filter validation;
- opaque cursor bind Work Item id/revision/collection/filters + conflict/restart;
- one-time legacy missing/null question/decision lifecycle migration;
- typed `WorkItemMutation` và state/history schema separation;
- historical full-array replacement không representable qua public mutation schema;
- checkpoint append với 200 existing checkpoints không hydrate/resend history;
- partial question resolve / decision supersede không resend immutable record body;
- monotonic lifecycle + immutable identity + write-once provenance guards;
- change lifecycle transition rules;
- final-candidate cross-record reference validation;
- duplicate semantic target và >50 operations bị reject;
- operation failure rollback cả state patch + prior operations;
- stale writer và concurrent writers vẫn conflict trên whole Work Item revision;
- nested repo state merge + current-array replacement semantics;
- repo-summary current-truth semantics + checkpoint `kind`/`artifact_id` metadata;
- shared `$work-item` incremental mutation protocol + explicit opt-in boundary;
- managed user-scope skill install/idempotence/unmanaged-conflict behavior;
- main MCP installer includes the shared skill installation;
- structured update validation/conflict/not-found results;
- immutable metadata và derived `artifacts` boundary;
- artifact create/list/get manifest;
- stale artifact writer revision;
- artifact revision độc lập Work Item revision;
- exact Work Item revision khi tạo artifact;
- exact 32,000-byte artifact write boundary và UTF-8 byte semantics;
- bounded artifact read + revision-bound continuation cursor;
- exact preservation của Markdown/code whitespace;
- artifact/section MVP caps;
- configurable artifact template default/override/startup validation;
- guidance load-once, detached create-response và storage independence;
- section ngoài template vẫn hợp lệ vì template chỉ advisory;
- finalize empty bị reject và complete artifact immutable;
- human CLI diagnostic/raw streaming + explicit JSON materialization đều read-only;
- static invariant cho MCP tool count, bounded read, typed incremental update, compact
  mutation response, template/storage boundary và read-only CLI.

Khi rollout thực tế, mở fresh Codex/Claude session để MCP client discover tool surface +
`$work-item` skill và smoke test QiQi + repository child trên cùng database.
