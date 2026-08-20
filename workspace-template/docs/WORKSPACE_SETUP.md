# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này setup `workspace-template/` sau khi Shared Knowledge MCP đã được cài
user/global scope từ `knowledge-template/`.

## Kết quả cần đạt

- `repos.yaml` trỏ đúng exact Git roots và không alias trùng root;
- `SYSTEM_MAP.md` giữ live topology/ownership/dependency;
- project-scoped `.codex/config.toml` chỉ đăng ký `qiqi_delegate`;
- user-scoped MCP `knowledge` có mặt trong fresh QiQi session và fresh child
  Codex/Claude session;
- QiQi + child đều áp dụng Shared Knowledge decision rule: read khi prior durable
  context có thể thay đổi quyết định/cách làm, review/write cho substantive work có
  khả năng tạo reusable conclusion, không dùng MCP như ceremony ở task trivial;
- live upstream result vẫn đi qua QiQi vào downstream prompt;
- child không đọc sibling source/result;
- Herdr integrations ở trạng thái `current`;
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

Smoke test tối thiểu trong fresh QiQi session:

1. tool inventory có `knowledge_read` và `knowledge_write`;
2. `knowledge_read` với keyword không match trả results rỗng, không crash;
3. không tạo test knowledge chỉ để smoke nếu chưa có durable fact thực.

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

## Bước 5: Agent Routing

`instructions/agent-routing.yaml` là canonical machine-readable runtime registry
cho execution agent/model/native START/RESUME argv. `instructions/model-routing.md`
chỉ là exact-route selection policy cho QiQi.

Runtime placeholders:

```text
{model}
{session_id}
{result_dir}
{route_args}
```

Routing example dưới `docs/examples/` chỉ là documentation; MCP không load.

## Bước 6: Chuẩn bị qiqi_delegate

```bash
uv sync --project mcp/qiqi_delegate
bash -n scripts/qiqi-mcp-server.sh
python3 -m py_compile mcp/qiqi_delegate/server.py
bash scripts/workspace-check.sh
```

`.codex/config.toml` chỉ expose `delegate_repo_task`. Knowledge MCP đến từ user
configuration và độc lập với workspace project config.

## Bước 7: Xác minh Knowledge MCP trong Herdr child

Đây là acceptance gate quan trọng vì execution agent chạy tại Git root khác.

Dùng `delegate_repo_task` với một repo test và task read-only yêu cầu agent:

1. xác nhận tool `knowledge_read` available;
2. query một keyword set vô hại;
3. **không** mở sibling repo hoặc external knowledge filesystem path;
4. ghi result bình thường.

Lặp cho mỗi adapter family thực sự dùng (Codex/Claude). Nếu child không thấy tool,
không workaround bằng project knowledge config trong từng repo; sửa user/global MCP
registration trước.

## Bước 8: Execution Handoff

QiQi public execution boundary vẫn là:

```text
delegate_repo_task(repository, task, route, session_id?)
```

START không có `session_id`; RESUME dùng exact native ID cũ. Success chỉ trả:

```json
{
  "session_id": "<native-session-id>",
  "result_path": ".qiqi/runs/<repo>-<english-task-slug>-<session-id>.md"
}
```

QiQi phải đọc `result_path` trước bước tiếp theo. Existing evidence đủ thì trả lời
trực tiếp; không START/RESUME chỉ để report lại.

## Bước 9: Context Boundary

### Durable shared context

QiQi và repo agent hiểu task trước rồi áp dụng `AGENTS.md` decision rule:

- **MUST read** khi prior durable knowledge có thể đổi interpretation,
  orchestration, implementation hoặc verification;
- **MAY read** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- **SKIP read** khi durable context không thể đổi hành động hợp lý, như
  typo/format/comment-only, exact local lookup hoặc report/status-only từ evidence
  đã đủ.

`context.repo/domain` chỉ boost ranking. QiQi không cần duplicate child query nếu
knowledge chỉ có thể ảnh hưởng repo-local implementation và không ảnh hưởng
orchestration/task prompt.

### Live upstream context

Nếu repo B phụ thuộc result mới từ repo A:

```text
repo A result_path
→ QiQi đọc/reconcile
→ inline relevant fact/evidence trong repo B task prompt
```

Không dùng Shared Knowledge Store như mailbox thay thế live handoff và không cho
child đọc sibling result/source.

## Bước 10: Knowledge Finalization

Knowledge review/write là required cho substantive work có khả năng tạo hoặc xác
nhận reusable conclusion: implementation/debugging/investigation có kết luận,
design/decision, contract/ownership change hoặc verified operational finding.

Trivial/mechanical/report-only work không tạo reusable conclusion được skip write;
không dùng empty write như ritual.

Khi review là required, sau work/verification agent gọi:

```text
knowledge_write(entries)
```

- search existing concept trước create/update để dedupe;
- create: semantic payload, không path/filename;
- update: exact ID + expected revision từ read;
- required review nhưng không candidate: `entries=[]`;
- write failure có durable candidate phải xuất hiện trong result/caveat.

`### Repo-local Knowledge` trong current result contract là legacy label; repo policy
ghi Knowledge MCP IDs create/update, `None`, hoặc persistence failure ở đây.

`### Cross-repo Impact` vẫn phải ghi live impact nếu repo khác còn cần action.

## Bước 11: Fresh-session Workflow Test

Tối thiểu xác minh:

1. QiQi thấy `knowledge_read` / `knowledge_write` từ workspace root và tự áp dụng
   decision rule thay vì gọi vô điều kiện.
2. START Codex repo turn: child `knowledge_read` hoạt động khi task cần durable
   context; result hợp lệ.
3. START Claude repo turn: child `knowledge_read` hoạt động nếu Claude route được dùng.
4. Một task có verified reusable candidate tự search existing concept, create hoặc
   update phù hợp mà không truyền filename/path; MCP trả ID/path/revision.
5. Follow-up read tìm được document vừa tạo/cập nhật.
6. Update bằng exact revision thành công; stale revision bị reject và agent reread
   trước retry.
7. Required review không có candidate dùng `knowledge_write(entries=[])` và không
   mutate store; trivial task được phép skip write hoàn toàn.
8. Repo A → QiQi → repo B live dependency vẫn hoạt động mà repo B không đọc repo A
   source/result.
9. Shared knowledge có body tiếng Việt vẫn tìm được bằng canonical English routing;
   alias tiếng Việt cũng match khi query tương ứng.
10. Nếu owner source mâu thuẫn shared knowledge, agent dùng live source/test và
    update knowledge chỉ sau verification.
11. Report/status-only hoặc exact local lookup không bị biến thành unnecessary
    knowledge call chỉ để thỏa checklist.

## Bước 12: Checker ownership

`workspace-check.sh` chỉ kiểm orchestration/qiqi_delegate harness. Knowledge Store
integrity thuộc `knowledge-template` checker/CLI; không duplicate knowledge schema
assertions vào workspace checker.

Chỉ coi environment sẵn sàng khi workspace checker pass, Knowledge Store checker
pass và fresh-session child discovery smoke test pass cho adapter thực sự dùng.
