# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này setup `workspace-template/` sau khi Shared Knowledge MCP đã được cài
user/global scope từ `knowledge-template/`.

## Kết quả cần đạt

- `repos.yaml` trỏ đúng exact Git roots và không alias trùng root;
- `SYSTEM_MAP.md` giữ live topology/ownership/dependency;
- project-scoped `.codex/config.toml` chỉ đăng ký `qiqi_delegate`;
- user-scoped MCP `knowledge` có mặt trong fresh QiQi và fresh child Codex/Claude;
- Knowledge MCP expose đủ `knowledge_search`, `knowledge_read`, `knowledge_write`;
- QiQi delegate bằng structured TaskPacket, không opaque prompt string;
- mọi required live fact QiQi đã dùng để quyết định semantics nằm trong
  `required_context` kèm provenance/certainty;
- child áp dụng closed-world context rule và không đọc sibling source/result/runtime;
- native final assistant response đi thẳng về QiQi qua Stop hook;
- Codex chỉ auto-trust exact QiQi result hook, không bypass trust cho hook khác;
- blocked START/RESUME không làm mất native `session_id`;
- runtime state nằm dưới `.qiqi/state/`, không dùng Markdown result làm transport;
- Herdr integrations ở trạng thái `current`;
- static/unit checker pass;
- native Stop-hook smoke pass trên installed CLI thật cho adapter family thực sự dùng.

## Bước 1: Cài Shared Knowledge MCP ngoài workspace

Từ source `knowledge-template/`:

```bash
bash scripts/install-user-mcp.sh --store-root /path/to/shared-knowledge/store
```

Mở fresh agent session sau registration. Xác minh CLI registration:

```bash
codex mcp get knowledge      # nếu dùng Codex
claude mcp get knowledge     # nếu dùng Claude
```

Knowledge MCP không được thêm vào workspace `.codex/config.toml`. Store root nằm sau
stable user wrapper; current workspace/repo/CWD không quyết định store nào được dùng.

Smoke tối thiểu trong fresh QiQi session:

1. tool inventory có `knowledge_search`, `knowledge_read`, `knowledge_write`;
2. `knowledge_search` query không match trả results rỗng, không crash;
3. search card không trả `content`, `sources`, `revision` hoặc physical `path`;
4. `knowledge_read` chỉ nhận exact IDs và hydrate tối đa hai IDs/call;
5. không tạo test knowledge chỉ để smoke khi chưa có durable fact thực.

## Bước 2: Điền Repository Registry

Xác nhận từng repo:

```bash
git -C <repository-path> rev-parse --show-toplevel
git -C <repository-path> remote -v
git -C <repository-path> branch --show-current
git -C <repository-path> status --short
```

Điền `repos.yaml` bằng path tương đối từ workspace root. Mỗi path phải là exact Git
root. Không tạo hai registry entries resolve về cùng root.

## Bước 3: Điền System Map

Điền `SYSTEM_MAP.md` từ live evidence cho topology/dependency/contract/ownership liên
repo. Đây là live workspace artifact, không phải Shared Knowledge Store.

## Bước 4: Cài Herdr integrations

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

Selected adapter phải `current`. `qiqi_delegate` không tự install integration.

## Bước 5: Agent Routing v2

`instructions/agent-routing.yaml` là canonical machine-readable runtime registry.
`instructions/model-routing.md` chỉ là exact-route selection policy cho QiQi.

Runtime placeholders:

```text
{model}
{session_id}
{route_args}
{handoff_args}
```

`{handoff_args}` phải xuất hiện đúng một lần trong `start_args` và `resume_args` mỗi
agent. Route không sở hữu Stop hook, hook sink hoặc result transport. Không còn
`{result_dir}` hoặc result-path placeholder.

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

`.codex/config.toml` chỉ expose `delegate_repo_task`. Knowledge MCP đến từ user
configuration.

Runtime state:

```text
.qiqi/state/qiqi_delegate.sqlite3
.qiqi/state/active-captures/*.json
```

SQLite giữ session/turn ownership. `active-captures/` là private ephemeral routing
metadata cho native hook; descriptor được tạo atomic `0600` và xóa khi delegation
kết thúc. Toàn bộ `.qiqi/state/` được gitignore. QiQi/child không đọc/sửa state trực
tiếp.

`.qiqi/runs/` có thể còn từ architecture cũ; chỉ dùng như legacy ownership-import
bridge cho exact old sessions, không làm semantic result/history cho turn mới.

## Bước 7: Public TaskPacket contract

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

- `user_request`, `objective`, `scope`, `acceptance_criteria` non-empty;
- list khác truyền `[]` khi thực sự không có item;
- mỗi `required_context` item có đúng:

```json
{
  "fact": "...",
  "source": "...",
  "certainty": "verified | user-provided | authoritative-decision"
}
```

Tổng serialized TaskPacket giữ safety boundary hiện có; không tự đặt guessed
per-field limits hoặc native-response size limit mới.

## Bước 8: Context boundary

Execution agent không chia sẻ hidden conversation/reasoning/workspace control context
hoặc sibling state của QiQi.

Nếu QiQi đã dùng fact để quyết định repository, dependency, scope, constraint,
acceptance criterion hoặc task semantics, fact đó **phải** nằm trong
`required_context` kèm provenance. Không kỳ vọng child tự query lại đúng knowledge
item.

Child vẫn được tự inspect current owner repo và query Shared Knowledge MCP theo repo
policy để discover/enrich/verify context khác. Child không tự mở sibling
source/result/runtime state để bù external input thiếu.

## Bước 9: Progressive Shared Knowledge trong QiQi/child

Retrieval lifecycle:

```text
knowledge_search(keywords, context?, limit?)
→ bounded decision cards
→ chọn 1–2 exact IDs
knowledge_read(ids)
→ full semantic payload + provenance + revision
```

Rules:

1. Hiểu concern trước rồi tạo khoảng 3–8 discriminative concepts.
2. Search card chỉ phục vụ chọn document; không coi summary/card là full evidence khi
   material conclusion cần content/provenance/uncertainty.
3. `context.repo/domain` chỉ boost ranking; không permission-filter namespace.
4. Search cố ý không trả revision; existing knowledge phải full-read trước update.
5. Không hydrate top-N chỉ vì search limit lớn.
6. Search/read stale index phải fail rõ; live owner source/test vẫn thắng conflict.
7. Fact QiQi đã dùng cho downstream semantics phải được inline vào
   `required_context`, không để child phải rediscover nó.

## Bước 10: Native result handoff

### Settled / failed

START không `session_id`; RESUME dùng exact native ID cũ. Khi native final message đã
có, MCP trả:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled | failed",
  "agent_response": "<exact native final assistant message>"
}
```

Agent tự chọn structure; không fixed headings. QiQi đọc **toàn bộ `agent_response`**
rồi reconcile với TaskPacket. MCP capture native message bằng Stop hook, không dùng
terminal viewport và không parse transcript.

### Blocked continuity

Ngay khi native `session_id` được Herdr xác nhận, MCP persist ownership trước mọi
blocked/result-capture branch. Nếu Herdr trả `blocked` trước native final response:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "blocked",
  "agent_response": null,
  "blocker_type": "agent_blocked"
}
```

QiQi giữ exact session ID và chỉ RESUME sau khi missing external input/approval được
giải quyết. Không xem `agent_response=null` là report bị cắt và không invent blocker
content từ screen/transcript.

Nếu native result hook thiếu/invalid sau khi session identity đã có, call fail rõ và
error phải giữ exact `session_id` còn resumable; không fallback sang screen/transcript.

## Bước 11: Stop-hook security model

Hook command không chứa per-turn sink/nonce, chỉ Python executable, `result_hook.py`,
adapter và static workspace state root. MCP ghi private descriptor cho
`(adapter, exact repo root)` dưới `.qiqi/state/active-captures/`; hook dùng native
`cwd` + `session_id` để resolve đúng turn.

### Codex — selective session trust

QiQi inject session config cho exact static Stop hook và `trusted_hash` chỉ cho hook
key đó. **Không launch child với `--dangerously-bypass-hook-trust`**, không trust-all
và không ghi persistent trust vào user config. Unrelated hooks giữ native trust state.

### Claude

QiQi inject invocation-scoped `--settings` chứa chỉ QiQi `Stop`/`StopFailure` hook;
không thay unrelated hook permission/trust configuration.

Private capture sink/event phải giữ permission/nonce/adapter/session validation và
fail closed nếu capture invalid; không fallback screen/transcript.

## Bước 12: Knowledge MCP trong Herdr child

Dùng repo test và read-only TaskPacket khi decision rule thực sự yêu cầu knowledge:

1. child thấy đủ ba tools;
2. `knowledge_search` trả decision cards;
3. child chỉ `knowledge_read` exact relevant IDs;
4. child không mở sibling repo hoặc external knowledge filesystem path;
5. child trả native final response bình thường.

Lặp cho mỗi adapter family thực sự dùng. Nếu child không thấy tool, sửa user/global
MCP registration; không workaround bằng per-repo knowledge store/config.

## Bước 13: Acceptance smoke — installed Claude/Codex thật

**Unit test không thay bước này.** Native hook payload/CLI option và Codex hook
fingerprint/trust behavior là external contract của installed agent CLI.

Smoke tối thiểu cho mỗi adapter family thực sự dùng:

1. **Selective hook trust:** Codex argv không có broad bypass; QiQi hook chạy; unrelated
   hook trust không bị thay đổi.
2. **Full response vượt viewport:** START response Unicode dài giữ nguyên marker đầu/cuối,
   không tạo result Markdown mới.
3. **RESUME exact session:** cùng native session ID, turn ID mới; cross-repo/family
   resume bị reject.
4. **Native capture fail-closed:** hook/capture invalid làm delegation fail rõ; không
   screen/transcript fallback; session ID đã biết vẫn được preserve.
5. **Blocked continuity:** khi có deterministic fixture, blocked return giữ exact
   session ownership và `agent_response=null`.
6. **Knowledge progressive disclosure:** fresh QiQi/child thấy search/read/write;
   search thin, read exact/bounded, stale revision update bị reject.

Chỉ coi workspace production-ready khi static/unit checker và required native CLI
smoke đều pass.
