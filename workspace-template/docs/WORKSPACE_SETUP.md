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

Smoke DB test/non-production:

1. create test Work Item;
2. get revision 1;
3. update bằng revision 1 → revision 2;
4. stale revision 1 phải conflict.

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

Xác nhận mỗi `repos.yaml` path là exact Git root. `SYSTEM_MAP.md` giữ live topology/ownership/dependency; Work Item không thay System Map.

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

1. QiQi `work_item_get` trước orchestration;
2. nếu task mới/not found, `work_item_create` trước substantive delegation;
3. reconcile `current_requirements`, questions/decisions/changes, repo states, blockers, handoffs, next actions;
4. choose repo/wave;
5. TaskPacket truyền Work Item ID + revision;
6. child `work_item_get` current state, làm current repo, persist repo evidence/handoff/checkpoint;
7. QiQi đọc full native response rồi `work_item_get` lại;
8. QiQi reconcile global phase/status/next action.

`phase` không phải FSM cứng; UAT → fix → UT → IT → UAT hợp lệ.

## 6. Questions/decisions/requirement changes

Ambiguity chưa chốt → open question. User/customer Q&A chốt → resolve question + active decision. Nếu semantics/scope đổi, update effective requirements + `changes[]`. Decision bị thay dùng `superseded_by`.

## 7. Cross-repo behavior

```text
repo A evidence
→ Work Item handoff A -> B
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

1. QiQi thấy `work_item_*` và đủ 6 Knowledge tools;
2. QiQi create/get test Work Item;
3. delegate TaskPacket identify task/revision;
4. child đọc cùng Work Item;
5. child chỉ update current-repo evidence;
6. QiQi reread thấy revision mới;
7. stale Work Item writer conflict;
8. Knowledge search card thin + metadata/section/full exact reads đúng scope;
9. partial Knowledge update preserve untouched canonical state và stale revision bị reject;
10. child không mở sibling repo/physical DB/store;
11. qiqi_delegate native hook/RESUME smoke pass cho agent family thực sự dùng.

## 12. Workspace đã cài harness

Không rsync đè template. Từ harness checkout mới:

```bash
bash scripts/migrate-workspace.sh --dry-run /path/to/workspace
bash scripts/migrate-workspace.sh /path/to/workspace
bash scripts/migrate-workspace.sh --status /path/to/workspace
bash scripts/migrate-workspace.sh --verify /path/to/workspace
```

Cài user-scoped Work Item/Knowledge MCP là explicit operator step; migration không tự sửa user MCP config. Sau Knowledge public-tool change phải rerun `knowledge-template/scripts/install-user-mcp.sh` từ harness checkout mới và mở fresh agent session để client discover tool surface mới.

## Acceptance gate

```text
work-item-template checker PASS
knowledge-template checker PASS
workspace-check PASS
fresh QiQi Work Item discovery PASS
fresh child Work Item discovery/update PASS
Knowledge scoped progressive-disclosure smoke PASS
native qiqi_delegate smoke PASS
```

Static/unit test không thay external CLI/user-MCP smoke.
