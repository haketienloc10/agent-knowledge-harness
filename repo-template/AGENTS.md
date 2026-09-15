# AGENTS.md — Execution agent trong repository con

Agent chịu trách nhiệm investigation, implementation và verification **chỉ trong Git root hiện tại**.

## Sources of truth

```text
TaskPacket            = current delegated assignment
mounted Work Item     = tracked-task durable current context
Repo source/test      = current implementation truth
Knowledge MCP         = reusable implementation/domain truth khi policy cho phép
qiqi_delegate state   = runtime/session truth
```

QiQi là canonical Work Item writer và cross-repo broker. Child không tự mark global task done.

## Bắt đầu

1. Xác nhận current directory là exact Git root.
2. Đọc TaskPacket để hiểu objective/scope/acceptance/constraints.
3. Nếu TaskPacket có trusted fact `work_item=<id>; revision=<n>`, đọc `$QIQI_WORK_ITEMS_DIR/<id>/WORK_ITEM.md` và chỉ lifecycle docs relevant.
4. Đọc repo architecture/verification docs khi cần.
5. Discover source/tests/config nhỏ nhất đủ task.
6. Dùng Shared Knowledge khi reusable context có thể đổi action; không gọi như ceremony.

TaskPacket vẫn phải semantically sufficient. Work Item cung cấp durable continuity, không phải fallback cho missing assignment semantics.

## Work Item boundary

Child MAY read mounted Work Item/lifecycle docs. Child MUST NOT:

- trực tiếp rewrite canonical Work Item;
- tạo turn/history/progress files trong Work Item;
- mark overall task hoặc sibling repo done;
- dùng stale Work Item để override newer TaskPacket instruction.

Nếu Work Item revision trên disk khác delegated revision và khác biệt có thể material, surface về QiQi thay vì tự chọn product truth.

## Multi-turn / investigation

Native session giữ short-term conversational continuity. Durable conclusion cần cho future turns phải xuất hiện trong native final response để QiQi reconcile vào current Work Item/lifecycle state.

Không tạo execution diary. Report material findings/evidence/open question/remaining risk, không report command chronology trừ command/result cần chứng minh verification.

## Repository boundary

- Chỉ đọc/sửa current Git root và authorized external evidence resources.
- Không sửa/delegate sibling repo.
- Không đọc/sửa `.qiqi/state`.
- `$QIQI_WORK_ITEMS_DIR` là exception read-only theo policy cho tracked task.

## Shared Knowledge

Knowledge dùng cho verified reusable repo/domain implementation knowledge, không phải task status hay working log. Live owner source/test thắng stale Knowledge cho current implementation truth.

## Handoff về QiQi

Native final response phải đủ để QiQi reconcile:

- outcome đạt/chưa đạt và phần còn lại;
- material investigation/design/implementation conclusion;
- exact paths/symbols/evidence khi relevant;
- actual verification commands/checks + results hoặc caveat;
- blocker/missing product input;
- cross-repo implication nếu có;
- reusable Knowledge mutation nếu material.

Không cần fixed headings và không thêm synthetic `completed|partial|blocked` semantic status. Runtime state là execution lifecycle; QiQi quyết định semantic completion.
