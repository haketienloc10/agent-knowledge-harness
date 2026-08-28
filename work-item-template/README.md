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

## Snapshot và history

Các field có hai vai trò khác nhau:

```text
summary/current_requirements/status/phase/repos/blockers/next_actions
= snapshot hiện tại để tiếp tục công việc ngay

questions/decisions/changes/checkpoints
= material history giải thích vì sao snapshot hiện tại hình thành
```

`repos[repo].summary` là **current effective repo truth** sau tất cả work đã biết. Nó
không phải narrative của session mới nhất. `checkpoints[]` là accumulated material
phase/milestone history; future reader phải reconstruct được major progression mà không
bắt buộc mở artifact.

Checkpoint có thể thêm:

```text
kind        = optional free-form descriptive milestone label
artifact_id = optional detail artifact reference
```

`kind` không phải enum/FSM. Ví dụ hữu ích: `investigation`, `implementation`,
`verification`, `review`, `decision`, `report`, `completion`.

Không persist terminal transcript, command-by-command activity hoặc agent reasoning.

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

- **Implementation:** phải persist current implemented outcome + material checkpoint dù
  không tạo artifact.
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

`work_item_get` trả Work Item cùng **thin artifact index**. Index này là derived
metadata, không được persist trong `work_items.document_json`. Core từ chối create hoặc
update nếu caller cố ghi field `artifacts`.

Full detail dùng progressive disclosure:

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
write chunk          <= 32,000 UTF-8 bytes/call
read section         4..32,000 UTF-8 bytes/call
artifacts/item       <= 50
sections/artifact    <= 100
template config file <= 64,000 bytes
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
work_item_list(status?, repository?, limit?)
work_item_create(id, title, summary?, status?, phase?, current_requirements?, repositories?)
work_item_update(id, expected_revision, changes: WorkItemPatch)
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

`work_item_update` vẫn dùng JSON merge-patch semantics:

- nested object merge;
- array replace nguyên tử;
- `null` remove field;
- required field bị remove sẽ fail validation;
- immutable/derived field như `id`, `revision`, `artifacts` không được patch.

Arrays replace nguyên tử là intentional cho MVP: caller phải đọc Work Item hiện tại,
reconcile full intended array, rồi update bằng exact revision.

### Typed WorkItemPatch

MCP expose schema cụ thể cho `changes` thay vì generic `dict`. Mục đích là để agent
không phải đoán shape hoặc ý nghĩa của semantic fields:

```text
questions[]     = external/product ambiguity records; không phải string/note
changes[]       = requirement/scope evolution; không phải generic code/progress log
blockers[]      = điều thực sự chặn tiến độ; không phải risk/note chung
handoffs[]      = remaining work chuyển giữa repo/owner
next_actions[]  = object có action + repo hoặc owner; không phải list[string]
checkpoints[]   = accumulated material milestones; optional kind/artifact_id
repos           = current repo truth; nested object merge
```

Canonical examples:

```yaml
questions:
  - id: q1
    status: open
    question: SMTP capacity thực tế là bao nhiêu?

blockers:
  - id: b1
    status: open
    summary: Chưa xác định producer-side bulk classifier.

next_actions:
  - repo: sg_mail
    action: Xác định classification boundary.

checkpoints:
  - repo: sg_mail
    kind: implementation-rework
    artifact_id: review:2
    summary: Fixed review finding and reverified.
```

Các nested semantic record cho phép provenance/evidence mở rộng như `source`,
`evidence`, `decided_by`, `caused_by_decision`, nhưng top-level patch field lạ bị từ
chối. Serialization dùng `exclude_unset=True`: field omitted nghĩa là không đổi, còn
explicit `null` vẫn được giữ để core áp JSON merge-patch deletion.

Expected update-domain failures (`work_item_validation`, `revision_conflict`, missing
Work Item) trả structured result với `updated=false` để agent thấy nguyên nhân và action
thay vì chỉ nhận generic `Error executing tool`. Unexpected runtime/store failures vẫn
là MCP tool errors.

## Optimistic concurrency

Mọi Work Item có `revision` do MCP sở hữu.

```text
QiQi đọc revision 12
backend đọc revision 12
backend update -> revision 13
QiQi update bằng expected_revision=12 -> conflict
QiQi reread revision 13 -> reconcile -> retry
```

Artifact có optimistic revision riêng:

```text
artifact revision 4
writer A append -> revision 5
writer B append expected_artifact_revision=4 -> conflict
writer B artifact_get -> reconcile -> retry
```

Không có last-write-wins silent overwrite.

SQLite dùng `BEGIN IMMEDIATE`, WAL và exact revision checks cho mutation paths.

## Ownership policy

MCP storage không triển khai RBAC trong MVP. Boundary được enforce bởi agent policy.

### QiQi

QiQi sở hữu global orchestration state:

- overall `status` / `phase` / `summary`;
- repo involvement/assignment;
- global `next_actions`;
- reconciliation sau cross-repo handoff;
- quyết định task thực sự `done`.

### Repository execution agent

Agent được đọc toàn bộ Work Item để hiểu context nhưng:

- chỉ investigation/implementation/verification trong Git root hiện tại;
- chỉ cập nhật repo evidence/state mà nó thực sự xác lập;
- có thể ghi blocker, open question, checkpoint và handoff nó phát hiện;
- không đánh dấu sibling repo done;
- không tự xử lý phần việc của repository khác;
- cross-repo remaining work phải được ghi/handoff và trả lại QiQi để điều phối.

Artifact không thay đổi ownership rule và không override newer canonical Work Item
state.

## Questions, decisions và changes

Open question tồn tại khi implementation không thể tự chốt một external/product
ambiguity. Agent không đoán để hoàn thành task.

Khi user/customer Q&A trả lời:

```text
question resolved
      ↓
decision active
      ↓
current_requirements được reconcile nếu semantics thay đổi
```

Nếu requirement/scope thực sự thay đổi, ghi thêm `changes[]`.

Decision cũ không bị xóa khi bị đổi. Mark `status: superseded` và trỏ
`superseded_by` sang decision mới để phân biệt "implementation trước sai" với
"requirement sau đã đổi".

## Handoff cross-repo

Handoff nằm trong chính canonical Work Item, không có handoff store thứ hai:

```text
backend agent
  ↓ ghi handoff backend -> frontend + evidence
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

`show` chỉ hiển thị thin artifact index. Text-mode `artifact` stream stored chunks trực
tiếp từ read-only SQLite connection; `--raw` stream copy/paste-ready titles + bodies;
chỉ explicit `--json` mới materialize full selected artifact. CLI không có mutation path.

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

Sau thay đổi skill/policy, mở fresh QiQi/child session để client discover user-scope skill
mới. Workspace migration không tự ghi vào user home; sau migration policy sang `$work-item`
thì rerun `scripts/install-user-mcp.sh` từ `work-item-template` để refresh skill.

## Verification

```bash
bash scripts/work-item-template-check.sh
```

Test/check cover ít nhất:

- create/get/list/update Work Item;
- questions/decisions/requirement changes;
- nested repo state merge;
- stale Work Item revision và concurrent writers;
- typed `WorkItemPatch` semantic shapes/descriptions;
- repo-summary current-truth semantics + checkpoint `kind`/`artifact_id` metadata;
- shared `$work-item` skill operational contract + explicit opt-in boundary;
- managed user-scope skill install/idempotence/unmanaged-conflict behavior;
- main MCP installer includes the shared skill installation;
- reject các payload từng gây retry: question string/`text`, blocker string, invalid change enum,
  next-action string/missing owner;
- preserve nested provenance, repo partial merge và explicit merge-patch `null`;
- structured update validation/conflict/not-found results;
- immutable metadata và derived `artifacts` guard;
- artifact create/list/get manifest;
- stale artifact writer revision;
- artifact revision độc lập Work Item revision;
- exact Work Item revision khi tạo artifact;
- exact 32,000-byte write boundary và UTF-8 byte semantics;
- bounded read + revision-bound continuation cursor;
- exact preservation của Markdown/code whitespace;
- artifact/section MVP caps;
- configurable artifact template default/override/startup validation;
- guidance load-once, detached create-response và storage independence;
- section ngoài template vẫn hợp lệ vì template chỉ advisory;
- finalize empty bị reject và complete artifact immutable;
- human CLI thin artifact index/full explicit artifact view;
- human CLI diagnostic/raw streaming + explicit JSON materialization đều read-only;
- static invariant cho MCP tool count, typed update surface, template/storage boundary,
  post-commit mutation response, bounded payload và read-only boundary.

Khi rollout thực tế, mở fresh Codex/Claude session để MCP client discover tool surface +
`$work-item` skill và smoke test QiQi + repository child trên cùng database.
