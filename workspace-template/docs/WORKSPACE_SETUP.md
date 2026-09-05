# Thiết lập Multi-repository Workspace cho QiQi

## Mục tiêu

Workspace sau setup dùng bốn nguồn truth độc lập:

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

`work_item` và `knowledge` phải được cài user/global scope; workspace project config chỉ có `qiqi_delegate`.

## 1. Cài Global Work Item MCP

Từ harness checkout:

```bash
cd work-item-template
bash scripts/work-item-template-check.sh
bash scripts/install-user-mcp.sh
```

Default DB:

```text
~/.local/share/agent-work-items/work-items.sqlite3
```

Có thể dùng `--db-path`. Mở fresh QiQi session rồi xác minh:

```bash
codex mcp get work_item
claude mcp get work_item
```

Fresh QiQi client phải discover:

```text
work_item_get
work_item_history_read
work_item_list
work_item_create
work_item_update
```

Work Item là **canonical owner** của mutable product-task state nhưng thuộc QiQi/orchestration side. Repository child không cần discover hoặc gọi Work Item MCP để hiểu/hoàn thành TaskPacket.

Smoke DB test/non-production:

1. create test Work Item;
2. `work_item_get` revision 1 và xác nhận response là bounded current-state projection;
3. `work_item_update` bằng revision 1 với `mutation.operations.checkpoint_append=[{summary: ...}]` → compact receipt revision 2;
4. stale revision 1 phải conflict;
5. `work_item_history_read(collection="checkpoints")` vẫn đọc exact stored history khi QiQi cần provenance.

`mutation.operations` là grouped typed object, không phải list `{op,value}`. Fresh-agent happy path không probe schema bằng intentionally-invalid calls.

## 2. Cài Shared Knowledge MCP

```bash
cd knowledge-template
bash scripts/knowledge-template-check.sh
bash scripts/install-user-mcp.sh --store-root /path/to/shared-knowledge/store
```

Fresh session phải có:

```text
knowledge_search
knowledge_read
knowledge_read_metadata
knowledge_read_section
knowledge_write
knowledge_update
```

Smoke progressive disclosure:

- search trả thin cards và không revision;
- full read trả full semantic content/sources/revision;
- metadata read trả provenance/revision + section index nhưng không whole content;
- section read trả đúng one section body + whole-document revision;
- partial metadata/section update không yêu cầu caller resend untouched whole document;
- stale whole-document revision phải conflict.

## 3. Registry và System Map

`repos.yaml` là canonical owner của workspace/repository registry: workspace name, repository name, exact Git-root path, role, `required_for` và dependency basics (`depends_on`). Xác nhận mọi path là exact Git root và dependency reference trỏ tới repository đã khai báo.

`SYSTEM_MAP.md` chỉ giữ cross-repo semantic facts không suy ra được từ registry: contract, ownership/data boundary, non-trivial integration behavior, compatibility/deprecation/rollback và shared-infrastructure facts. Không copy full repository list/path/role/dependency sang System Map. **dependency-only** repository selection/wave không cần đọc `SYSTEM_MAP.md`.

## 4. Herdr/qiqi_delegate

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
uv sync --project mcp/qiqi_delegate
python3 -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

Runtime state nằm dưới `.qiqi/state/` và chỉ là session/turn lifecycle truth, không phải semantic completion truth.

## 5. Canonical Work Item behavior

Với task có stable ID như `redmine:116655`:

1. QiQi `work_item_get` bounded current state trước orchestration;
2. nếu task mới/not found, `work_item_create` trước substantive delegation;
3. scoped `work_item_history_read` chỉ khi exact provenance thực sự cần;
4. reconcile current requirements/repo state/open lifecycle state/next actions;
5. choose repo/wave;
6. QiQi distill repo-local TaskPacket **không chứa Work Item ID/revision**;
7. child làm current repo từ immutable TaskPacket + repo/stable policy và trả exact native evidence;
8. QiQi reread latest Work Item khi dependent decision cần current canonical truth;
9. QiQi reconcile returned evidence, stale materiality, phase/status/next action bằng exact latest revision.

Task có Work Item và task không có Work Item phải có child-facing semantics tương đương khi objective/scope/acceptance/premises giống nhau.

`phase` không phải FSM cứng; UAT → fix → UT → IT → UAT hợp lệ.

## 6. TaskPacket contract

TaskPacket là **smallest sufficient repo-local problem contract** và là **immutable semantic snapshot** cho một delegated turn.

```text
repository                 runtime routing arg
route                      runtime routing arg
objective                  required task semantic
scope[]                    required task semantic
acceptance_criteria[]      required task semantic
out_of_scope[]?            optional
context?                   optional
  trusted_facts[]?         {fact, source}
  claims_to_investigate[]? {claim, source}
constraints[]?             optional
known_unknowns[]?          optional
session_id?                runtime continuity arg
```

Không có child-facing `user_request`, Work Item ref/revision hoặc normal `verification` field.

- `trusted_fact`: execution premise child MAY rely on; trusted-for-execution không đồng nghĩa independently verified truth.
- `claim_to_investigate`: child MUST NOT assume; confirm/contradict/unresolved theo scope.
- `known_unknown`: child MUST NOT silently assume away.
- Acceptance nói WHAT phải chứng minh; child discover HOW từ current repo/stable policy. Exact method/command chỉ bắt buộc khi method itself là contractual requirement.

### Material semantics survive distillation

QiQi có thể bỏ original wording/history, nhưng mọi semantic element có thể đổi objective/scope/constraint/acceptance/external premise/unresolved decision phải survive distillation.

`smallest sufficient` đánh giá bằng:

- **completeness:** context-naive child hiểu WHAT/boundary/premises/acceptance không cần hidden QiQi/Work Item state;
- **minimality:** datum task-specific chỉ ở packet nếu bỏ nó có thể làm child hiểu sai assignment hoặc QiQi accept sai result.

Character/token count là performance metric phụ, không được dùng để truncate material semantics.

## 7. Task-semantic closed world

Child MUST NOT dùng Work Item, Shared Knowledge, sibling repo hoặc QiQi workspace/orchestration state để reconstruct objective/scope/product decision/constraint/acceptance bị thiếu.

Missing material semantics là coordinator-contract failure/blocker. Child surface exact missing input để QiQi repair/resume/redelegate; không tự search global task state để đoán.

Self-sufficiency chỉ áp dụng cho **task meaning**. Child vẫn MAY dùng:

```text
current repo
stable execution policy/environment
allowed Shared Knowledge cho reusable repo/domain implementation knowledge
authorized runtime/log/API/DB/browser/infra evidence
```

khi task/policy cho phép.

## 8. Knowledge progressive disclosure và child boundary

Ở QiQi layer, Knowledge có thể ảnh hưởng TaskPacket semantics; material external/product premise phải được distill vào TaskPacket.

Ở child layer, Knowledge MAY dùng cho reusable implementation/domain knowledge phát sinh sau repo discovery nếu stable policy cho phép. Knowledge **không phải fallback cho incomplete TaskPacket**.

Progressive read:

1. `knowledge_search`;
2. chọn exact candidate;
3. `knowledge_read` / `knowledge_read_metadata` / `knowledge_read_section` ở smallest sufficient scope;
4. owner source/test thắng stale Knowledge cho current implementation;
5. mutation chỉ khi authority/policy cho phép và dùng whole-document revision concurrency.

## 9. Greenfield decision authority

Trong requirement-only repo, child MAY tự chọn reversible technical decision không materially đổi:

- observable product semantics;
- public/external contract;
- security/compliance semantics;
- significant cost/operational envelope.

Decision vượt boundary phải surface options/trade-offs/open decision về QiQi/user.

## 10. Stale semantics

Sau START, TaskPacket không mutate. QiQi chịu trách nhiệm stale detection/materiality/reconciliation.

```text
canonical state change
        ↓
QiQi evaluates materiality
        ↓
non-material
  → child may settle
  → reconcile against latest truth

material
  → stale result MUST NOT become current truth
  → cancel / interrupt / resume / redelegate / reconcile
    tùy runtime capability
```

Normative requirement là stale result không được promote thành current truth; interrupt không phải mandatory mechanism.

## 11. Native result/RESUME

Settled/failed trả exact native `agent_response`. Blocked trả `agent_response=null` + exact `session_id`. Không viewport/transcript fallback.

`settled | failed | blocked` chỉ là runtime lifecycle state. Không thêm semantic `completed | partial | blocked` envelope; QiQi đọc native response và quyết định semantic completion.

START không có session ID; RESUME dùng exact native ID của cùng repo/agent conversation. Session continuity khác canonical task continuity.

## 12. Fresh-session acceptance smoke

Trên repo test an toàn:

1. QiQi thấy Work Item + đủ 6 Knowledge tools; repository child không cần Work Item để hiểu assignment;
2. cùng repo-local assignment được delegate một lần no-Work-Item và một lần tracked-by-Work-Item với child-facing semantics tương đương;
3. TaskPacket không render original ticket/history/Work Item ID/revision/normal verification command;
4. empty optional fields không tạo headings/fallback prose;
5. missing task semantics khiến child surface blocker, không query Work Item/Knowledge để reconstruct task;
6. child discover reusable legacy connector concern và MAY dùng Shared Knowledge nếu stable policy cho phép;
7. stale Knowledge không override current owner source/test;
8. runtime/external evidence task MAY dùng authorized logs/API/DB/browser tools;
9. greenfield child surface product/security/compliance/material-cost decisions vượt technical authority;
10. canonical state material change trong lúc child chạy: stale result không được QiQi promote thành current truth;
11. native qiqi_delegate hook/RESUME smoke pass cho agent family thực sự dùng;
12. dependency-only orchestration chọn repo/wave từ `repos.yaml` không hydrate `SYSTEM_MAP.md`.

## 13. Workspace đã cài harness

Không rsync đè template. Từ harness checkout mới:

```bash
bash scripts/migrate-workspace.sh --dry-run /path/to/workspace
bash scripts/migrate-workspace.sh /path/to/workspace
bash scripts/migrate-workspace.sh --status /path/to/workspace
bash scripts/migrate-workspace.sh --verify /path/to/workspace
```

Đây là breaking public schema change của `qiqi_delegate` 0.2.x: existing QiQi/workspace policy phải migrate coordinated với server/tool schema. Migration không tự sửa user MCP config. Mở fresh agent session để client discover `delegate_repo_task` schema mới.

## Acceptance gate

```text
work-item-template checker PASS
knowledge-template checker PASS
workspace-check PASS
qiqi_delegate unit/schema checks PASS
fresh TaskPacket no-Work-Item / Work-Item equivalence PASS
missing-task-semantics boundary PASS
legitimate child Knowledge/runtime-evidence smoke PASS
stale-result reconciliation smoke PASS
native qiqi_delegate smoke PASS
```

Static/unit test không thay external CLI/user-MCP smoke.
