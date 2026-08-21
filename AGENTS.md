# AGENTS.md

Repo này phát triển ba template phối hợp nhưng giữ boundary độc lập:

- `workspace-template/`: QiQi Chief of Staff control plane + synchronous Herdr repo
  delegation;
- `repo-template/`: workflow tối thiểu cho execution agent trong từng Git repo con;
- `knowledge-template/`: Shared Knowledge Store + user-scoped Knowledge MCP độc lập
  với current workspace/repository.

Repo không chứa tri thức nghiệp vụ thật của một workspace cụ thể.

## Nguyên tắc

- QiQi là Chief of Staff/coordinator, không phải coding agent của repo con.
- Mọi repo-local work từ QiQi đi qua đúng một MCP tool: `delegate_repo_task`.
- Input delegation là TaskPacket có cấu trúc, giữ original `user_request`, repo-local
  `objective`, scope, required context + provenance, constraints, acceptance,
  verification và known unknowns.
- Execution agent không chia sẻ hidden conversation/workspace/sibling context của
  QiQi. External fact nào QiQi đã dùng để quyết định task semantics phải nằm trong
  `required_context`; child Knowledge MCP không thay required input.
- Output semantic là exact native final `agent_response` được capture qua native
  Stop hook; không ép fixed headings và không dùng agent-written Markdown result
  artifact làm transport.
- Nếu Herdr báo blocked trước khi native final response tồn tại, MCP phải preserve
  native session ownership và trả structured blocked continuity result; không bịa
  `agent_response` từ screen/transcript.
- MCP-owned SQLite giữ runtime session ownership; QiQi/child không đọc/sửa DB trực
  tiếp.
- QiQi là broker duy nhất của **live execution evidence** giữa repositories:
  producer response được reconcile rồi relevant fact/evidence đi vào downstream
  `required_context`.
- Shared durable knowledge đi qua `knowledge_read` / `knowledge_write`; current repo
  chỉ là ranking hint, không phải permission boundary.
- Knowledge MCP là conditional context/persistence path, không phải ceremony mỗi
  turn.
- Trước create/update knowledge candidate phải search existing concept, dedupe và
  ưu tiên update; `entries=[]` chỉ dùng sau required review không còn candidate.
- Child agent không tự đọc sibling source/result/runtime state.
- Product/workspace repo giữ live source/test/topology truth; Shared Knowledge Store
  giữ reusable distilled knowledge. Khi conflict ở owner repo, live evidence thắng.
- Agent không sở hữu knowledge filename/path/directory. Knowledge MCP sở hữu
  ID/path/render/index/locking/revision/persistence.
- Human được phép sửa Shared Knowledge Markdown trực tiếp nếu tuân schema rồi chạy
  `knowledge check`/`knowledge reindex`.
- Knowledge routing metadata dùng canonical concepts; aliases có thể multilingual;
  content tự do và không có field `language`.
- Không đưa vector DB, embedding, translation hoặc LLM vào Knowledge MCP MVP.

## qiqi_delegate contract

`workspace-template/mcp/qiqi_delegate` sở hữu Herdr execution lifecycle, native
session, Stop-hook capture, runtime state và cleanup. START/RESUME dùng cùng tool.

Public structured input:

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

Settled/failed return:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "settled | failed",
  "agent_response": "<exact native final assistant message>"
}
```

Blocked continuity return:

```json
{
  "session_id": "<native-session-id>",
  "turn_id": "<qiqi-turn-id>",
  "state": "blocked",
  "agent_response": null,
  "blocker_type": "agent_blocked"
}
```

Session ownership phải được persist ngay khi native identity được biết, trước
blocked/result-capture handling. `agent_response=null` ở blocked state nghĩa native
final message chưa tồn tại; không được thay bằng viewport/transcript text.

QiQi đọc toàn bộ `agent_response` khi có rồi đánh giá completion bằng TaskPacket +
evidence. Agent không bị ép khai `Outcome` hoặc headings implementation-specific.

Native response transport **fail closed**: nếu Stop hook không trả final message hợp
lệ, không fallback sang terminal screen, pane scrollback, transcript parsing hay
report Markdown. Nếu native session đã được biết trước capture failure, error phải
preserve/report exact `session_id` để continuation không mất.

`.qiqi/state/qiqi_delegate.sqlite3` là MCP-owned runtime state. `.qiqi/runs/` chỉ
là legacy ownership-import bridge cho session tạo trước migration; new turn không
dùng Markdown artifact làm transport/history.

## Shared Knowledge contract

Public MVP tools:

```text
knowledge_read(keywords, context?, limit?)
knowledge_write(entries)
```

Store là Markdown + generated `INDEX.md` với namespaces:

```text
global/
systems/
repos/
domains/
```

Identity:

```text
<scope-kind>:<scope-id>:<canonical-name>
```

Create không nhận filesystem path. Update bắt buộc exact ID + optimistic revision.
Detail document là canonical metadata source; `INDEX.md` là generated routing
projection. Human direct edit làm index stale cho tới khi reindex; stale read/write
phải fail rõ.

Knowledge write giữ cross-process lock, atomic replace, revision conflict check và
bounded document size. Semantic merge/dedupe thuộc agent/skill, không thuộc MCP core.

### Usage decision invariant

- **MUST read** khi prior reusable knowledge có thể đổi interpretation,
  orchestration, implementation hoặc verification.
- **MAY read** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp.
- **SKIP read** cho typo/format/comment-only, exact local lookup, report/status-only
  đã đủ evidence hoặc mechanical work nơi durable context không thể đổi action.
- QiQi không cần duplicate repo-agent query nếu knowledge chỉ ảnh hưởng repo-local
  implementation và không ảnh hưởng orchestration/TaskPacket.
- Fact từ knowledge mà QiQi đã dùng làm required premise phải nằm trong
  `required_context` với ID/revision hoặc provenance phù hợp.
- **MUST review/write** cho substantive work có khả năng tạo/xác nhận reusable
  conclusion; trivial/mechanical/report-only work được skip.
- `knowledge_write(entries=[])` chỉ dùng sau required review không có candidate.
- Trước create/update phải search existing concept và ưu tiên update.

## Khi thay đổi Workspace Template

1. Giữ QiQi task semantics, evidence-reuse gate, delegation waves và Delegation
   Silence.
2. `.codex/config.toml` chỉ sở hữu project-scoped `qiqi_delegate`; không thêm
   project-specific Knowledge Store.
3. Shared Knowledge MCP phải ở user/global scope để workspace agent và Herdr child
   cùng thấy service independent CWD.
4. Live producer result phải qua QiQi vào downstream `required_context`; child không
   tự đọc sibling source/result/runtime.
5. `SYSTEM_MAP.md` vẫn là live workspace topology artifact.
6. Workspace `AGENTS.md` giữ conditional Knowledge MCP policy.
7. TaskPacket phải giữ original user request + closed-world context; không quay lại
   opaque prompt-only contract.
8. Native result capture phải giữ exact final response, không fixed schema,
   viewport scraping hay transcript fallback.
9. Blocked state phải preserve native session continuity trước khi cleanup.
10. Execution/runtime change bắt buộc cập nhật checker + docs + migration definition.

## Khi thay đổi Repository Template

1. Giữ Git-root boundary và cấm đọc/sửa sibling source/runtime state.
2. Knowledge MCP là tool exception, không phải filesystem exception.
3. Agent hiểu task trước khi áp dụng Knowledge decision rule.
4. Live owner source/test thắng stale shared knowledge.
5. Substantive work phải knowledge review/write; trivial work được skip.
6. Cross-repo impact phải nằm trong native final response khi repo khác cần work.
7. Không thêm repo-local knowledge store/index.
8. Không thêm fixed result headings hoặc agent-written QiQi result artifact.

## Khi thay đổi Knowledge Template

1. Giữ store độc lập với workspace/repo và không infer root từ CWD.
2. Agent-facing write schema không expose filename/path/directory/index path.
3. Identity/canonical path deterministic từ semantic scope/name.
4. `INDEX.md` generate từ detail metadata; không tạo hai source of truth.
5. Human-authored Markdown là first-class workflow; checker/reindex dùng cùng core.
6. Retrieval deterministic/index-first; repo/domain context chỉ boost ranking.
7. Update dùng optimistic revision; external edit không silent overwrite.
8. Không thêm `language`; aliases xử lý multilingual terminology.
9. `sources` bắt buộc; guess/hypothesis chưa verified không persist như fact.
10. Unit/integrity tests cover create/update, stale index/revision, concurrency,
    canonical path/traversal, multilingual aliases, empty review và batch failure.
11. Agent-facing schema/error phải discoverable, không dựa trial-and-error.

## Migration

Execution contract change phải có migration cho workspace/repo đã tồn tại. Migration
`0004` chuyển opaque prompt + Markdown result transport sang TaskPacket + native
Stop-hook response + SQLite session ownership. Repo `AGENTS.md` dùng 3-way merge để
không mặc nhiên xóa product-specific instructions; template-owned runtime/checker/
docs dùng replace với backup behavior của migration framework.

## Review tối thiểu

Review phải xác nhận:

- public `qiqi_delegate` input là structured TaskPacket;
- required facts có provenance và closed-world boundary;
- native response round-trip không viewport/truncation dependency;
- blocked START giữ `session_id` và RESUME ownership;
- fixed result headings/`result_path` không còn trong active contract;
- QiQi vẫn broker upstream → downstream live handoff;
- child không đọc sibling source/result/runtime;
- Knowledge MCP user/global registration independent CWD;
- knowledge usage vẫn conditional, không ceremony;
- docs/checkers/migration phản ánh cùng architecture;
- static/unit test không được dùng để tuyên bố native CLI Stop-hook smoke đã pass.
