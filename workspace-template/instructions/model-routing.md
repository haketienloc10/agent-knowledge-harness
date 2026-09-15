# Route Selection Policy cho QiQi

Tệp này chỉ giúp QiQi **chọn exact `route`** để truyền vào
`delegate_repo_task`. Nó không mô tả cách MCP chạy agent.

`instructions/agent-routing.yaml` là machine source of truth duy nhất cho route
đang tồn tại và cho executable, adapter, model, START/RESUME argv cùng native CLI
flags của từng route.

Không copy model ID, permission mode, effort hay CLI flags vào file này. Khi
runtime configuration thay đổi, chỉ registry machine-readable phải đổi.

## Activation

File này **không phải mandatory startup material**.

Always-on template default invariant nằm ở `AGENTS.md`:

```text
Default delegation route = claude-balanced.
```

Turn không delegate **không đọc** file này chỉ để hoàn thành startup.

Khi một turn thực sự cần delegation, QiQi **đọc file này ngay trước route decision** rồi mới phân loại task vào fast/balanced/deep/verifier/Codex. Không yêu cầu always-on policy tự nhận diện trước các exception signal mà file này định nghĩa.

Sau khi activation xảy ra, nếu `.qiqi/config.local.json` tồn tại thì QiQi đọc file đó cùng route decision. Đây là machine-local runtime preference do workspace setup sinh ra, không phải product/task truth. Hai field liên quan routing là:

```json
{
  "execution_agents": ["claude", "codex"],
  "default_route": "claude-balanced"
}
```

`execution_agents` giới hạn agent family được phép chọn trên machine hiện tại. `default_route` override template default cho trường hợp policy không có lý do rõ để chọn route chuyên biệt khác. Override này **supersede** câu default `claude-balanced` trong always-on template policy; nếu file/field không tồn tại thì fallback vẫn là `claude-balanced`.

Không đọc `.qiqi/config.local.json` cho turn không delegate. Không dùng file local này làm task/product truth và không copy nó vào TaskPacket.

`claude-balanced` vẫn là deterministic template default/fallback khi không có local override và sau khi áp dụng policy không có lý do rõ để chọn route khác. User/project explicit route selection vẫn phải được kiểm tra theo policy, local enabled-agent constraint và route registry trước delegation.

Mục tiêu của activation rule là tránh fixed context tax cho status-only/answer-only
turn nhưng không đánh đổi route-selection correctness ở các turn thực sự delegate.

## Route hiện có

### `claude-fast`

Dùng cho task nhỏ, cơ học và có phạm vi rõ, khi:

- thay đổi hẹp và ít uncertainty;
- expected outcome cụ thể;
- verification trực tiếp;
- không cần reasoning kiến trúc đáng kể.

### `claude-balanced`

Route mặc định template cho phần lớn repo-local implementation, gồm:

- feature/bugfix thông thường;
- refactor có phạm vi vừa;
- test hoặc docs kỹ thuật gắn với implementation;
- investigation cần reasoning ở mức vừa nhưng chưa phải bài toán kiến trúc sâu.

Khi không có local default override và không có lý do rõ để chọn route khác, ưu tiên `claude-balanced`.

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

Independence của route này là rollover signal: khi chọn `claude-verifier` cho
independent verification/review, QiQi **MUST START fresh by default** theo semantic
START/RESUME policy trong `AGENTS.md`. Không reuse implementation native session chỉ
vì verifier dùng cùng underlying native agent family. Chỉ RESUME khi task explicitly
không còn yêu cầu independence và QiQi có affirmative reason cần exact native
continuity.

Nếu verifier phát hiện cần implementation mới, QiQi quyết định delegation tiếp
theo; verifier không mặc nhiên trở thành implementation route.

### `codex-balanced`

Dùng khi **Codex được yêu cầu, được project policy ưu tiên có chủ đích, hoặc được chọn làm machine-local default**, chẳng hạn:

- `.qiqi/config.local.json` chọn `codex-balanced` làm `default_route`;
- người dùng hoặc project policy chỉ định Codex;
- task phụ thuộc capability/integration đã được xác minh là phù hợp riêng với Codex;
- QiQi có lý do cụ thể để giữ execution trên Codex.

Không chọn Codex chỉ để retry một environment/runtime failure của route khác.

## Quy tắc chọn route

1. Xác định outcome, scope, risk và uncertainty của repo-local task.
2. Nếu `.qiqi/config.local.json` tồn tại, loại mọi route thuộc agent family không có trong `execution_agents` trước khi chọn.
3. Chọn route nhẹ nhất vẫn đủ tin cậy để hoàn thành task trong tập route còn được enable.
4. Khi không có lý do rõ cho route chuyên biệt khác, dùng `default_route` từ local config; nếu không có local override thì dùng `claude-balanced`.
5. Truyền **exact route name** vào `delegate_repo_task`; không truyền profile name.
6. Không đặt executable, model ID, permission mode, effort, hook config hoặc raw CLI flags vào TaskPacket hay public MCP arguments.
7. Nếu route không tồn tại trong `agent-routing.yaml`, route đó không khả dụng dù được nhắc ở tài liệu hay ví dụ khác.
8. Không đổi route chỉ để né blocker về environment, dependency, permission hoặc product decision; giải quyết blocker thực tế trước.

## Boundary

File này sở hữu duy nhất câu hỏi:

```text
QiQi nên chọn route nào cho task này?
```

Các concern sau **không thuộc route-selection policy** và được mô tả ở artifact
sở hữu tương ứng:

- TaskPacket/prompt semantics → `AGENTS.md` + `identity.md`;
- semantic START/RESUME rollover decision → `AGENTS.md`;
- agent/model/native argv + `{handoff_args}` insertion point → `agent-routing.yaml`;
- Herdr lifecycle, native session identity, Stop-hook capture và SQLite runtime state → MCP;
- dependency/concurrency/delegation waves → `AGENTS.md`;
- setup + multi-phase session rollover smoke → `docs/WORKSPACE_SETUP.md`.