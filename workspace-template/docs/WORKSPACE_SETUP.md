# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này dùng khi đưa `workspace-template/` vào workspace thực tế. Mục tiêu là
để QiQi giữ vai trò Chief of Staff, dùng `qiqi_delegate` cho repo-local execution
và dùng Shared Knowledge MCP cho durable reusable knowledge độc lập workspace/repo.

## Kết quả cần đạt

Sau setup:

- `repos.yaml` trỏ đúng exact Git root local, không duplicate resolved root;
- `SYSTEM_MAP.md` mô tả live topology/dependency/contract liên repo;
- `qiqi_delegate` project-scoped chỉ expose `delegate_repo_task`;
- Knowledge MCP là server riêng với `knowledge_read` + `knowledge_write`;
- Shared Knowledge Store nằm tại absolute `QIQI_KNOWLEDGE_ROOT`, không derive từ
  workspace/repo/CWD;
- `qiqi_knowledge` được đăng ký **user scope** ở Codex và Claude để QiQi + child
  repo sessions cùng thấy;
- QiQi broker live execution result; Knowledge MCP broker durable reusable knowledge;
- child không tự đọc sibling repository source hoặc sibling result artifact;
- đầu work turn QiQi/repo agent gọi `knowledge_read`; trước finalize gọi
  `knowledge_write`, kể cả `entries=[]` khi không có update;
- Knowledge MCP tests/checker và workspace/repo checker pass;
- START/RESUME/result continuity/concurrency/Delegation Silence không regression.

## Runtime yêu cầu

```bash
command -v codex && codex --version
command -v claude && claude --version
command -v herdr && herdr --version
command -v uv && uv --version
command -v python3
command -v git
command -v rg
command -v yq
```

## Bước 1: Điền Repository Registry và System Map

Xác nhận từng repository:

```bash
git -C <repository-path> rev-parse --show-toplevel
git -C <repository-path> remote -v
git -C <repository-path> branch --show-current
git -C <repository-path> status --short
```

Điền `repos.yaml` bằng path tương đối từ workspace root. Mỗi path phải là exact Git
root. Điền `SYSTEM_MAP.md` bằng evidence thực tế cho topology, dependency, shared
boundary và live contract ownership.

`SYSTEM_MAP.md` vẫn là workspace operational document; không move nó vào Shared
Knowledge Store trong MVP.

## Bước 2: Chuẩn bị qiqi_delegate

Cài Herdr integrations cho execution agents:

```bash
herdr integration install codex
herdr integration install claude
herdr integration status
```

Selected adapter phải báo `current`.

Cài MCP runtime:

```bash
uv sync --project mcp/qiqi_delegate
bash -n scripts/qiqi-mcp-server.sh
python3 -m py_compile mcp/qiqi_delegate/server.py
```

`.codex/config.toml` project-scoped phải chỉ expose:

```text
delegate_repo_task(repository, task, route, session_id?)
```

Knowledge MCP **không** được thêm vào project `.codex/config.toml` này.

## Bước 3: Điền Execution Routing

`instructions/agent-routing.yaml` là canonical runtime execution registry duy nhất
mà `qiqi_delegate` load. Agent entry sở hữu command/adapter/START/RESUME argv;
route entry sở hữu agent/model/route-specific args.

`instructions/model-routing.md` chỉ giúp QiQi chọn exact route, không duplicate
model ID/native CLI flags.

Runtime placeholders hợp lệ:

```text
{model}
{session_id}
{result_dir}
{route_args}
```

Routing examples dưới `docs/examples/` chỉ là documentation-only.

## Bước 4: Tạo Shared Knowledge Store

Chọn một absolute path ổn định, khuyến nghị Git repository riêng:

```bash
export QIQI_KNOWLEDGE_ROOT=/absolute/path/to/shared-knowledge
uv sync --project mcp/knowledge
bash scripts/qiqi-knowledge-store.sh init
bash scripts/qiqi-knowledge-store.sh check
```

Store không phụ thuộc workspace hiện tại. Canonical detail documents được tổ chức
bởi scope `global/system/repo/domain`, còn `INDEX.md` chỉ là generated routing
index.

Full format, human edit, canonical ID/path và source/provenance rules nằm trong
`docs/KNOWLEDGE_STORE.md`.

## Bước 5: Đăng ký Knowledge MCP ở user scope

Từ workspace đã cài template:

```bash
export QIQI_KNOWLEDGE_ROOT=/absolute/path/to/shared-knowledge
launcher="$PWD/scripts/qiqi-knowledge-mcp-server.sh"

codex mcp add qiqi_knowledge \
  --env QIQI_KNOWLEDGE_ROOT="$QIQI_KNOWLEDGE_ROOT" \
  -- bash "$launcher"

claude mcp add qiqi_knowledge --scope user \
  --env QIQI_KNOWLEDGE_ROOT="$QIQI_KNOWLEDGE_ROOT" \
  -- bash "$launcher"
```

Nếu server name đã tồn tại, inspect/remove cấu hình cũ trước khi add lại. Xác nhận
user-scope registration bằng MCP listing/get command tương ứng của CLI đang cài.

Lý do dùng user scope: QiQi chạy ở workspace root nhưng Herdr launch Codex/Claude
ở exact child Git root. Knowledge MCP phải khả dụng độc lập CWD.

## Bước 6: Hiểu Shared Knowledge contract

Public tools:

```text
knowledge_read(keywords, context?, limit?)
knowledge_write(entries)
```

Read lifecycle:

```text
understand task
→ generate multiple task-relevant terms
→ knowledge_read
→ investigation/planning
```

Write lifecycle:

```text
work + verification
→ review reusable verified knowledge
→ knowledge_write
→ terminal result/final answer
```

Không có durable update vẫn gọi:

```text
knowledge_write(entries=[])
```

Agent submit semantic fields, không submit storage filename/path/directory. MCP sở
hữu materialization/index/locking/revision. Routing metadata dùng canonical
terminology, aliases có thể đa ngôn ngữ, content tùy ngôn ngữ, **không có field
`language`**.

Human có thể edit detail Markdown trực tiếp theo exact format rồi chạy:

```bash
bash scripts/qiqi-knowledge-store.sh reindex
bash scripts/qiqi-knowledge-store.sh check
```

Shared knowledge không thay live owner source/test. Nếu owner repo evidence mới
mâu thuẫn document cũ, source/test thắng và knowledge cần được cập nhật.

## Bước 7: Live result handoff vẫn qua QiQi

Knowledge MCP không thay QiQi orchestration boundary.

Khi repo B cần **live result** từ repo A:

```text
repo A terminal result
→ QiQi đọc result_path
→ QiQi chắt lọc fact/evidence
→ inline vào repo B task prompt
→ repo B
```

Repo B không tự mở repo A source/result. Durable shared knowledge thì repo B tự
query qua Knowledge MCP.

Current result headings vẫn giữ:

```text
### Outcome
### Changes
### Verification
### Git State
### Blockers
### Repo-local Knowledge
### Cross-repo Impact
```

`Repo-local Knowledge` là compatibility audit field cho shared knowledge review;
`Cross-repo Impact` là live execution signal, không phải knowledge transport.

## Bước 8: START/RESUME

START không có `session_id`; dòng không rỗng đầu tiên của task là English title ngắn
để derive readable result filename. RESUME dùng exact native ID và same artifact.

Success return chỉ có:

```json
{
  "session_id": "<native-session-id>",
  "result_path": ".qiqi/runs/<repo>-<task-slug>-<session-id>.md"
}
```

QiQi phải đọc result artifact trước bước tiếp theo. Không START/RESUME chỉ để report
lại evidence đã đủ.

Trong một `qiqi_delegate` process, same resolved Git root hoặc same native session
bị reject concurrent call. Trong delegation wave QiQi không poll child state và
không phát progress commentary.

## Bước 9: Chạy checkers

```bash
bash scripts/knowledge-mcp-check.sh
bash scripts/workspace-check.sh
```

Trong từng repository đã áp dụng `repo-template/`:

```bash
bash scripts/repo-check.sh
```

Knowledge checker xác minh core Python syntax/runtime, đúng hai tools, external
root contract, path/field guards, locking/atomic replace và unit tests.

## Bước 10: Smoke test Knowledge MCP

Tối thiểu:

1. QiQi session tại workspace thấy `knowledge_read` + `knowledge_write`.
2. Herdr-launched Codex child tại repo root thấy cùng tools.
3. Herdr-launched Claude child tại repo root thấy cùng tools.
4. Query dùng English concepts + Vietnamese alias tìm đúng document.
5. Body tiếng Việt vẫn được trả khi routing metadata canonical English.
6. Create knowledge không truyền storage path và MCP tự materialize đúng hierarchy.
7. `knowledge_write(entries=[])` hoạt động.
8. Update bằng `id` + `expected_revision` hoạt động.
9. Human sửa document giữa read/write làm stale update bị reject.
10. Human thêm document đúng format → reindex/check → agent đọc được.
11. Human đặt document sai canonical path → checker/reindex fail rõ.
12. Payload agent chứa top-level storage `path/filename/directory` bị reject.

## Bước 11: Smoke test Execution + Knowledge end-to-end

Dùng producer repo A và consumer repo B:

```text
QiQi knowledge_read
→ delegate repo A
→ repo A knowledge_read
→ work/verify
→ repo A knowledge_write
→ terminal result with live Cross-repo Impact
→ QiQi read/reconcile
→ live fact/evidence in repo B prompt
→ repo B knowledge_read
→ work/verify/knowledge_write
→ terminal result
→ QiQi knowledge review/write
```

Workflow chỉ đạt khi durable knowledge đi qua Knowledge MCP và live producer result
vẫn đi qua QiQi; không chấp nhận child-to-child source/result access.

Chỉ coi workspace sẵn sàng khi Knowledge MCP user-scope discovery đã được xác nhận
cho agent CLIs thực tế, checkers pass và START/RESUME + producer→QiQi→consumer smoke
test không regression.
