# Thiết lập Repository con cho QiQi Workspace

Repo agent dùng bốn nguồn truth:

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
qiqi_delegate state    = runtime/session truth
```

## Kết quả cần đạt

- `AGENTS.md` bảo vệ Git-root/sibling boundaries;
- fresh repo agent thấy user-scoped `work_item` và `knowledge` MCP;
- Work Item delegation đọc bounded canonical task, scoped history on demand và chỉ execute current repo;
- Work Item write dùng grouped typed incremental mutation, không reconstruct historical full arrays và không dùng legacy `{op,value}` envelope;
- Knowledge dùng search → exact scoped read → whole/partial mutation progressive disclosure;
- native final assistant response là semantic handoff về QiQi;
- `bash scripts/repo-check.sh` PASS.

## 1. Xác nhận Git root

```bash
pwd
git rev-parse --show-toplevel
git status --short
```

Template phải ở exact Git root.

## 2. Xác minh user-scoped MCP

```bash
codex mcp get work_item
codex mcp get knowledge
claude mcp get work_item
claude mcp get knowledge
```

Không tạo project-local DB/store/config để bù missing registration.

## 3. Work Item behavior

Nếu TaskPacket identify `redmine:116655 @ revision N`:

1. `work_item_get` bounded current state trước substantive work;
2. dùng exact whole Work Item revision; chỉ `work_item_history_read` khi exact provenance cần;
3. làm đúng current repo;
4. `work_item_update` bằng `WorkItemMutation`:
   - `mutation.state.repos[current_repo]` cho current effective evidence/state;
   - `mutation.operations.checkpoint_append[]` cho material milestone;
   - `mutation.operations.blocker_upsert[]`, `question_upsert[]`, `handoff_upsert[]` trong authority khi cần;
   - omit `state` hoặc operation group không dùng; không gửi `state: {}` boilerplate;
5. mutation success là compact receipt, không full Work Item;
6. stale revision → reread/reconcile/retry; server không auto-rebase dù concurrent writer target khác;
7. không mark sibling/overall task done.

`mutation.operations` là direct grouped typed object. Không gửi operation list `{op,value}` và không dùng intentionally-invalid `work_item_update` calls để dò schema. Các group build một final candidate atomically; cross-group caller order không phải public semantics.

Historical semantic collections không có public full-array replacement path. Repo agent không hydrate/resend checkpoints/questions/handoffs chỉ để append/advance một record.

Cross-repo remaining work phải quay lại QiQi qua Work Item handoff + native final response.

## 4. Knowledge progressive disclosure

Sau khi hiểu concern:

1. nếu reusable knowledge có thể đổi action, tạo 3–8 discriminative concepts;
2. `knowledge_search` để nhận thin decision cards;
3. chọn tối đa 1–2 exact candidates thực sự cần;
4. exact-read ở smallest sufficient semantic scope:
   - `knowledge_read(ids)` khi cần full content;
   - `knowledge_read_metadata(ids)` khi chỉ cần metadata/provenance/revision + section index;
   - `knowledge_read_section(id, section_id)` khi chỉ cần một existing marked section;
5. không dùng search card như full evidence và không lấy revision từ search;
6. before create/update search dedupe; existing update target exact-read sufficient scope trước;
7. create/full replacement dùng `knowledge_write`; metadata/content/one-section partial mutation dùng `knowledge_update`;
8. partial update vẫn dùng whole-document exact revision và không tạo per-section revision/chunk store;
9. substantive reusable conclusion phải qua knowledge-distill review trước mutation.

Live owner source/test thắng stale Knowledge.

## 5. TaskPacket/closed-world boundary

TaskPacket chứa original user request, objective, scope, Work Item ID/revision khi có, required external context + provenance/certainty, constraints, acceptance, verification và known unknowns.

Child không chia sẻ hidden QiQi context và không mở sibling source/result/runtime. Work Item/Knowledge access là tool exception, không filesystem exception.

## 6. Native handoff

Native final assistant response là authoritative semantic handoff. Không fixed result headings, result path hoặc Markdown transport artifact.

Substantive Work Item turn phải persist material repo state trước final response khi possible. Final response giữ evidence/verification/blocker/handoff/caveat cần cho QiQi.

## 7. Checker

```bash
bash scripts/repo-check.sh
```

Checker xác nhận Work Item authority, incremental mutation boundary, progressive Knowledge contract, current-repo boundary và native-result handoff. Product tests vẫn theo `docs/VERIFY.md`.

## 8. Fresh-session smoke

1. TaskPacket identify test Work Item.
2. Child `work_item_get` đúng task và GET không hydrate accumulated checkpoint/resolved history.
3. Child append checkpoint bằng `mutation.operations.checkpoint_append` ở **first valid attempt**, không schema-probing và không resend historical checkpoints; receipt compact.
4. Child partial-resolve blocker/question bằng direct grouped field ở **first valid attempt**, không resend immutable body/full collection.
5. Child update only current repo evidence; QiQi reread thấy revision mới.
6. Stale writer bị reject dù target semantic collection khác.
7. Scoped Work Item history read chỉ dùng khi exact provenance cần và stale cursor bị reject.
8. `knowledge_search` trả thin cards và không revision.
9. `knowledge_read_metadata` trả revision/provenance/section index nhưng không whole content.
10. `knowledge_read_section` trả đúng one section + whole-document revision.
11. `knowledge_update` metadata/section không yêu cầu caller resend untouched whole document và stale revision bị reject.
12. Child không mở sibling repo/physical DB/store.
13. Native final response quay lại QiQi bình thường.

Happy-path Work Item smoke có **zero intentionally-invalid schema discovery calls**.
