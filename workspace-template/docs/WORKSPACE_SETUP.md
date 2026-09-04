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

Có thể dùng `--db-path`. Mở fresh agent session rồi xác minh:

```bash
codex mcp get work_item
claude mcp get work_item
```

Fresh client phải discover:

```text
work_item_get
work_item_history_read
work_item_list
work_item_create
work_item_update
```

Smoke DB test/non-production:

1. create test Work Item;
2. `work_item_get` revision 1 và xác nhận response là bounded current-state projection;
3. `work_item_update` bằng revision 1 với `mutation.operations.checkpoint_append=[{summary: ...}]` → compact receipt revision 2 ngay lần gọi hợp lệ đầu tiên;
4. receipt không chứa full canonical Work Item/checkpoint history;
5. stale revision 1 phải conflict;
6. `work_item_history_read(collection="checkpoints")` vẫn đọc exact stored history khi cần provenance.

`mutation.operations` là **grouped typed object**, không phải list `{op,value}`. Fresh-agent happy path không được probe schema bằng intentionally-invalid `work_item_update` calls.

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

`repos.yaml` là canonical owner của workspace/repository registry: workspace name, repository
name, exact Git-root path, role, `required_for` và dependency basics (`depends_on`). Xác nhận
mọi path là exact Git root và mọi dependency reference trỏ tới repository đã khai báo.

`SYSTEM_MAP.md` chỉ giữ cross-repo semantic facts không suy ra được từ registry: contract,
ownership/data boundary, non-trivial integration behavior, compatibility/deprecation/rollback
và shared-infrastructure facts. Không copy full repository list/path/role/dependency sang
System Map. dependency-only repository selection/wave không cần đọc `SYSTEM_MAP.md`.

## 4. Herdr/qiqi_delegate

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
uv sync --project mcp/qiqi_delegate
python3 -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

Runtime state nằm dưới `.qiqi/state/` và chỉ là session/turn truth.

## 5. Canonical Work Item behavior

Với task có stable ID như `redmine:116655`:

1. QiQi `work_item_get` bounded current state trước orchestration;
2. nếu task mới/not found, `work_item_create` trước substantive delegation;
3. scoped `work_item_history_read` chỉ khi exact provenance thực sự cần;
4. reconcile current requirements/repo state/open lifecycle state/next actions;
5. choose repo/wave;
6. TaskPacket truyền Work Item ID + exact whole revision;
7. child `work_item_get`, làm current repo, persist current repo state bằng `mutation.state` + smallest direct groups dưới `mutation.operations` (`checkpoint_append`, blocker/question/handoff upsert);
8. QiQi đọc full native response rồi reread bounded Work Item khi dependent orchestration decision cần resulting state;
9. QiQi reconcile global phase/status/next action bằng exact latest revision.

Historical semantic collections không được reconstruct/resend như full-array mutation. `mutation.operations` có direct typed groups, tối đa 50 semantic records tổng cộng/call, commit all-or-nothing trên một final candidate, và stale writer không được server auto-rebase. Cross-group caller order không phải public semantics.

`phase` không phải FSM cứng; UAT → fix → UT → IT → UAT hợp lệ.

## 6. Questions/decisions/requirement changes

Ambiguity chưa chốt → `operations.question_upsert` tạo open question. User/customer Q&A chốt có thể dùng một atomic grouped mutation:

```text
operations.decision_upsert = [new active decision, old decision -> superseded nếu cần]
operations.question_upsert = [open -> resolved]
state.current_requirements nếu effective semantics đổi
operations.change_upsert nếu requirement/scope thực sự đổi
```

Decision bị thay dùng monotonic `active -> superseded` + `superseded_by`; không rewrite historical summary/provenance. Cross-record reference validate trên final candidate document nên create successor + supersede old + resolve question có thể commit trong cùng revision mà không phụ thuộc cross-group execution order.

## 7. Cross-repo behavior

```text
repo A evidence
→ operations.handoff_upsert pending
→ native response về QiQi
→ QiQi reread/reconcile
→ delegate repo B
```

Child không tự sửa/delegate sibling repo.

## 8. Knowledge progressive disclosure

Sau khi hiểu concern:

1. tạo 3–8 discriminative concepts;
2. `knowledge_search`;
3. chọn 1–2 exact candidates;
4. exact-read smallest sufficient semantic scope:
   - full `knowledge_read` khi cần whole concept;
   - `knowledge_read_metadata` khi chỉ cần metadata/provenance/revision + section index;
   - `knowledge_read_section` khi chỉ cần one existing marked section;
5. material use/update dựa trên exact read đủ scope, không search card;
6. before create/update search dedupe; existing update target lấy exact revision từ exact read;
7. create/intentional whole replacement dùng `knowledge_write`;
8. metadata/content/one-section partial mutation dùng `knowledge_update` và vẫn cạnh tranh trên one whole-document revision;
9. substantive reusable conclusion review/mutation theo knowledge-distill policy.

Fact từ Knowledge mà QiQi dùng làm delegation premise và không nằm trong Work Item vẫn phải inline TaskPacket với provenance.

## 9. TaskPacket contract

```text
repository
route
user_request
objective
scope
out_of_scope
required_context
constraints
acceptance_criteria
verification
known_unknowns
session_id?
```

`scope` và `acceptance_criteria` non-empty. `required_context` item có `fact`, `source`, `certainty`; certainty chỉ `verified`, `user-provided`, `authoritative-decision`.

## 10. Native result/RESUME

Settled/failed trả exact native `agent_response`. Blocked trả `agent_response=null` + exact `session_id`. Không viewport/transcript fallback.

START không có session ID; RESUME dùng exact native ID của cùng repo/agent conversation. Task continuity đến từ Work Item, không infer session từ task ID.

## 11. Fresh-session acceptance smoke

Trên repo test an toàn:

1. QiQi thấy `work_item_*` gồm scoped history + grouped typed incremental update và đủ 6 Knowledge tools;
2. QiQi create/get test Work Item; GET không hydrate accumulated history;
3. fresh agent append checkpoint bằng `operations.checkpoint_append` thành công ở **first valid attempt**, không schema-probing, không gửi historical checkpoints, receipt compact;
4. fresh agent partial-resolve blocker/question bằng direct group thành công ở **first valid attempt**, không resend immutable body/full collection;
5. old `operations:[{op,value}]` shape bị schema reject và không xuất hiện trong declared public schema/skill;
6. history cursor stale/cross-item bị reject đúng contract;
7. delegate TaskPacket identify task/revision;
8. child đọc cùng Work Item và chỉ mutate current-repo authority;
9. stale Work Item writer conflict dù target khác collection;
10. Knowledge search card thin + metadata/section/full exact reads đúng scope;
11. partial Knowledge update preserve untouched canonical state và stale revision bị reject;
12. child không mở sibling repo/physical DB/store;
13. qiqi_delegate native hook/RESUME smoke pass cho agent family thực sự dùng;
14. dependency-only orchestration chọn repo/wave từ `repos.yaml` mà không hydrate `SYSTEM_MAP.md`;
15. contract/ownership/compatibility-impact task đọc `SYSTEM_MAP.md` và lấy đúng semantic fact ngoài registry.

Happy-path acceptance có **zero intentionally-invalid schema discovery calls**. Validation errors dùng để reject bad input, không phải runtime discovery protocol.

## 12. Workspace đã cài harness

Không rsync đè template. Từ harness checkout mới:

```bash
bash scripts/migrate-workspace.sh --dry-run /path/to/workspace
bash scripts/migrate-workspace.sh /path/to/workspace
bash scripts/migrate-workspace.sh --status /path/to/workspace
bash scripts/migrate-workspace.sh --verify /path/to/workspace
```

Cài user-scoped Work Item/Knowledge MCP là explicit operator step; migration không tự sửa user MCP config. Sau Work Item public read/write contract change phải rerun `work-item-template/scripts/install-user-mcp.sh` từ checkout mới; sau Knowledge public-tool change phải rerun `knowledge-template/scripts/install-user-mcp.sh`. Mở fresh agent session để client discover schema mới.

## Acceptance gate

```text
work-item-template checker PASS
knowledge-template checker PASS
workspace-check PASS
fresh QiQi Work Item discovery/read/grouped-update PASS without schema probing
fresh child Work Item discovery/update PASS
Knowledge scoped progressive-disclosure smoke PASS
native qiqi_delegate smoke PASS
```

Static/unit test không thay external CLI/user-MCP smoke.
