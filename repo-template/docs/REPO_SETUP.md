# Thiết lập Repository con cho QiQi Workspace

Tài liệu này dùng khi đưa `repo-template/` vào một Git repository nằm trong
workspace multi-repo.

Fresh repo agent phải thấy hai user-scoped services independent CWD:

```text
Global Work Item MCP   = mutable product-task truth
Knowledge MCP          = reusable durable truth
```

Repo source/test vẫn là implementation truth. `qiqi_delegate` runtime/session state
không thuộc repo agent.

## Kết quả cần đạt

- `AGENTS.md` bảo vệ Git-root/sibling boundaries;
- `ARCHITECTURE.md` và `docs/VERIFY.md` có live evidence;
- nếu TaskPacket identify product Work Item, agent `work_item_get` trước substantive
  work;
- agent đọc cùng canonical task state với QiQi nhưng chỉ execute current Git root;
- agent chỉ update current-repo evidence/state + material blocker/question/handoff /
  checkpoint nó thực sự xác lập;
- cross-repo remaining work quay lại QiQi, agent không tự sửa/delegate sibling repo;
- stale Work Item revision phải reread/reconcile, không silent overwrite;
- agent áp dụng Shared Knowledge decision rule, không query như ceremony;
- native final assistant response là semantic handoff về QiQi, không fixed result
  headings hoặc Markdown result artifact;
- `bash scripts/repo-check.sh` trả `PASS`.

## Bước 1: Xác nhận Git root

```bash
pwd
git rev-parse --show-toplevel
git status --short
```

Template phải nằm đúng Git root.

Không tạo `.qiqi/tasks/` hoặc SQLite task database trong repo. Product task state
đến từ user-scoped Work Item MCP.

## Bước 2: Xác minh user-scoped MCPs

Trong fresh agent session tại repo root, tool inventory phải có:

```text
work_item_get
work_item_list
work_item_create
work_item_update
knowledge_read
knowledge_write
```

CLI registration:

```bash
codex mcp get work_item      # nếu dùng Codex
claude mcp get work_item     # nếu dùng Claude
codex mcp get knowledge      # nếu dùng Codex
claude mcp get knowledge     # nếu dùng Claude
```

Không tạo project-specific Work Item/Knowledge config chỉ để repo này có tool.
Không tự tìm/open Work Item DB hoặc Knowledge Store filesystem path.

## Bước 3: Merge instruction hiện có

Nếu repo đã có `AGENTS.md` hoặc instruction tương đương:

1. giữ workflow đặc thù của repo;
2. gộp Git-root boundary, `ARCHITECTURE.md`, `docs/VERIFY.md`;
3. gộp canonical Work Item read/update policy;
4. gộp closed-world TaskPacket boundary;
5. gộp Shared Knowledge decision rule/lifecycle;
6. gộp cross-repo handoff semantics;
7. không copy qiqi_delegate runtime/Stop-hook mechanics;
8. không ép fixed result schema/artifact;
9. không tạo local duplicate task/knowledge store;
10. ưu tiên 3-way merge thay vì ghi đè product-specific instruction.

## Bước 4: Khảo sát và điền live docs

Thu thập evidence từ manifest/build, source entrypoint, module/package structure,
CI/test/config/runtime và docs hiện hữu.

`ARCHITECTURE.md` mô tả responsibility/module/data flow/boundary bằng live evidence.
`docs/VERIFY.md` mô tả command thực tế, side effect và known verified baseline.

Work Item/Knowledge không thay thế owner source/test/live docs.

## Bước 5: Structured input từ QiQi

TaskPacket truyền:

- original user request liên quan;
- repo-local objective;
- scope/out-of-scope;
- required context + provenance/certainty;
- constraints;
- acceptance criteria;
- required verification;
- known unknowns;
- khi có product task: canonical Work Item ID + revision trong `required_context`.

Ví dụ handoff pointer:

```text
redmine:116655 @ revision 12
```

Revision trong packet không phải immutable snapshot. Child phải `work_item_get` để
lấy current revision/state vì QiQi hoặc agent khác có thể đã update sau delegation
plan.

Execution agent không chia sẻ hidden conversation, hidden reasoning, workspace
control context hoặc sibling source/runtime state của QiQi.

Allowed external context:

```text
canonical Work Item identified by TaskPacket
+ current repo source/test
+ explicit TaskPacket facts
+ Shared Knowledge theo decision rule
```

## Bước 6: Work Item read behavior

Nếu TaskPacket identify Work Item, agent MUST đọc trước substantive work và reconcile:

- `current_requirements`;
- open/resolved `questions`;
- active/superseded `decisions`;
- requirement/scope `changes`;
- current repo state/verification;
- blockers;
- pending handoffs;
- next actions/checkpoints.

Nếu current revision mới hơn packet và task semantics conflict với objective/
constraint trong packet, agent không tự chọn một phía. Finalize conflict/evidence về
QiQi để reconcile.

## Bước 7: Work Item update behavior

Repo agent chỉ update state nó có authority/evidence:

```text
repos[current_repo]
material current-repo checkpoints
blockers discovered here
open questions discovered here
cross-repo handoffs produced/discovered here
```

Agent không:

- mark sibling repo done;
- mark overall Work Item done;
- rewrite global phase/status để tự orchestration;
- resolve customer/product question bằng guess;
- dispatch agent khác.

Trước update:

1. dùng exact revision từ latest `work_item_get`;
2. reconcile current document;
3. arrays replace nguyên tử: giữ entry hiện hành không định xóa;
4. `work_item_update(id, expected_revision, changes)`;
5. conflict → reread → reconcile → retry;
6. persistence vẫn fail → report rõ trong native response, không claim canonical
   state đã update.

## Bước 8: Open question, decision và change

Khi code/investigation gặp external/product ambiguity chưa thể trả lời từ current
repo, persist `questions[].status=open` và blocker nếu cần. Không đoán để unblock.

Product/customer Q&A decision thường do QiQi reconcile sau khi user/customer trả lời:

```text
question resolved
→ decision active
→ current_requirements reconcile nếu semantics đổi
→ changes[] nếu requirement/scope thực sự đổi
```

Technical decision thuộc local implementation authority có thể được agent ghi nếu
material cho continuation. Decision `superseded` không được dùng như current truth.

## Bước 9: Cross-repo handoff

Khi current repo tạo/khám phá impact cho repo khác:

```text
current repo evidence
→ Work Item handoff pending + evidence
→ native response về QiQi
→ QiQi chọn downstream repo/wave
```

Handoff nên có `from`, `to`, `status`, `summary`, evidence khi có. Agent không cần và
không được mở sibling source để “giúp làm nốt”.

## Bước 10: Knowledge read behavior

Sau khi hiểu task/Work Item, agent áp dụng decision rule:

- **MUST read** khi prior reusable knowledge có khả năng đổi implementation,
  verification hoặc interpretation;
- **MAY read** khi query ngắn có thể giảm uncertainty hoặc tránh investigation lặp;
- **SKIP read** cho mechanical/exact local/status-only work nơi durable context không
  thể đổi hành động hợp lý.

Task-specific status, temporary blocker, Q&A riêng ticket và next action thuộc Work
Item, không phải reusable Knowledge.

Nếu Knowledge mâu thuẫn current owner source/test, live source/test thắng cho task
hiện tại; verified reusable conclusion mới mới được persist khi phù hợp.

## Bước 11: Knowledge finalization

Substantive work có khả năng tạo/xác nhận reusable conclusion phải knowledge
review/write sau implementation/investigation + verification và trước final response.

- search existing concept trước create/update;
- create không truyền filesystem path;
- update dùng exact ID/revision từ `knowledge_read`;
- no durable candidate sau required review → `knowledge_write(entries=[])`;
- candidate write failure phải được báo;
- không persist working/task state vào Knowledge MCP.

## Bước 12: Native result về QiQi

Trước final native response của substantive Work Item turn:

1. update canonical Work Item với material current-repo state/evidence;
2. xử lý revision conflict nếu có;
3. thực hiện Knowledge finalization nếu policy yêu cầu;
4. final response nêu result + evidence + verification + blockers/handoffs/caveats có
   thể đổi next orchestration decision.

Native final assistant response là authoritative semantic handoff. Không tạo result
Markdown artifact và không phụ thuộc terminal scrollback.

Agent không tự tuyên bố global Work Item complete; QiQi quyết định completion sau khi
reread canonical state.

## Bước 13: Chạy checker

```bash
bash scripts/repo-check.sh
```

Checker xác nhận Git-root boundary, Work Item policy, structured TaskPacket,
Knowledge lifecycle và native response ownership. Product tests thật vẫn theo
`docs/VERIFY.md`.

## Bước 14: Fresh-session smoke test

Dùng một test Work Item an toàn:

1. QiQi tạo Work Item và include ID + revision trong TaskPacket;
2. fresh repo child thấy `work_item_get` và đọc same Work Item;
3. child đọc current requirements/decisions/handoff thay vì yêu cầu QiQi kể lại;
4. child chỉ sửa current Git root;
5. child update `repos[current_repo]` + checkpoint/handoff bằng exact revision;
6. QiQi reread thấy revision/state mới;
7. stale revision update bị reject;
8. child không đọc sibling source/runtime hoặc external DB/store filesystem;
9. Knowledge read/write vẫn hoạt động theo conditional decision rule;
10. final response giữ material evidence/verification/cross-repo remaining work mà
    không fixed headings.

Chỉ coi repo sẵn sàng khi checker pass và fresh-session Work Item + Knowledge MCP
discovery/update đã được xác nhận cho agent family thực sự dùng.
