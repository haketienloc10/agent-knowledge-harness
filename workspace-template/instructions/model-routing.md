# Route Selection Policy cho QiQi

Tệp này chỉ giúp QiQi **chọn exact `route`** để truyền vào
`delegate_repo_task`. Nó không mô tả cách MCP chạy agent.

`instructions/agent-routing.yaml` là machine source of truth duy nhất cho route
đang tồn tại và cho executable, adapter, model, START/RESUME argv cùng native CLI
flags của từng route.

Không copy model ID, permission mode, effort hay CLI flags vào file này. Khi
runtime configuration thay đổi, chỉ registry machine-readable phải đổi.

## Route hiện có

### `claude-haiku`

Dùng cho task nhỏ, cơ học và có phạm vi rõ, khi:

- thay đổi hẹp và ít uncertainty;
- expected outcome cụ thể;
- verification trực tiếp;
- không cần reasoning kiến trúc đáng kể.

### `claude-balanced`

Route mặc định cho phần lớn repo-local implementation, gồm:

- feature/bugfix thông thường;
- refactor có phạm vi vừa;
- test hoặc docs kỹ thuật gắn với implementation;
- investigation cần reasoning ở mức vừa nhưng chưa phải bài toán kiến trúc sâu.

Khi không có lý do rõ để chọn route khác, ưu tiên `claude-balanced`.

### `claude-deep`

Dùng khi task có uncertainty hoặc reasoning cost cao, ví dụ:

- architecture hoặc design trade-off phức tạp;
- migration có nhiều bước/ràng buộc;
- contract thay đổi có blast radius đáng kể;
- bug khó, nguyên nhân chưa rõ hoặc cần reasoning sâu qua nhiều subsystem.

Không chọn route này chỉ vì task dài; chọn vì độ khó reasoning/risk thực sự cao.

### `claude-verifier`

Dùng cho verification/review độc lập khi mục tiêu chính là đánh giá evidence thay
vì implementation, ví dụ:

- review change quan trọng;
- đối chiếu implementation với spec/contract;
- tìm regression/risk sau một delegation khác;
- xác minh claim trước khi QiQi reconcile cross-repo result.

Nếu verifier phát hiện cần implementation mới, QiQi quyết định delegation tiếp
theo; verifier không mặc nhiên trở thành implementation route.

### `codex-balanced`

Dùng khi **Codex được yêu cầu hoặc ưu tiên có chủ đích**, chẳng hạn:

- người dùng hoặc project policy chỉ định Codex;
- task phụ thuộc capability/integration đã được xác minh là phù hợp riêng với
  Codex;
- QiQi có lý do cụ thể để giữ execution trên Codex thay vì route Claude mặc định.

Không chọn Codex chỉ để retry một environment/runtime failure của route khác.

## Quy tắc chọn route

1. Xác định outcome, scope, risk và uncertainty của repo-local task.
2. Chọn route nhẹ nhất vẫn đủ tin cậy để hoàn thành task.
3. Ưu tiên `claude-balanced` khi không có tín hiệu rõ cho fast/deep/verifier hoặc
   Codex.
4. Truyền **exact route name** vào `delegate_repo_task`; không truyền profile name.
5. Không đặt executable, model ID, permission mode, effort, hook config hoặc raw CLI
   flags vào TaskPacket hay public MCP arguments.
6. Nếu route không tồn tại trong `agent-routing.yaml`, route đó không khả dụng dù
   được nhắc ở tài liệu hay ví dụ khác.
7. Không đổi route chỉ để né blocker về environment, dependency, permission hoặc
   product decision; giải quyết blocker thực tế trước.

## Boundary

File này sở hữu duy nhất câu hỏi:

```text
QiQi nên chọn route nào cho task này?
```

Các concern sau **không thuộc route-selection policy** và được mô tả ở artifact
sở hữu tương ứng:

- TaskPacket/prompt semantics → `AGENTS.md` + `identity.md`;
- agent/model/native argv + `{handoff_args}` insertion point → `agent-routing.yaml`;
- START/RESUME, Herdr lifecycle, native session identity, Stop-hook capture và
  SQLite runtime state → MCP;
- dependency/concurrency/delegation waves → `AGENTS.md`;
- setup và smoke test → `docs/WORKSPACE_SETUP.md`.
