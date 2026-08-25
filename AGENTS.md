# AGENTS.md

Repo này phát triển ba template phối hợp nhưng giữ boundary độc lập:

- `workspace-template/`: QiQi Chief of Staff control plane + synchronous Herdr repo delegation;
- `repo-template/`: workflow tối thiểu cho execution agent trong từng Git repo con;
- `knowledge-template/`: Shared Knowledge Store + user-scoped Knowledge MCP độc lập với
  current workspace/repository.

Repo không chứa tri thức nghiệp vụ thật của một workspace cụ thể.

## Nguyên tắc

- QiQi là Chief of Staff/coordinator, không phải coding agent của repo con.
- Mọi repo-local work từ QiQi đi qua đúng một MCP tool: `delegate_repo_task`.
- Input delegation là structured TaskPacket giữ original `user_request`, objective,
  scope, required context + provenance, constraints, acceptance, verification và known
  unknowns.
- Execution agent không chia sẻ hidden conversation/workspace/sibling context của QiQi.
  External fact QiQi đã dùng để quyết định task semantics phải nằm trong
  `required_context`; child Knowledge MCP không thay required input.
- Output semantic là exact native final `agent_response` capture qua native Stop hook;
  không ép fixed headings và không dùng agent-written Markdown result làm transport.
- Nếu Herdr báo blocked trước native final response, MCP preserve native session
  ownership và trả structured blocked continuity result; không dựng `agent_response`
  từ screen/transcript.
- MCP-owned SQLite giữ runtime session ownership; QiQi/child không đọc/sửa DB trực tiếp.
- QiQi là broker duy nhất của **live execution evidence** giữa repositories: producer
  response được reconcile rồi relevant fact/evidence đi vào downstream
  `required_context`.
- Shared durable knowledge đi qua progressive lifecycle
  `knowledge_search → knowledge_read → knowledge_write`; current repo chỉ là ranking
  hint, không permission boundary.
- Search card là candidate-routing surface, không phải full durable evidence; search
  cố ý không trả revision và không hydrate full top-N.
- Trước create/update knowledge phải search existing concept; existing update target
  phải full-read để lấy semantic payload + exact revision.
- `entries=[]` chỉ dùng sau required review không còn candidate.
- Child không tự đọc sibling source/result/runtime state.
- Product/workspace repo giữ live source/test/topology truth; Shared Knowledge Store giữ
  reusable distilled knowledge. Khi conflict ở owner repo, live evidence thắng.
- Agent không sở hữu knowledge filename/path/directory. Knowledge MCP sở hữu
  ID/path/render/index/locking/revision/persistence.
- Human được phép sửa Shared Knowledge Markdown trực tiếp nếu tuân schema rồi chạy
  `knowledge check`/`knowledge reindex`.
- Knowledge routing metadata dùng canonical concepts; aliases có thể multilingual;
  content tự do và không có field `language`.
- Không đưa vector DB, embedding, translation hoặc LLM vào Knowledge MCP nếu chưa có
  evaluation chứng minh lexical retrieval là bottleneck.

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

Session ownership phải persist ngay khi native identity được biết, trước blocked/
result-capture handling. `agent_response=null` ở blocked state nghĩa native final
message chưa tồn tại; không thay bằng viewport/transcript text.

QiQi đọc toàn bộ `agent_response` khi có rồi đánh giá completion bằng TaskPacket +
evidence. Native response transport **fail closed**: nếu Stop hook không trả final
message hợp lệ, không fallback sang terminal screen, pane scrollback, transcript
parsing hay report Markdown. Nếu native session đã biết, error phải preserve exact
`session_id` để continuation không mất.

`.qiqi/state/qiqi_delegate.sqlite3` là MCP-owned runtime state. `.qiqi/runs/` chỉ là
legacy ownership-import bridge; new turn không dùng Markdown artifact làm
transport/history.

## Shared Knowledge contract

Public tools:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_write(entries)
```

Store là Markdown + generated `INDEX.md` với namespaces `global/`, `systems/`,
`repos/`, `domains/`.

Identity:

```text
<scope-kind>:<scope-id>:<canonical-name>
```

Create không nhận filesystem path. Update bắt buộc exact ID + optimistic revision từ
full `knowledge_read`. Detail document là canonical metadata source; `INDEX.md` là
generated routing projection. Human direct edit làm index stale cho tới khi reindex;
stale search/read/write phải fail rõ.

### Progressive disclosure invariant

```text
knowledge_search(limit <= 10)
→ bounded decision cards only
→ chọn 1–2 exact IDs
knowledge_read(ids)
→ full routing + sources + semantic content + revision
```

Search card chứa `id`, title, scope, summary, bounded `when_to_read`, bounded matches,
score; không chứa `content`, `sources`, `revision`, physical `path` hoặc duplicate
`canonical_name`.

`knowledge_search` vẫn verify revision của selected top hits với index nhưng không
serialize body. `knowledge_read` hydrate tối đa hai unique exact IDs/call. Full read
trả semantic content không chứa canonical H1 để read→write không duplicate heading.

Retrieval deterministic/index-first. Relevance chỉ đến từ exact ID, canonical name,
keywords, aliases, when-to-read và summary; title/scope/path không tự tạo relevance.
Repo/domain context chỉ boost entry đã có semantic match. Query contributions được
bounded để tránh query stuffing.

Knowledge write giữ cross-process lock, atomic replace, revision conflict check và
bounded document size. Semantic merge/dedupe thuộc agent/skill, không MCP core.

### Usage decision invariant

- **MUST search** khi prior reusable knowledge có thể đổi interpretation,
  orchestration, implementation hoặc verification.
- **MAY search** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp.
- **SKIP** cho typo/format/comment-only, exact local lookup, report/status-only đã đủ
  evidence hoặc mechanical work nơi durable context không thể đổi action.
- QiQi không cần duplicate repo-agent query nếu knowledge chỉ ảnh hưởng repo-local
  implementation và không ảnh hưởng orchestration/TaskPacket.
- Fact từ knowledge QiQi đã dùng làm required premise phải nằm trong
  `required_context` với ID/revision/provenance phù hợp.
- **MUST review/write** cho substantive work có khả năng tạo/xác nhận reusable
  conclusion; trivial/mechanical/report-only work được skip.
- `knowledge_write(entries=[])` chỉ dùng sau required review không có candidate.
- Trước create/update phải search existing concept; update existing target phải full
  read trước.

## Khi thay đổi Workspace Template

1. Giữ QiQi task semantics, evidence-reuse gate, delegation waves và Delegation Silence.
2. `.codex/config.toml` chỉ sở hữu project-scoped `qiqi_delegate`; không thêm
   project-specific Knowledge Store.
3. Shared Knowledge MCP phải ở user/global scope để workspace agent và Herdr child cùng
   thấy service independent CWD.
4. Live producer result phải qua QiQi vào downstream `required_context`; child không
   tự đọc sibling source/result/runtime.
5. `SYSTEM_MAP.md` vẫn là live workspace topology artifact.
6. Workspace `AGENTS.md` giữ conditional progressive Knowledge MCP policy.
7. TaskPacket giữ original user request + closed-world context; không quay lại opaque
   prompt-only contract.
8. Native result capture giữ exact final response, không fixed schema, viewport scraping
   hay transcript fallback.
9. Blocked state preserve native session continuity trước cleanup.
10. Execution/runtime hoặc public knowledge-API change phải cập nhật checker + docs +
    migration definition.

## Khi thay đổi Repository Template

1. Giữ Git-root boundary và cấm đọc/sửa sibling source/runtime state.
2. Knowledge MCP là tool exception, không filesystem exception.
3. Agent hiểu task trước khi áp dụng Knowledge decision rule.
4. Search cards chỉ dùng chọn document; material use/update phải full-read exact target.
5. Live owner source/test thắng stale shared knowledge.
6. Substantive work phải knowledge review/write; trivial work được skip.
7. Cross-repo impact phải nằm trong native final response khi repo khác cần work.
8. Không thêm repo-local knowledge store/index hoặc fixed result headings.

## Khi thay đổi Knowledge Template

1. Giữ store độc lập với workspace/repo và không infer root từ CWD.
2. Agent-facing schema không expose arbitrary filesystem path/read/write.
3. Search và exact read phải là hai stage riêng; search không trả revision/content.
4. Full read phải bounded và đủ semantic fields để safe read→write round trip.
5. Identity/canonical path deterministic từ semantic scope/name.
6. `INDEX.md` generate từ detail metadata; không tạo hai source of truth.
7. Human-authored Markdown là first-class workflow; checker/reindex dùng cùng core.
8. Retrieval deterministic/index-first; repo/domain context chỉ boost ranking.
9. Update dùng optimistic revision; external edit không silent overwrite.
10. Không thêm `language`; aliases xử lý multilingual terminology.
11. `sources` bắt buộc; guess/hypothesis chưa verified không persist như fact.
12. Tests cover search thinness/context budget, exact read bounds/round trip,
    stale index/revision, create/update, concurrency, canonical path/traversal,
    multilingual aliases, empty review và batch failure.
13. Agent-facing schema/error phải discoverable, không dựa trial-and-error.

## Migration

Public contract change phải có migration cho workspace/repo đã tồn tại. Migration
framework dùng per-file strategy `replace`, `merge`, `delete`, `manual_review`, pin
exact `from_ref`/`to_ref`, preflight toàn workspace/repo trước khi mutate và lưu state
ở `.qiqi/agent-knowledge-harness-migrations.tsv`.

## Review tối thiểu

Review phải xác nhận:

- public `qiqi_delegate` input là structured TaskPacket;
- required facts có provenance và closed-world boundary;
- native response round-trip không viewport/truncation dependency;
- blocked START giữ `session_id` và RESUME ownership;
- QiQi vẫn broker upstream → downstream live handoff;
- child không đọc sibling source/result/runtime;
- Knowledge MCP user/global registration independent CWD;
- search result thin và full read exact/bounded;
- search không trả revision, update lấy revision từ full read;
- docs/checkers/migration phản ánh cùng architecture;
- static/unit test không được dùng để tuyên bố installed native CLI Stop-hook smoke đã pass.
