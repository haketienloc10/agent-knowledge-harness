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
- Work Item delegation đọc same canonical task nhưng chỉ execute current repo;
- Knowledge dùng `knowledge_search → knowledge_read → knowledge_write` progressive disclosure;
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

1. `work_item_get` trước substantive work;
2. dùng current state/revision;
3. làm đúng current repo;
4. `work_item_update` current-repo evidence/checkpoint/blocker/question/handoff;
5. stale revision → reread/reconcile/retry;
6. không mark sibling/overall task done.

Cross-repo remaining work phải quay lại QiQi qua Work Item handoff + native final response.

## 4. Knowledge progressive disclosure

Sau khi hiểu concern:

1. nếu reusable knowledge có thể đổi action, tạo 3–8 discriminative concepts;
2. `knowledge_search` để nhận thin decision cards;
3. chọn tối đa 1–2 exact candidates thực sự cần;
4. `knowledge_read(ids)` để lấy full content/provenance/revision;
5. không dùng search card như full evidence và không lấy revision từ search;
6. before create/update search dedupe; existing update target full-read trước;
7. substantive reusable conclusion review/write bằng `knowledge_write`.

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

Checker xác nhận Work Item authority, progressive Knowledge contract, current-repo boundary và native-result handoff. Product tests vẫn theo `docs/VERIFY.md`.

## 8. Fresh-session smoke

1. TaskPacket identify test Work Item.
2. Child `work_item_get` đúng task.
3. Child update only current repo evidence; QiQi reread thấy revision mới.
4. Stale writer bị reject.
5. `knowledge_search` trả thin cards và không revision.
6. `knowledge_read` exact ID trả full semantic content/sources/revision.
7. Child không mở sibling repo/physical DB/store.
8. Native final response quay lại QiQi bình thường.
