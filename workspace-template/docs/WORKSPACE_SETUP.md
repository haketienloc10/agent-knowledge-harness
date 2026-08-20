# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này setup `workspace-template/` sau khi Shared Knowledge MCP đã được cài
user/global scope từ `knowledge-template/`.

## Kết quả cần đạt

- `repos.yaml` trỏ đúng exact Git roots và không alias trùng root;
- `SYSTEM_MAP.md` giữ live topology/ownership/dependency;
- project-scoped `.codex/config.toml` chỉ đăng ký `qiqi_delegate`;
- user-scoped MCP `knowledge` có mặt trong fresh QiQi session và fresh child
  Codex/Claude session;
- QiQi + child đều áp dụng Shared Knowledge decision rule;
- required live/durable premise đi qua structured TaskPacket với provenance;
- live upstream result đi qua QiQi vào downstream `required_context`;
- child không đọc sibling source/runtime state;
- Herdr integrations ở trạng thái `current`;
- native final response capture hoạt động cho adapter thực sự dùng;
- `bash scripts/workspace-check.sh` trả `PASS`.

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

Knowledge MCP **không được thêm vào workspace `.codex/config.toml`**. Store root
được đóng vào stable user wrapper; current workspace/repo/CWD không quyết định
store nào được dùng.

## Bước 2: Điền Repository Registry

Xác nhận từng repo:

```bash
git -C <repository-path> rev-parse --show-toplevel
git -C <repository-path> remote -v
git -C <repository-path> branch --show-current
git -C <repository-path> status --short
```

Điền `repos.yaml` bằng path tương đối từ workspace root. Mỗi path phải là exact Git
root. Không tạo hai registry entry resolve về cùng root.

## Bước 3: Điền System Map

Điền `SYSTEM_MAP.md` từ live evidence cho topology/dependency/contract/ownership
liên repo. Đây là live workspace artifact, **không phải Shared Knowledge Store**.

## Bước 4: Cài Herdr Integrations

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

Selected adapter phải `current`. `qiqi_delegate` không tự install integration.
Herdr vẫn sở hữu interactive workspace/agent lifecycle và native session identity;
result transport không dựa vào pane scrollback.

## Bước 5: Agent Routing

`instructions/agent-routing.yaml` là canonical machine-readable runtime registry.
Version hiện tại là `2`.

Runtime placeholders:

```text
{model}
{session_id}
{route_args}
{handoff_args}
```

Mỗi `start_args` và `resume_args` phải có đúng một `{handoff_args}`. MCP thay slot
này bằng invocation-scoped native Stop-hook config. Không đặt hook command,
`result_path`, result schema hoặc storage path vào routing file.

Routing example dưới `docs/examples/` chỉ là documentation; MCP không load.

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
configuration và độc lập với workspace project config.

Runtime state được tạo tại:

```text
.qiqi/state/qiqi_delegate.sqlite3
```

Path này gitignored. QiQi/child không đọc hoặc sửa database trực tiếp.

## Bước 7: Public TaskPacket Contract

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
- các list khác truyền `[]` khi thực sự không có item;
- mỗi `required_context` item có đúng:

```json
{
  "fact": "...",
  "source": "...",
  "certainty": "verified | user-provided | authoritative-decision"
}
```

Tổng serialized TaskPacket giữ safety boundary 100.000 ký tự, tương ứng giới hạn
100.000 ký tự của public `task` contract trước migration.

## Bước 8: Context Boundary

Execution agent không chia sẻ hidden conversation, hidden reasoning, workspace
control context hoặc sibling state của QiQi.

Nếu QiQi đã dùng một fact để quyết định repository, dependency, scope, constraint,
acceptance criterion hoặc task semantics, fact đó **phải** nằm trong
`required_context` kèm provenance. Không kỳ vọng child tự query lại đúng knowledge
item đó.

Child vẫn được tự:

- inspect current owner repository;
- query Shared Knowledge MCP khi repo decision rule yêu cầu;
- dùng knowledge để enrich/discover/verify context khác.

Child không được tự mở sibling source/runtime state để bù external input bị thiếu.

## Bước 9: Native Result Handoff

START không có `session_id`; RESUME dùng exact native ID cũ. Success trả:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled | failed",
  "agent_response": "<exact native final assistant message>"
}
```

Agent tự chọn structure của final response; không có fixed headings. QiQi phải đọc
**toàn bộ `agent_response`** rồi reconcile với TaskPacket trước bước tiếp theo.

MCP capture native message bằng Stop hook, không dùng terminal viewport và không
parse transcript. Vì vậy response dài hơn một screen không phụ thuộc scrollback.

Nếu native hook không trả final message hợp lệ, call fail rõ; không fallback sang
screen capture, transcript parsing hay agent-written Markdown artifact.

`.qiqi/runs/` chỉ là legacy compatibility input để MCP import ownership metadata khi
RESUME session tạo trước migration; turn mới không đọc/ghi result tại đó.

## Bước 10: Stop-hook Security Model

### Claude

MCP inject `--settings <inline-json>` chứa invocation-scoped command hook cho
`Stop` và `StopFailure`. Hook command là `mcp/qiqi_delegate/result_hook.py` chạy
bằng cùng Python executable của MCP.

### Codex

MCP inject:

```text
--dangerously-bypass-hook-trust
-c features.hooks=true
-c hooks.Stop=<MCP-owned command hook>
```

Flag trust bypass chỉ dùng cho invocation này để Codex chạy exact hook command do
MCP tự dựng. Không đặt flag/hook này trong TaskPacket hoặc route args.

Điều này có nghĩa các hook khác được enable trong cùng Codex invocation cũng không
được dựa vào interactive trust prompt. Workspace/operator phải coi native hook config
của agent là trusted execution configuration. Nếu môi trường có untrusted custom
hooks, không coi setup là accepted cho Codex delegation cho tới khi đã review/remove
chúng.

Hook sink được tạo bằng temporary directory private cho turn; event file được ghi
atomic và permission `0600`. Hook failure không block/continue agent turn; MCP phát
hiện missing/invalid event sau khi agent settle và fail delegation.

## Bước 11: Xác minh Knowledge MCP trong Herdr child

Dùng `delegate_repo_task` với một repo test và read-only TaskPacket yêu cầu agent:

1. xác nhận tool `knowledge_read` available;
2. query một keyword set vô hại khi decision rule thực sự yêu cầu;
3. không mở sibling repo hoặc external knowledge filesystem path;
4. trả native final response bình thường.

Lặp cho mỗi adapter family thực sự dùng. Nếu child không thấy tool, không workaround
bằng project knowledge config trong từng repo; sửa user/global MCP registration.

## Bước 12: Native Handoff Smoke Test

Với **mỗi adapter family thực sự dùng**, chạy một START turn có acceptance rõ và
final response chứa:

- Unicode tiếng Việt;
- một marker đầu response;
- đủ nhiều dòng để vượt terminal viewport;
- một marker cuối response khác biệt.

Acceptance:

1. tool success trả `agent_response` chứa nguyên văn cả marker đầu và marker cuối;
2. Unicode không hỏng;
3. không có `.qiqi/runs/*.md` mới;
4. `.qiqi/state/qiqi_delegate.sqlite3` có thể được MCP dùng để RESUME nhưng QiQi
   không đọc trực tiếp;
5. RESUME exact `session_id` tạo turn mới và trả native response của turn mới;
6. RESUME session với repository/agent khác bị reject;
7. xóa/disable native Stop hook phải làm delegation fail rõ, **không** âm thầm lấy
   output từ screen/transcript.

Smoke này là acceptance runtime bắt buộc. Unit test chỉ chứng minh parser/state
logic, không thay thế việc kiểm exact installed Codex/Claude CLI hook behavior.

## Bước 13: Live Upstream Handoff

Nếu repo B phụ thuộc result mới từ repo A:

```text
repo A agent_response
→ QiQi đọc/reconcile
→ relevant fact/evidence + provenance trong repo B required_context
```

Không dùng Shared Knowledge Store như mailbox thay thế live handoff và không cho
child đọc sibling source/runtime state.

## Bước 14: Knowledge Finalization

Knowledge review/write là required cho substantive work có khả năng tạo hoặc xác
nhận reusable conclusion. Trivial/mechanical/report-only work không tạo reusable
conclusion được skip write.

Khi review là required:

```text
knowledge_write(entries)
```

- search existing concept trước create/update để dedupe;
- create: semantic payload, không path/filename;
- update: exact ID + expected revision từ read;
- required review nhưng không candidate: `entries=[]`;
- write failure có durable candidate phải xuất hiện trong native final response.

Cross-repo impact không có heading bắt buộc; khi có, response phải nêu fact,
affected boundary/repository, evidence và next action đủ để QiQi điều phối.

## Bước 15: Fresh-session Workflow Test

Tối thiểu xác minh:

1. QiQi thấy `knowledge_read` / `knowledge_write` từ workspace root và tự áp dụng
   decision rule thay vì gọi vô điều kiện.
2. START Codex/Claude route thực sự dùng có native handoff smoke pass.
3. TaskPacket giữ original user request và required fact/provenance đến child.
4. Child không giả định hidden QiQi context khi một external fact không được truyền.
5. Một task có verified reusable candidate tự search existing concept, create/update
   phù hợp mà không truyền filename/path.
6. Update bằng exact revision thành công; stale revision bị reject và agent reread.
7. Required review không có candidate dùng `knowledge_write(entries=[])`; trivial
   task được phép skip write hoàn toàn.
8. Repo A → QiQi → repo B live dependency hoạt động qua `required_context` mà repo B
   không đọc repo A source/runtime state.
9. Nếu owner source mâu thuẫn shared knowledge hoặc required context, agent handoff
   conflict/evidence thay vì silently overwrite premise.
10. Single-repo response không conflict được QiQi giữ gần nguyên văn thay vì
    summarize mất caveat/evidence.

## Bước 16: Checker ownership

`workspace-check.sh` kiểm orchestration/qiqi_delegate harness, structured input,
native capture configuration, unit tests và routing invariants. Knowledge Store
integrity thuộc `knowledge-template` checker/CLI; không duplicate knowledge schema
assertions vào workspace checker.

Chỉ coi environment sẵn sàng khi workspace checker pass, Knowledge Store checker
pass và fresh-session native handoff/child discovery smoke test pass cho adapter
thực sự dùng.
