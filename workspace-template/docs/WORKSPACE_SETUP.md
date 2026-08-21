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
- trước mỗi START/RESUME, operator phải **tự approve** native result-capture hook qua
  MCP elicitation; QiQi/model không được tự điền approval;
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

Checker phải import được `Elicit` và `Resolve` từ MCP SDK v2. `.codex/config.toml`
chỉ expose `delegate_repo_task`; Knowledge MCP đến từ user configuration.

Runtime state được tạo tại:

```text
.qiqi/state/qiqi_delegate.sqlite3
```

Path này gitignored. QiQi/child không đọc hoặc sửa database trực tiếp.

`.qiqi/runs/` có thể còn tồn tại từ architecture cũ. MCP chỉ được đọc metadata
legacy ở đó để import session ownership khi RESUME exact session cũ; turn mới không
đọc/ghi semantic result tại đó.

## Bước 7: Public TaskPacket contract

Model-visible input của `delegate_repo_task` là:

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

`hook_approval` **không phải public/model-visible input**. Nó là resolver-owned
parameter được MCP client resolve bằng human elicitation. QiQi/model không được tự
set `hook_approval=true` trong tool arguments để bỏ qua operator.

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

Tổng serialized TaskPacket giữ safety boundary 100.000 ký tự. Không đặt guessed
per-field limit và không đặt native-response size limit tự chế.

## Bước 8: Context boundary

Execution agent không chia sẻ hidden conversation, hidden reasoning, workspace
control context hoặc sibling state của QiQi.

Nếu QiQi đã dùng một fact để quyết định repository, dependency, scope, constraint,
acceptance criterion hoặc task semantics, fact đó **phải** nằm trong
`required_context` kèm provenance. Không kỳ vọng child tự query lại đúng knowledge
item đó.

Child vẫn được inspect current owner repository và query Shared Knowledge MCP khi
repo decision rule yêu cầu. Child không tự mở sibling source/result/runtime state để
bù external input thiếu.

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

Ngay khi native `session_id` được Herdr xác nhận, MCP persist ownership trước mọi
blocked/result-capture branch. Nếu Herdr trả `blocked` trước khi native final
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
được giải quyết. Không scrape screen/transcript để dựng blocker text.

Nếu native result hook thiếu/invalid sau khi session identity đã có, call fail rõ và
error phải ghi session ownership đã được preserve cùng exact `session_id`; không
fallback sang screen/transcript.

## Bước 10: Stop-hook security model và human approval

`delegate_repo_task` dùng MCP resolver elicitation **trước khi tool body chạy**.
Operator phải thấy và quyết định một confirmation mô tả:

- adapter (`codex` hoặc `claude`);
- repository target;
- local helper `mcp/qiqi_delegate/result_hook.py` sẽ chạy khi child turn kết thúc;
- hook chỉ dùng để capture native final assistant message;
- approval chỉ áp dụng cho delegation hiện tại.

Nếu operator decline/cancel, child invocation và native hook không được chạy. Nếu
form được accept nhưng `approve=false`, tool cũng fail trước khi launch child.

### Codex

Codex coi hook đến từ session flags là untrusted trừ khi hook state đã có matching
trusted hash hoặc CLI được yêu cầu bypass hook trust. Handoff hook hiện là
per-turn/dynamic vì command chứa private sink + nonce, nên hash thay đổi mỗi turn và
không phù hợp để persist một trusted hash.

Vì vậy qiqi_delegate chỉ thêm `--dangerously-bypass-hook-trust` vào **child Codex
invocation sau khi human elicitation của delegation đó đã được accept**. Flag này
không phải automatic authorization của QiQi/model: resolver gate chạy trước tool
body và approval field không nằm trong model-visible schema.

Không đặt flag/hook configuration trong route args hoặc TaskPacket. Nếu yêu cầu là
"không bao giờ xuất hiện bypass flag", phải đổi sang architecture hook ổn định với
trust lifecycle khác; không được đơn giản xóa flag khỏi dynamic hook rồi claim
capture vẫn hoạt động.

### Claude

Claude không có equivalent per-hook trust prompt cho command hook được inject bằng
session `--settings`. Vì vậy cùng MCP human elicitation gate được dùng trước khi MCP
inject `--settings <inline-json>` chứa `Stop` và `StopFailure`.

Hook command là `mcp/qiqi_delegate/result_hook.py` chạy bằng cùng Python executable
của MCP. Claude child chỉ được launch sau human approval.

### Hook sink

Hook sink nằm trong private temporary directory của turn. Event được ghi atomic,
permission `0600`; malformed hook input không được block agent turn. MCP validate
nonce/adapter/session identity trước khi nhận event.

## Bước 11: Knowledge MCP trong Herdr child

Dùng một repo test và read-only TaskPacket:

1. child xác nhận `knowledge_read` available;
2. query keyword vô hại khi decision rule thực sự yêu cầu;
3. không mở sibling repo hoặc external knowledge filesystem path;
4. trả native final response bình thường.

Lặp cho mỗi adapter family thực sự dùng.

## Bước 12: Acceptance smoke — installed Claude/Codex thật

**Unit test không thay thế bước này.** Native hook payload/CLI option và MCP
elicitation UI là external contract của installed CLI.

Với **mỗi adapter family thực sự dùng**, chạy trên một test repository an toàn.

### Smoke 0 — human approval gate

Chạy trước các smoke khác, riêng cho Codex và Claude.

**Decline path**:

1. yêu cầu một delegation bình thường;
2. client phải hiện human elicitation trước child execution;
3. decline/cancel confirmation;
4. delegation không được launch child agent và không được chạy result hook;
5. không có native session/result mới do call bị decline;
6. model không được thấy một public `hook_approval` argument để tự approve.

**Accept path**:

1. gọi lại cùng loại delegation;
2. accept confirmation với `approve=true`;
3. child được launch và native result-capture hoạt động;
4. START/RESUME kế tiếp phải tạo approval mới vì approval là per delegation.

Nếu client không render được resolver elicitation hoặc model có thể tự truyền
`hook_approval`, **dừng migration** và coi E2E fail.

### Smoke A — full response vượt viewport

START một task có acceptance rõ. Yêu cầu final response chứa marker đầu duy nhất,
Unicode tiếng Việt, ít nhất vài trăm dòng deterministic để vượt viewport và marker
cuối duy nhất.

Acceptance:

1. `state=settled`;
2. `agent_response` chứa nguyên văn cả hai markers đúng thứ tự;
3. Unicode không hỏng và tail content còn đầy đủ;
4. không có `.qiqi/runs/*.md` mới;
5. SQLite session ownership được tạo nhưng QiQi không đọc DB trực tiếp.

### Smoke B — RESUME exact session

Dùng `session_id` từ Smoke A và RESUME cùng repo/agent. Acceptance:

1. return cùng native `session_id`;
2. `turn_id` mới;
3. `agent_response` chỉ phản ánh turn mới;
4. RESUME session với repository hoặc agent family khác bị reject;
5. operator được hỏi approval mới trước RESUME hook injection.

### Smoke C — native capture fail-closed

Trong test checkout riêng, làm native result hook unavailable/invalid theo cách có
thể hoàn nguyên. Acceptance:

1. delegation fail rõ;
2. không trả terminal viewport text như semantic response;
3. không parse undocumented transcript;
4. nếu native session identity đã được xác nhận trước failure, error ghi exact
   `session_id` còn resumable.

### Smoke D — blocked continuity (khi có fixture deterministic)

Chỉ chạy nếu installed agent/Herdr có deterministic test case dẫn tới
`agent_status=blocked` mà không cần đoán UI state. Acceptance:

1. return `state=blocked`;
2. `session_id` non-empty;
3. `agent_response=null`;
4. RESUME exact session sau khi giải blocker hoạt động;
5. không dùng screen/transcript để dựng blocker text.

Nếu không có deterministic blocked fixture, không claim smoke D đã pass; unit test
không thay thế native smoke.

## Bước 13: Knowledge finalization

Knowledge review/write required cho substantive work có khả năng tạo/xác nhận
reusable conclusion. Trivial/mechanical/report-only work được skip. Cross-repo impact
vẫn phải nằm trong native response khi repository khác cần work; không phụ thuộc
fixed heading.

## Bước 14: Checker ownership

`workspace-check.sh` kiểm orchestration/qiqi_delegate static + unit invariants và
MCP resolver imports. Knowledge Store integrity thuộc `knowledge-template`
checker/CLI.

Chỉ coi environment production-ready khi:

1. workspace checker pass;
2. relevant repo checkers pass;
3. Knowledge Store checker pass;
4. Shared Knowledge discovery trong fresh child pass;
5. **Smoke 0 human approval pass cho Codex và Claude**;
6. Native Handoff Smoke A/B/C pass cho từng adapter family thực sự dùng;
7. Smoke D pass nếu có deterministic fixture, hoặc được ghi rõ chưa chạy.
