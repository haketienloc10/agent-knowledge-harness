# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này setup `workspace-template/` sau khi Shared Knowledge MCP đã được cài
user/global scope từ `knowledge-template/`.

## Kết quả cần đạt

- `repos.yaml` trỏ đúng exact Git roots và không alias trùng root;
- `SYSTEM_MAP.md` giữ live topology/ownership/dependency;
- project-scoped `.codex/config.toml` chỉ đăng ký `qiqi_delegate`;
- user-scoped MCP `knowledge` có mặt trong fresh QiQi session và fresh child
  Codex/Claude session;
- QiQi delegate bằng structured TaskPacket, không opaque prompt string;
- mọi required live fact QiQi đã dùng để quyết định semantics nằm trong
  `required_context` kèm provenance/certainty;
- child áp dụng closed-world context rule và không đọc sibling source/result/runtime;
- native final assistant response đi thẳng về QiQi qua Stop hook;
- blocked START/RESUME không làm mất native `session_id`;
- runtime state nằm dưới `.qiqi/state/`, không dùng Markdown artifact làm transport;
- Herdr integrations ở trạng thái `current`;
- static/unit checker pass;
- native Stop-hook smoke pass trên **installed CLI thật** cho adapter family thực sự
  được dùng.

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

Knowledge MCP không được thêm vào workspace `.codex/config.toml`. Store root nằm
sau stable user wrapper; current workspace/repo/CWD không quyết định store nào được
dùng.

Smoke tối thiểu trong fresh QiQi session:

1. tool inventory có `knowledge_read` và `knowledge_write`;
2. query không match trả results rỗng, không crash;
3. không tạo test knowledge chỉ để smoke khi chưa có durable fact thực.

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

Điền `SYSTEM_MAP.md` từ live evidence cho topology/dependency/contract/ownership
liên repo. Đây là live workspace artifact, không phải Shared Knowledge Store.

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

`{handoff_args}` phải xuất hiện đúng một lần trong `start_args` và `resume_args` của
mỗi agent. Giá trị được MCP inject theo invocation; route không sở hữu Stop hook,
hook sink hoặc result transport.

Không còn `{result_dir}` hoặc result-path placeholder.

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

Runtime state được tạo tại:

```text
.qiqi/state/qiqi_delegate.sqlite3
```

Path này gitignored. QiQi/child không đọc hoặc sửa database trực tiếp.

`.qiqi/runs/` có thể còn tồn tại từ architecture cũ. MCP chỉ được đọc metadata
legacy ở đó để import session ownership khi RESUME exact session cũ; turn mới không
đọc/ghi semantic result tại đó.

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

- `user_request` và `objective` non-empty;
- `scope` non-empty;
- `acceptance_criteria` non-empty;
- list khác truyền `[]` khi thực sự không có item;
- mỗi `required_context` item có đúng:

```json
{
  "fact": "...",
  "source": "...",
  "certainty": "verified | user-provided | authoritative-decision"
}
```

Tổng serialized TaskPacket giữ safety boundary 100.000 ký tự, tương ứng public
`task` boundary trước migration. Không đặt guessed per-field limit và không đặt
native-response size limit tự chế.

## Bước 8: Context boundary

Execution agent không chia sẻ hidden conversation, hidden reasoning, workspace
control context hoặc sibling state của QiQi.

Nếu QiQi đã dùng một fact để quyết định repository, dependency, scope, constraint,
acceptance criterion hoặc task semantics, fact đó **phải** nằm trong
`required_context` kèm provenance. Không kỳ vọng child tự query lại đúng knowledge
item đó.

Child vẫn được tự:

- inspect current owner repository;
- query Shared Knowledge MCP khi repo decision rule yêu cầu;
- dùng knowledge để discover/enrich/verify context khác.

Child không tự mở sibling source/result/runtime state để bù external input thiếu.

## Bước 9: Native result handoff

### Settled / failed turn

START không có `session_id`; RESUME dùng exact native ID cũ. Khi native final message
đã tồn tại, MCP trả:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled | failed",
  "agent_response": "<exact native final assistant message>"
}
```

Agent tự chọn structure; không fixed headings. QiQi đọc **toàn bộ
`agent_response`** rồi reconcile với TaskPacket trước bước tiếp theo.

MCP capture native message bằng Stop hook, không dùng terminal viewport và không
parse transcript. Response dài hơn một screen không phụ thuộc scrollback.

### Blocked continuity

Herdr `AgentInfo` có native session identity + status nhưng không bảo đảm một field
chuẩn chứa nguyên văn blocker question. Vì vậy MCP không scrape screen để dựng lại
semantic report.

Ngay khi native `session_id` được Herdr xác nhận, MCP persist ownership trước mọi
blocked/result-capture branch. Nếu Herdr sau đó trả `blocked` trước khi native final
response tồn tại, MCP trả:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "blocked",
  "agent_response": null,
  "blocker_type": "agent_blocked"
}
```

QiQi giữ exact `session_id` và chỉ RESUME sau khi missing external input/approval đã
được giải quyết. Không xem `agent_response=null` là report bị cắt và không invent
blocker content.

Repo policy yêu cầu child ưu tiên finalize một native response mô tả missing external
input thay vì dùng interactive question khi có thể; blocked return là continuity
fallback.

Nếu native result hook thiếu/invalid sau khi session identity đã có, call fail rõ và
error phải ghi session ownership đã được preserve cùng exact `session_id`; không
fallback sang screen/transcript.

## Bước 10: Stop-hook security model

### Claude

MCP inject invocation-scoped `--settings <inline-json>` chứa command hook cho `Stop`
và `StopFailure`. Hook command là `mcp/qiqi_delegate/result_hook.py` chạy bằng cùng
Python executable của MCP.

### Codex

MCP inject invocation-scoped native hook configuration để enable `features.hooks`
và đăng ký MCP-owned `hooks.Stop`. Hook trust bypass chỉ được dùng cho exact
MCP-constructed invocation; không đặt hook configuration vào TaskPacket hoặc route
args.

Operator phải review/remove untrusted custom hooks trước khi chấp nhận Codex
runtime. Handoff hook không được trở thành cách nới trust cho arbitrary workspace
hook.

Hook sink nằm trong private temporary directory của turn. Event được ghi atomic,
permission `0600`; malformed hook input không được block agent turn. MCP validate
nonce/adapter/session identity trước khi nhận event.

## Bước 11: Knowledge MCP trong Herdr child

Dùng một repo test và read-only TaskPacket:

1. child xác nhận `knowledge_read` available;
2. query keyword vô hại khi decision rule thực sự yêu cầu;
3. không mở sibling repo hoặc external knowledge filesystem path;
4. trả native final response bình thường.

Lặp cho mỗi adapter family thực sự dùng. Nếu child không thấy tool, sửa user/global
MCP registration; không workaround bằng per-repo knowledge store/config.

## Bước 12: Acceptance smoke — installed Claude/Codex thật

**Unit test không thay thế bước này.** Native hook payload/CLI option là external
contract của installed agent CLI.

Với **mỗi adapter family thực sự dùng**, chạy trên một test repository an toàn.

### Smoke A — full response vượt viewport

START một task có acceptance rõ. Yêu cầu final response chứa:

- marker đầu duy nhất, ví dụ `QIQI_NATIVE_START_<nonce>`;
- Unicode tiếng Việt;
- ít nhất vài trăm dòng deterministic để vượt terminal viewport;
- marker cuối duy nhất `QIQI_NATIVE_END_<nonce>`.

Acceptance:

1. `state=settled`;
2. `agent_response` chứa nguyên văn cả hai markers đúng thứ tự;
3. Unicode không hỏng;
4. tail content sau viewport vẫn còn;
5. không có `.qiqi/runs/*.md` mới;
6. SQLite session ownership được tạo nhưng QiQi không đọc DB trực tiếp.

### Smoke B — RESUME exact session

Dùng `session_id` từ Smoke A và RESUME cùng repo/agent. Yêu cầu một response marker
mới.

Acceptance:

1. return cùng native `session_id`;
2. `turn_id` mới;
3. `agent_response` chỉ phản ánh turn mới;
4. RESUME session với repository hoặc agent family khác bị reject.

### Smoke C — native capture fail-closed

Trong test checkout riêng, làm native result hook unavailable/invalid theo cách có
thể hoàn nguyên, không chạm production workspace.

Acceptance:

1. delegation fail rõ;
2. không trả terminal viewport text như semantic response;
3. không parse undocumented transcript;
4. nếu native session identity đã được xác nhận trước failure, error ghi exact
   `session_id` còn resumable.

### Smoke D — blocked continuity (khi adapter có cách tái hiện ổn định)

Chỉ chạy nếu installed agent/Herdr có deterministic test case dẫn tới
`agent_status=blocked` mà không cần đoán UI state.

Acceptance:

1. return `state=blocked`;
2. `session_id` non-empty;
3. `agent_response=null`;
4. RESUME exact session sau khi giải blocker hoạt động;
5. không dùng screen/transcript để dựng blocker text.

Nếu không có deterministic blocked fixture, không giả lập bằng grep/screen và không
claim smoke D đã pass; unit/state-store test chỉ chứng minh local continuity logic.

## Bước 13: Knowledge finalization

Knowledge review/write required cho substantive work có khả năng tạo/xác nhận
reusable conclusion. Trivial/mechanical/report-only work được skip.

Khi review required:

- search existing concept trước create/update;
- create dùng semantic payload, không path/filename;
- update dùng exact ID + expected revision;
- required review không candidate → `entries=[]`;
- persistence failure có candidate phải xuất hiện trong native final response.

Cross-repo impact vẫn phải nằm trong native response khi repository khác cần work;
không phụ thuộc fixed heading.

## Bước 14: Checker ownership

`workspace-check.sh` kiểm orchestration/qiqi_delegate static + unit invariants.
Knowledge Store integrity thuộc `knowledge-template` checker/CLI.

Chỉ coi environment production-ready khi:

1. workspace checker pass;
2. relevant repo checkers pass;
3. Knowledge Store checker pass;
4. Shared Knowledge discovery trong fresh child pass;
5. Native Handoff Smoke A/B/C pass cho **từng adapter family thực sự dùng**;
6. Smoke D pass nếu môi trường có deterministic blocked fixture, hoặc được ghi rõ là
   chưa chạy vì không có fixture — không được thay bằng claim từ unit test.
