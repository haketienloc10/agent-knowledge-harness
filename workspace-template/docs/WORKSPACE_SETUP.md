# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này setup `workspace-template/` sau khi hai user-scoped service đã được cài:

- Global Work Item MCP từ `work-item-template/`;
- Shared Knowledge MCP từ `knowledge-template/`.

Bốn nguồn truth phải giữ độc lập:

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

## Kết quả cần đạt

- `repos.yaml` trỏ đúng exact Git roots và không alias trùng root;
- `SYSTEM_MAP.md` giữ live topology/ownership/dependency;
- project-scoped `.codex/config.toml` chỉ đăng ký `qiqi_delegate`;
- user-scoped MCP `work_item` và `knowledge` có mặt trong fresh QiQi + child sessions;
- workspace không có `.qiqi/tasks/` task store;
- product task có canonical Work Item như `redmine:116655`;
- QiQi đọc Work Item trước orchestration và reread sau repo turn;
- child đọc cùng Work Item nhưng chỉ execute/update evidence thuộc current Git root;
- cross-repo remaining work quay lại QiQi qua Work Item handoff + native response;
- TaskPacket giữ structured external context, không opaque prompt string;
- native final assistant response đi thẳng về QiQi qua Stop hook;
- blocked START/RESUME không làm mất native `session_id`;
- runtime state nằm dưới `.qiqi/state/`, không làm semantic task store;
- static/unit checker pass;
- fresh-session Work Item/Knowledge MCP smoke pass;
- native Stop-hook smoke pass trên installed CLI thật cho adapter family được dùng.

## Bước 1: Cài Global Work Item MCP ngoài workspace

Từ source `work-item-template/`:

```bash
bash scripts/install-user-mcp.sh
```

Default database:

```text
~/.local/share/agent-work-items/work-items.sqlite3
```

Có thể override:

```bash
bash scripts/install-user-mcp.sh --db-path /path/to/work-items.sqlite3
```

Mở fresh agent session rồi xác minh registration:

```bash
codex mcp get work_item      # nếu dùng Codex
claude mcp get work_item     # nếu dùng Claude
```

`work_item` không được thêm vào workspace `.codex/config.toml`. Database path nằm sau
stable user wrapper và không phụ thuộc current CWD.

Smoke tối thiểu:

1. tool inventory có `work_item_get`, `work_item_list`, `work_item_create`,
   `work_item_update`;
2. tạo một test Work Item canonical trong DB test/non-production;
3. `work_item_get` trả `revision=1`;
4. update bằng exact revision tạo revision mới;
5. update lại bằng stale revision bị reject;
6. không để test item rác trong production DB.

## Bước 2: Cài Shared Knowledge MCP ngoài workspace

Từ `knowledge-template/`:

```bash
bash scripts/install-user-mcp.sh --store-root /path/to/shared-knowledge/store
```

Xác minh fresh session:

```bash
codex mcp get knowledge      # nếu dùng Codex
claude mcp get knowledge     # nếu dùng Claude
```

Knowledge MCP không được thêm vào workspace project config. Không tạo test knowledge
chỉ để smoke khi chưa có durable fact thực.

## Bước 3: Điền Repository Registry

Xác nhận từng repo:

```bash
git -C <repository-path> rev-parse --show-toplevel
git -C <repository-path> remote -v
git -C <repository-path> branch --show-current
git -C <repository-path> status --short
```

Điền `repos.yaml` bằng path tương đối từ workspace root. Mỗi path phải là exact Git
root. Không tạo hai entries resolve về cùng root.

## Bước 4: Điền System Map

Điền `SYSTEM_MAP.md` từ live evidence cho topology/dependency/contract/ownership liên
repo. Work Item không thay System Map; Work Item giữ state của product task cụ thể.

## Bước 5: Cài Herdr integrations

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

Selected adapter phải `current`. `qiqi_delegate` không tự install integration.

## Bước 6: Chuẩn bị qiqi_delegate

```bash
uv sync --project mcp/qiqi_delegate
bash -n scripts/qiqi-mcp-server.sh
python3 -m py_compile \
  mcp/qiqi_delegate/core.py \
  mcp/qiqi_delegate/result_hook.py \
  mcp/qiqi_delegate/server.py
python3 -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

`.codex/config.toml` chỉ expose `delegate_repo_task`. `work_item` và `knowledge` đến
từ user configuration.

Runtime state:

```text
.qiqi/state/qiqi_delegate.sqlite3
.qiqi/state/active-captures/*.json
```

Đây là native session/turn ownership và ephemeral hook-routing state, không phải
product task state. QiQi/child không đọc/sửa trực tiếp.

`.qiqi/runs/` chỉ là legacy session-ownership import bridge. `.qiqi/tasks/` không
được tồn tại trong architecture mới.

## Bước 7: Canonical Work Item behavior của QiQi

Với product task có identity ổn định như `redmine:116655`:

1. QiQi `work_item_get` trước khi reconstruct plan;
2. nếu not found và đây là task mới, QiQi `work_item_create` trước substantive work;
3. reconcile `current_requirements`, questions/decisions/changes, repo states,
   blockers, handoffs và next actions;
4. chọn repo/wave;
5. delegate repo-local work;
6. đọc full native `agent_response`;
7. `work_item_get` lại để thấy update child đã persist;
8. QiQi reconcile global `status/phase/summary/next_actions`;
9. chỉ mark `done` khi effective requirements + verification + mandatory handoffs,
   questions và blockers đều đã xử lý.

Work Item `phase` không phải finite-state-machine. Loop UAT → fix → UT → IT → UAT là
hợp lệ.

## Bước 8: Questions, decisions và requirement changes

Open ambiguity chưa thể tự chốt được persist vào `questions[]` thay vì nằm chỉ trong
conversation.

Khi user/customer Q&A trả lời:

```text
question resolved
→ decision active
→ current_requirements reconcile nếu semantics đổi
→ changes[] nếu requirement/scope thực sự đổi
```

Decision cũ bị thay không bị xóa: mark `superseded` + `superseded_by`.

Mục tiêu là sau nhiều ngày vẫn trả lời được:

- hiện tại requirement hiệu lực là gì;
- câu hỏi nào còn mở;
- ai/nguồn nào đã chốt điều gì;
- requirement thay đổi ở đâu;
- vì sao implementation hiện tại đi theo hướng đó.

## Bước 9: Cross-repo behavior

Agent con chỉ làm current Git root. Khi repo A phát hiện repo B còn việc:

```text
repo A evidence
→ Work Item handoff A -> B + evidence
→ native response về QiQi
→ QiQi reread/reconcile
→ delegate repo B
```

Child không tự sửa/delegate sibling repo. Không cần copy toàn bộ Work Item vào
TaskPacket vì repo B đọc same canonical Work Item.

## Bước 10: Public TaskPacket contract

`delegate_repo_task` nhận:

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

Rules tối thiểu:

- `user_request`/`objective` non-empty;
- `scope` và `acceptance_criteria` non-empty;
- mỗi `required_context` item có `fact`, `source`, `certainty`;
- certainty là `verified`, `user-provided`, `authoritative-decision`;
- khi turn thuộc Work Item, QiQi truyền canonical Work Item ID + revision trong
  `required_context`, ví dụ `redmine:116655 @ revision 12`;
- child gọi `work_item_get` để lấy revision/state mới nhất;
- external fact ngoài Work Item mà QiQi đã dùng để quyết định semantics vẫn phải
  inline với provenance/certainty;
- tổng serialized TaskPacket giữ safety boundary 100.000 ký tự.

## Bước 11: Context boundary

Child không chia sẻ hidden conversation, hidden reasoning, workspace control context
hoặc sibling source/runtime state của QiQi.

Allowed task context:

```text
canonical Work Item identified by TaskPacket
+ current repo source/test
+ TaskPacket external facts
+ Shared Knowledge when repo policy requires
```

Work Item/Knowledge tool access không nới filesystem boundary.

Nếu current Work Item revision mới hơn packet và làm objective/constraint conflict,
child phải báo conflict thay vì silently làm theo stale prompt.

## Bước 12: Optimistic concurrency smoke

Dùng DB test:

1. QiQi đọc revision N;
2. child đọc cùng revision N;
3. child update → N+1;
4. QiQi thử update với `expected_revision=N` → phải conflict;
5. QiQi reread N+1, reconcile full intended arrays/nested state, retry → N+2.

`work_item_update` dùng nested JSON merge-patch nhưng arrays replace nguyên tử. Caller
phải giữ lại current array entries không định xóa.

## Bước 13: Native result handoff

Settled/failed:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled | failed",
  "agent_response": "<exact native final assistant message>"
}
```

Blocked trước native final response:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "blocked",
  "agent_response": null,
  "blocker_type": "agent_blocked"
}
```

MCP capture native message bằng Stop hook, không viewport/transcript fallback.
Session ownership được persist ngay khi native identity known.

## Bước 14: Stop-hook security model

Codex chỉ trust exact static QiQi Stop hook bằng computed `trusted_hash`. Không dùng
`--dangerously-bypass-hook-trust`.

Claude inject invocation-scoped `--settings` chỉ cho QiQi Stop/StopFailure hook.
Unrelated hooks giữ native trust/permission state.

Dynamic sink/nonce nằm dưới private `.qiqi/state/active-captures/`, không nằm trên
child argv. Capture failure fail closed; nếu native session đã known thì error giữ
exact resumable `session_id`.

## Bước 15: Fresh child Work Item + Knowledge smoke

Trên repo test an toàn, với mỗi agent family thực sự dùng:

1. QiQi tạo/đọc Work Item test;
2. delegate TaskPacket identify Work Item + revision;
3. child xác nhận `work_item_get` available và đọc cùng task;
4. child chỉ update `repos[current_repo]`/checkpoint hoặc handoff được evidence chứng
   minh;
5. QiQi reread thấy revision/state mới;
6. child xác nhận Knowledge MCP available khi decision rule cần;
7. child không mở sibling repo/Work Item DB/Knowledge Store filesystem;
8. cross-repo remaining work quay lại QiQi, không được child tự dispatch.

## Bước 16: Native CLI acceptance smoke

Unit test không thay bước này. Với mỗi adapter family thực sự dùng, cover ít nhất:

1. **Selective hook trust** — Codex argv không có global bypass; Claude settings chỉ
   inject QiQi hook.
2. **Long Unicode response** — START response vượt viewport vẫn giữ marker đầu/cuối.
3. **Exact RESUME** — same session ID, new turn ID; cross-repo/agent resume reject.
4. **Capture fail-closed** — không screen/transcript fallback; known session ID vẫn
   resumable.
5. **Blocked continuity** — nếu adapter có fixture ổn định, blocked return giữ native
   session ownership mà không fake blocker text.

## Acceptance gate

Chỉ coi workspace sẵn sàng khi:

```text
work-item-template checker PASS
knowledge-template checker PASS
workspace-check PASS
fresh QiQi Work Item discovery PASS
fresh child Work Item discovery/update PASS
fresh child Knowledge discovery PASS
native qiqi_delegate smoke PASS cho agent family thực sự dùng
```

Checker/unit test không được dùng để tuyên bố external CLI/user-MCP smoke đã pass.
